"""Deterministic calculations; every table retains scope and observation dates."""
import numpy as np
import pandas as pd

ACTIONS = ['add', 'reduce', 'new_position', 'sold_out', 'initial_disclosure']


def filter_data(data, tickers=None, start=None, end=None):
    out = data.copy()
    if tickers is not None:
        out = out[out.ticker.isin(tickers)]
    if start is not None:
        out = out[out.date.ge(pd.Timestamp(start))]
    if end is not None:
        out = out[out.date.le(pd.Timestamp(end))]
    return out


def positions_for_valuation(data, dataset_type):
    if dataset_type == 'Reported position changes':
        return pd.DataFrame(), 'Reported changes do not establish a complete current portfolio.'
    if data.empty:
        return data.copy(), 'No positions match the active filters.'
    if dataset_type in ['Complete historical snapshots', 'Dated holdings']:
        dates = data.date.dropna()
        if dates.empty:
            return pd.DataFrame(), 'A complete snapshot requires an observation date.'
        latest = dates.max()
        return data[data.date.eq(latest)].copy(), f'Estimate using dated quantities from {latest.date()}; only supplied positions are covered, completeness is unverified. No weights carried forward.'
    return data.copy(), 'Valuation uses supplied current quantities.'


def value_positions(positions, quotes, basis_type='Per share', company_groups=None):
    """Never combine currencies, guess missing quantities, or sum duplicate positions."""
    if positions.empty:
        return {'positions': pd.DataFrame(), 'totals': pd.DataFrame(), 'uncovered': 0}
    out = positions.copy()
    quote_cols = ['ticker', 'market_price', 'quote_currency', 'sector', 'timestamp', 'provider']
    q = quotes.reindex(columns=quote_cols).drop_duplicates('ticker')
    out = out.merge(q, on='ticker', how='left')
    duplicate = out.duplicated('ticker', keep=False)
    currency_match = out.currency.eq(out.quote_currency)
    valid = out.shares.ge(0) & out.market_price.gt(0) & currency_match & ~duplicate
    out['valuation_status'] = 'Covered'
    out.loc[~valid, 'valuation_status'] = 'Uncovered: missing quantity/price, currency mismatch or duplicate'
    out['position_value'] = (out.shares * out.market_price).where(valid)
    out['company_group'] = out.ticker.map(company_groups or {}).fillna(out.ticker)
    out['basis_total'] = out.cost_basis * out.shares if basis_type == 'Per share' else out.cost_basis
    out['unrealized_gain_loss'] = (out.position_value - out.basis_total).where(out.basis_total.ge(0))
    out['allocation_pct'] = np.nan
    totals = []
    for currency, group in out.groupby('currency', dropna=False):
        total = group.position_value.sum(min_count=1)
        covered = group.position_value.notna().sum()
        partial = covered < len(group)
        if pd.notna(total) and total > 0:
            out.loc[group.index, 'allocation_pct'] = group.position_value / total * 100
        totals.append(dict(currency=currency, covered_value=total, priced_positions=int(covered),
                           supplied_positions=len(group), partial=partial,
                           label='Partial covered valuation' if partial else 'Covered valuation'))
    return {'positions': out, 'totals': pd.DataFrame(totals), 'uncovered': int((~valid).sum())}


def activity_summary(data, frequency='Q'):
    events = data[data.ticker.ne('') & data.date.notna() & data.action.isin(ACTIONS)].copy()
    if events.empty:
        return {'events': events, 'counts': pd.DataFrame(), 'frequent': pd.DataFrame(), 'latest': events,
                'max_weights': pd.DataFrame(), 'reentries': pd.DataFrame(), 'durations': pd.DataFrame(), 'streaks': pd.DataFrame()}
    events = events.sort_values(['date', 'source_row'])
    events['period'] = events.date.dt.to_period(frequency).astype(str)
    counts = events.groupby(['period', 'action']).size().unstack(fill_value=0).reindex(columns=ACTIONS, fill_value=0)
    frequent = events[events.action.ne('initial_disclosure')].groupby('ticker').size().rename('adjustments').sort_values(ascending=False).reset_index()
    durations, reentries, streaks = [], [], []
    for ticker, group in events.groupby('ticker'):
        opened, disclosed, last_exit = None, False, None
        previous_quarter, previous_action, run = None, None, 0
        for row in group.itertuples():
            quarter = row.date.to_period('Q').ordinal
            if row.action in ['add', 'reduce']:
                run = run + 1 if previous_action == row.action and previous_quarter == quarter - 1 else 1
                if run >= 2:
                    streaks.append(dict(ticker=ticker, action=row.action, end=row.date.date(), observed_consecutive_quarters=run))
            else:
                run = 0
            previous_quarter, previous_action = quarter, row.action
            if row.action == 'initial_disclosure':
                disclosed = True
            elif row.action == 'new_position':
                if last_exit is not None and row.date > last_exit:
                    reentries.append(dict(ticker=ticker, exit=last_exit.date(), reentry=row.date.date()))
                if opened is None:
                    opened = row.date
            elif row.action == 'sold_out':
                durations.append(dict(ticker=ticker, entry=opened, exit=row.date,
                                      days=(row.date - opened).days if opened is not None else None,
                                      status='Observed entry to exit' if opened is not None else 'Incomplete: entry unobserved'))
                opened, last_exit, disclosed = None, row.date, False
        if opened is not None or disclosed or group.iloc[-1].action in ['add', 'reduce']:
            durations.append(dict(ticker=ticker, entry=opened, exit=pd.NaT, days=None, status='Incomplete: exit unobserved'))
    return dict(events=events, counts=counts, frequent=frequent,
                latest=events[events.date.eq(events.date.max())],
                max_weights=events.groupby('ticker').weight.max().dropna().rename('maximum_observed_weight_pct').reset_index(),
                reentries=pd.DataFrame(reentries), durations=pd.DataFrame(durations), streaks=pd.DataFrame(streaks))


def security_performance(prices, min_observations=3):
    """Common complete observation window; no filled prices or fabricated daily returns."""
    prices = prices.sort_index().apply(pd.to_numeric, errors='coerce')
    prices = prices.where(prices.gt(0))
    common = prices.dropna(how='any')
    if common.shape[0] < min_observations or common.shape[1] == 0:
        return {'metrics': pd.DataFrame(), 'cumulative': pd.DataFrame(), 'note': 'At least three common positive price observations are required.'}
    cumulative = common / common.iloc[0] - 1
    drawdown = common / common.cummax() - 1
    # Use adjacent observations on the provider's union daily index only. Gaps stay missing.
    daily = prices.pct_change(fill_method=None).loc[common.index.min():common.index.max()]
    metrics = pd.DataFrame({
        'return_pct': cumulative.iloc[-1] * 100,
        'max_drawdown_pct': drawdown.min() * 100,
        'annualized_volatility_pct': daily.std(ddof=1).where(daily.count().ge(20)) * np.sqrt(252) * 100,
        'daily_return_observations': daily.count(),
    })
    return {'metrics': metrics, 'cumulative': cumulative * 100,
            'note': f'Common observed window {common.index.min().date()} to {common.index.max().date()}. Daily sampling; sample volatility annualized with √252 (minimum 20 daily returns). Missing prices are never forward-filled. Drawdown uses observed common prices.'}


def portfolio_return_requirements():
    return ['Dated total portfolio valuations including cash', 'Dated external contributions and withdrawals',
            'Complete holdings/transaction and corporate-action history to reconcile valuations',
            'Consistent valuation currency and dated FX rates where needed']


def top_holdings(positions, limit=10):
    """Rank one currency's covered positions; profit share uses all positive gains."""
    covered = positions[positions.position_value.gt(0)].copy()
    if covered.currency.nunique() > 1:
        raise ValueError('Rank holdings separately for each currency.')
    by_value = covered.sort_values(['position_value', 'ticker'], ascending=[False, True]).head(limit)
    profitable = covered[covered.unrealized_gain_loss.gt(0)].copy()
    profitable['profit_share_pct'] = profitable.unrealized_gain_loss / profitable.unrealized_gain_loss.sum() * 100
    by_profit = profitable.sort_values(['unrealized_gain_loss', 'ticker'], ascending=[False, True]).head(limit)
    return {'value': by_value, 'profit': by_profit,
            'missing_basis': int(covered.unrealized_gain_loss.isna().sum()),
            'losses': int(covered.unrealized_gain_loss.lt(0).sum())}


def reported_top_holdings(data, limit=10):
    """Latest record per security across selected quarters, retaining its true date.

    This is a mixed-date historical ranking, not a reconstructed current portfolio.
    Do not resurrect older weights when the latest record is an exit or missing.
    """
    observed = data[data.ticker.ne('')].copy()
    if observed.date.notna().any():
        latest = observed.groupby('ticker').date.transform('max')
        observed = observed[observed.date.eq(latest)]
    observed = observed[~observed.duplicated('ticker', keep=False)]
    observed = observed[observed.action.ne('sold_out') & ~observed.shares.eq(0)]
    return observed.dropna(subset=['weight']).sort_values(['weight', 'ticker'], ascending=[False, True]).head(limit)


def activity_heatmap_data(events, ending_period, row_limit=15, period_limit=12):
    """A readable window of observed periods, ranked by reported event counts."""
    periods = sorted(events.period.unique())
    periods = [p for p in periods if p <= ending_period][-period_limit:]
    window = events[events.period.isin(periods)].copy()
    if window.empty:
        return pd.DataFrame(), pd.DataFrame()
    counts = window.groupby(['ticker', 'period']).size().unstack(fill_value=0).reindex(columns=periods, fill_value=0)
    order = counts.sum(axis=1).sort_values(ascending=False, kind='stable').head(row_limit).index
    counts = counts.loc[order]
    descriptions = window.groupby(['ticker', 'period']).action.apply(
        lambda actions: ', '.join(f'{action.replace("_", " ")}: {count}' for action, count in actions.value_counts().items())
    ).unstack().reindex(index=order, columns=periods).fillna('No event reported in the uploaded records')
    return counts, descriptions


def directional_heatmap_data(events, ending_period, row_limit=15, period_limit=12):
    """One row per stock; color encodes add-minus-reduce event count only.

    Both counts remain visible, including equal counts. Not shares or cash flow.
    """
    periods = [p for p in sorted(events.period.unique()) if p <= ending_period][-period_limit:]
    window = events[events.period.isin(periods) & events.action.isin(['add', 'new_position', 'reduce', 'sold_out'])]
    order = window.groupby('ticker').size().sort_values(ascending=False, kind='stable').head(row_limit).index
    rows, details, labels = {}, {}, {}
    for ticker in order:
        rows[ticker], details[ticker], labels[ticker] = [], [], []
        for period in periods:
            actions = window.loc[window.ticker.eq(ticker) & window.period.eq(period), 'action']
            adds = int(actions.isin(['add', 'new_position']).sum())
            reduces = int(actions.isin(['reduce', 'sold_out']).sum())
            rows[ticker].append(adds - reduces)
            labels[ticker].append(f'↑{adds}  ↓{reduces}' if adds + reduces else '')
            detail = ', '.join(f'{action.replace("_", " ")}: {count}' for action, count in actions.value_counts().items())
            details[ticker].append(detail or 'No event reported in the uploaded records')
    return tuple(pd.DataFrame.from_dict(values, orient='index', columns=periods)
                 for values in [rows, details, labels])


def bubble_activity_analysis(events):
    """Observed changes only; signed-log coordinates retain zero and reductions."""
    usable = events[events.action.isin(['add', 'reduce', 'new_position', 'sold_out'])].copy()
    valid = (np.isfinite(usable.share_change_pct) & np.isfinite(usable.weight)
             & usable.weight.between(0, 100))
    points = usable[valid].copy()
    points['change_axis'] = np.sign(points.share_change_pct) * np.log10(1 + points.share_change_pct.abs())
    points['bubble_area'] = points.weight.clip(lower=.25)
    insights = []
    def describe(row):
        return f'{row.ticker} ({row.date.strftime("%b %Y")})'
    additions = points[points.action.isin(['add', 'new_position']) & points.share_change_pct.gt(0)]
    reductions = points[points.action.isin(['reduce', 'sold_out']) & points.share_change_pct.lt(0)]
    if not additions.empty:
        largest = additions.loc[additions.share_change_pct.idxmax()]
        insights.append(f'Biggest percentage increase — {describe(largest)}: shares held rose by {largest.share_change_pct:,.2f}%. The stock made up {largest.weight:.2f}% of the portfolio afterward. A big increase does not always mean a big holding.')
    if not points.empty:
        largest = points.loc[points.weight.idxmax()]
        insights.append(f'Biggest holding shown — {describe(largest)}: this stock represented about {largest.weight:.2f} out of every 100 invested in the portfolio at that time. That is why its bubble is large.')
        insights.append(f'A useful comparison — in half of the {len(points):,} records shown, the number of shares went up or down by no more than {points.share_change_pct.abs().median():,.2f}%.')
    if not reductions.empty:
        largest = reductions.loc[reductions.share_change_pct.idxmin()]
        insights.append(f'Biggest percentage cut — {describe(largest)}: shares held fell by {abs(largest.share_change_pct):,.2f}%. The stock made up {largest.weight:.2f}% of the portfolio afterward.')
    return {'points': points, 'insights': insights, 'omitted': len(events) - len(points)}
