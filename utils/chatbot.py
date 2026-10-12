"""Local, deterministic portfolio assistant. No network or model calls."""
import json
import re
import pandas as pd
from utils.analytics import activity_summary, portfolio_return_requirements, reported_top_holdings


def records(frame, limit=15):
    if frame is None or frame.empty:
        return []
    # JSON encoding handles NaN and dates without credentials or raw full uploads.
    clean = frame.head(limit).copy()
    for col in clean.select_dtypes(include='object'):
        clean[col] = clean[col].map(lambda x: str(x)[:180] if x is not None else None)
    return json.loads(clean.to_json(orient='records', date_format='iso'))


def build_context(data, dataset_type, filters, valuation=None, performance=None, market=None):
    summary = activity_summary(data) if dataset_type == 'Reported position changes' else None
    context = dict(dataset_type=dataset_type, filters=filters, row_count=len(data),
                   unique_tickers=int(data.ticker.nunique()),
                   missing_fields={col: int(data[col].isna().sum()) for col in ['shares', 'cost_basis', 'date']},
                   actual_portfolio_returns={'available': False, 'required': portfolio_return_requirements()},
                   note='Local context signature contains selected rows and aggregates; answers use the full filtered data. Dates bound observations, not guaranteed complete coverage.')
    if summary is not None:
        context.update(action_counts=summary['events'].action.value_counts().to_dict(),
                       latest_changes=records(summary['latest']),
                       frequent_adjustments=records(summary['frequent']), reentries=records(summary['reentries']),
                       largest_relative_increases=records(summary['events'].sort_values('share_change_pct', ascending=False)),
                       largest_share_increases=records(summary['events'].sort_values('share_change', ascending=False)))
    if valuation:
        context['valuation_totals'] = records(valuation.get('totals'))
        positions = valuation.get('positions', pd.DataFrame())
        context['largest_covered_positions'] = records(positions.sort_values('position_value', ascending=False)) if not positions.empty else []
    if performance:
        context['security_risk'] = records(performance.get('metrics', pd.DataFrame()).reset_index())
        context['risk_method'] = performance.get('note')
    if market:
        context['market_sources'] = records(market.get('quotes'), 10)
        context['adjustments'] = market.get('adjustments')
        context['provider_failures'] = market.get('failures')
    return context


HELP = ('I can answer questions about your CSV: biggest additions or reductions, latest-quarter changes, '
        'top reported holdings, exits and re-entries, missing data, and a stock’s history. '
        'Try “What changed in the latest quarter?” or “Tell me about AAPL”. '
        'This is a local rule-based assistant, so it cannot answer every wording or predict stock prices.')


def _intent(question):
    q = question.lower()
    if any(x in q for x in ['predict', 'forecast', 'should i', 'will it', 'will the', 'why did buffett']):
        return 'unsupported'
    if any(x in q for x in ['why can', 'portfolio return', 'missing', 'cannot', "can't"]):
        return 'missing'
    if any(x in q for x in ['heatmap', 'heat map', 'bubble', 'chart mean', 'explain chart']):
        return 'chart'
    if any(x in q for x in ['risk', 'volatility', 'drawdown', 'return', 'performance']):
        return 'risk'
    if any(x in q for x in ['profit', 'gain', 'loss']):
        return 'profit'
    if any(x in q for x in ['re-entry', 'reentry', 'reentries', 're-entries', 're-enter', 'bought again']):
        return 'reentry'
    if any(x in q for x in ['latest', 'last quarter', 'recent', 'what changed']):
        return 'latest'
    if any(x in q for x in ['sold out', 'exit']):
        return 'exit'
    if any(x in q for x in ['reduce', 'reduction', 'decrease', 'sell', 'sold']):
        return 'reduce'
    if any(x in q for x in ['increase', 'addition', 'added', 'buy', 'bought']):
        return 'add'
    if any(x in q for x in ['holdings', 'dominate', 'allocation', 'weight', 'portfolio share', 'top 10']):
        return 'holdings'
    if any(x in q for x in ['summary', 'summarize', 'overview', 'history', 'tell me', 'about']):
        return 'summary'
    return None


def ask_local(question, history, data, dataset_type, filters, valuation=None, performance=None):
    """Answer with bounded templates over the entire validated, filtered dataset."""
    if data is None or data.empty:
        return {'ok': True, 'message': 'No CSV rows match the active filters. Upload a CSV or widen the sidebar selection.'}
    frame = data.copy()
    words = set(re.findall(r'[A-Za-z0-9.^=\-]+', question.upper()))
    tickers = [s for s in frame.ticker.unique() if s and s in words and (len(s) > 1 or s in question.split())]
    intent = _intent(question)
    named = re.search(r'\b(?:about|for)\s+([A-Z][A-Z0-9.-]{1,14})\b', question)
    if named and named[1] not in set(frame.ticker):
        return {'ok': True, 'message': f'{named[1]} is not present in the active CSV selection. Check the ticker and sidebar filters.'}
    if tickers:
        frame = frame[frame.ticker.isin(tickers)]
        if intent in (None, 'summary'):
            # A short ticker follow-up inherits the previous supported topic.
            if len(question.split()) <= 4:
                prior = next((m['content'] for m in reversed(history) if m.get('role') == 'user'), '')
                intent = _intent(prior) or 'summary'
    quarter = re.search(r'\b(\d{4})\s*Q([1-4])\b', question, re.I)
    if quarter:
        frame = frame[frame.date.dt.to_period('Q').astype(str).eq(f'{quarter[1]}Q{quarter[2]}')]
    if frame.empty:
        return {'ok': True, 'message': 'No matching observations exist within your current CSV filters.'}
    dates = frame.date.dropna()
    scope = f'Source: uploaded CSV · {len(frame):,} matching rows'
    if not dates.empty:
        scope += f' · {dates.min().date()} to {dates.max().date()}'
    if tickers:
        scope += ' · ' + ', '.join(tickers)
    scope += '. Sidebar ticker/date filters apply.'
    def answer(message, source=scope):
        return {'ok': True, 'message': message + '\n\n' + source}
    def events_text(rows):
        lines = []
        for row in rows.head(10).itertuples():
            line = f'{row.ticker} — {row.date.date()}: {row.action.replace("_", " ")}'
            if pd.notna(row.share_change_pct):
                line += f'; shares {row.share_change_pct:+,.2f}%'
            if pd.notna(row.weight):
                line += f'; reported portfolio share {row.weight:.2f}%'
            lines.append('• ' + line)
        return '\n'.join(lines)
    if intent == 'unsupported' or intent is None:
        return answer(HELP)
    if intent == 'missing':
        counts = ', '.join(f'{col.replace("_", " ")}: {frame[col].isna().sum()} missing' for col in ['shares', 'cost_basis', 'date'])
        return answer('This CSV cannot establish actual portfolio returns. It needs:\n' +
                      '\n'.join('• ' + item for item in portfolio_return_requirements()) + '\n\n' + counts +
                      '. Missing information is not treated as zero.')
    if intent == 'chart':
        if 'bubble' in question.lower():
            return answer('Each bubble is one dated change. Green means more shares; red means fewer. Bigger bubbles mean larger portfolio weights. The horizontal scale compresses extreme changes; hover shows the original values. It is not a profit chart.')
        return answer('The heatmap combines reported events by year (or quarter). Green means more additions than reductions; red means more reductions. Neutral can mean equal counts or no event. Hover shows both counts. Initial disclosures are not counted as purchases.')
    if intent == 'risk':
        metrics = performance.get('metrics', pd.DataFrame()) if performance else pd.DataFrame()
        metrics = metrics.loc[metrics.index.isin(frame.ticker)]
        if metrics.empty:
            return answer('The CSV alone does not contain an adjusted price series for security returns or risk. This local assistant makes no price requests. If you already loaded market history in the sidebar, its calculated metrics can be explained here. Actual portfolio returns still require cash flows and valuations.')
        lines = []
        for ticker, row in metrics.head(10).iterrows():
            values = [f'{label}: {row[col]:.2f}%' for col, label in [('return_pct', 'return'), ('max_drawdown_pct', 'largest drop from a prior peak'), ('annualized_volatility_pct', 'annualized volatility')] if pd.notna(row[col])]
            lines.append('• ' + ticker + ' — ' + '; '.join(values))
        return answer('\n'.join(lines) + '\nThese are security results, not account profits.', scope + '\nSource: previously loaded Yahoo Finance history. ' + performance.get('note', ''))
    if intent in ['holdings', 'profit']:
        positions = valuation.get('positions', pd.DataFrame()) if valuation else pd.DataFrame()
        if not positions.empty:
            positions = positions[positions.ticker.isin(frame.ticker)]
        if intent == 'profit':
            if positions.empty or positions.unrealized_gain_loss.notna().sum() == 0:
                return answer('Profit is unavailable: it requires priced holding quantities and a valid cost basis. Changes in shares or portfolio percentages are not profits.')
            lines = []
            for currency, group in positions.groupby('currency'):
                for row in group.dropna(subset=['unrealized_gain_loss']).sort_values('unrealized_gain_loss', ascending=False).head(10).itertuples():
                    lines.append(f'• {row.ticker}: {row.unrealized_gain_loss:,.2f} {currency} unrealized gain/loss')
            return answer('\n'.join(lines) + '\nOnly positions with valid basis and prices are included; currencies are separate.', scope + '\nValuation source: supplied quantities and previously loaded Yahoo Finance prices.')
        if not positions.empty and positions.position_value.notna().any():
            lines = []
            for currency, group in positions.groupby('currency'):
                for row in group.dropna(subset=['position_value']).sort_values('position_value', ascending=False).head(10).itertuples():
                    share = f'{row.allocation_pct:.2f}%' if pd.notna(row.allocation_pct) else 'unavailable'
                    lines.append(f'• {row.ticker}: {row.position_value:,.2f} {currency}; share of covered value {share}')
            return answer('\n'.join(lines) + '\nRanked within each currency using covered positions only; totals may be partial. Dated quantities produce estimates.', scope + '\nValuation source: CSV and previously loaded Yahoo Finance prices.')
        ranked = reported_top_holdings(frame)
        if ranked.empty:
            return answer('No usable reported portfolio weights or covered valuations are available. Share counts alone cannot tell us which holding is most valuable.')
        lines = [f'• {row.ticker}: {row.weight:.2f}% (observed {row.date.date() if pd.notna(row.date) else "date not supplied"})' for row in ranked.itertuples()]
        return answer('\n'.join(lines) + '\nEach stock uses its latest record in the selected data. Dates may differ; these percentages must not be added together or treated as today’s portfolio.')
    summary = activity_summary(frame) if dataset_type == 'Reported position changes' else None
    if summary is None or summary['events'].empty:
        return answer(f'This selection contains {len(frame)} rows and {frame.loc[frame.ticker.ne(""), "ticker"].nunique()} stocks. Dated, recognized activity records are needed to explain purchases or sales; holdings alone do not establish trading history.')
    events = summary['events']
    if intent == 'latest':
        period = events.date.dt.to_period('Q').max()
        rows = events[events.date.dt.to_period('Q').eq(period)]
        return answer(f'Latest observed quarter: {period} · {len(rows)} reported changes.\n' + events_text(rows) + '\nShowing up to 10 records. Missing rows do not prove no activity.')
    if intent in ['add', 'reduce', 'exit']:
        actions = {'add': ['add', 'new_position'], 'reduce': ['reduce', 'sold_out'], 'exit': ['sold_out']}[intent]
        rows = events[events.action.isin(actions)]
        numeric = rows.dropna(subset=['share_change_pct'])
        if not numeric.empty and intent != 'exit':
            rows = numeric.sort_values('share_change_pct', ascending=intent == 'reduce')
            label = 'Largest reported percentage changes in shares (individual observations, not summed across quarters)'
        else:
            rows = rows.sort_values('date', ascending=False)
            label = 'Latest matching reported events; comparable percentage changes are unavailable' if intent != 'exit' else 'Latest reported exits'
        if rows.empty:
            return answer('No matching reported events in this selection. Initial disclosures are not purchases.')
        return answer(label + ':\n' + events_text(rows) + '\nShowing up to 10. Event counts are not dollar flows or profit.')
    if intent == 'reentry':
        rows = summary['reentries']
        if rows.empty:
            return answer('No exit followed by a new position is observed in this selected history.')
        return answer('\n'.join(f'• {r.ticker}: exit {r.exit}, re-entry {r.reentry}' for r in rows.head(10).itertuples()) + '\nObserved dates only; showing up to 10.')
    counts = events.action.value_counts()
    totals = ', '.join(f'{action.replace("_", " ")}: {count}' for action, count in counts.items())
    return answer(f'{events.ticker.nunique()} stocks · {len(events)} recognized reported events.\n{totals}.\n\nLatest observations:\n' + events_text(events.sort_values('date', ascending=False)) + '\nInitial disclosures are not purchases. This history does not establish a complete current portfolio.')
