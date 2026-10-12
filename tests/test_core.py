from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pandas as pd
import pytest
from utils.data_loader import normalize, detect_mapping, read_csv, manual_watchlist
from utils.validation import validate
from utils.analytics import (value_positions, positions_for_valuation, activity_summary,
                             security_performance, filter_data, portfolio_return_requirements)
from utils.market_data import get_market_data, clear_cache
from utils.chatbot import build_context, ask_local
from utils.state import activate


def normalized(rows):
    frame = pd.DataFrame(rows).fillna('').astype(str)
    return normalize(frame, detect_mapping(frame), percentage_units={k: 'Percentage points' for k in ['weight', 'share_change_pct', 'portfolio_change_pct']})[0]


def quotes():
    return pd.DataFrame([{'ticker': 'A', 'market_price': 100, 'quote_currency': 'USD'},
                         {'ticker': 'B', 'market_price': 200, 'quote_currency': 'USD'}])


def holdings():
    return normalized([dict(ticker='A', shares=10), dict(ticker='B', shares=5)])


def test_valuation_and_partial_coverage():
    result = value_positions(holdings(), quotes())
    assert result['totals'].iloc[0].covered_value == 2000
    assert result['positions'].allocation_pct.tolist() == [50, 50]
    result = value_positions(holdings(), quotes().iloc[:1])
    assert result['totals'].iloc[0].partial
    assert result['totals'].iloc[0].covered_value == 1000
    assert result['uncovered'] == 1
    assert pd.isna(result['positions'].iloc[1].position_value)


def test_missing_prices_and_missing_quantities_never_zero():
    result = value_positions(holdings(), pd.DataFrame())
    assert pd.isna(result['totals'].iloc[0].covered_value)
    d = normalized([dict(ticker='A', shares='', portfolio_pct='0.00%')])
    assert pd.isna(d.shares.iloc[0]) and d.weight.iloc[0] == 0
    assert pd.isna(value_positions(d, quotes())['positions'].position_value.iloc[0])


def test_currency_and_basis():
    d = holdings()
    d.loc[1, 'currency'] = 'EUR'
    result = value_positions(d, quotes())
    assert len(result['totals']) == 2
    assert pd.isna(result['positions'].iloc[1].position_value)
    d = holdings()
    d['cost_basis'] = 50
    assert value_positions(d, quotes())['positions'].unrealized_gain_loss.tolist() == [500, 750]
    assert value_positions(d, quotes(), 'Total position')['positions'].unrealized_gain_loss.tolist() == [950, 950]


def test_aliases_units_mapping_and_dates():
    frame = pd.DataFrame({'symbol': ['a'], 'period': ['2024 Q2'], 'portfolio_pct': ['.5'], 'shares_held_after': ['1,200']})
    mapping = detect_mapping(frame)
    with pytest.raises(ValueError, match='percentage units'):
        normalize(frame, mapping, percentage_units={})
    d, _ = normalize(frame, mapping, percentage_units={'weight': 'Fractions'})
    assert d.weight.iloc[0] == 50 and d.shares.iloc[0] == 1200
    assert d.date.iloc[0] == pd.Timestamp('2024-06-30')
    with pytest.raises(ValueError, match='only one'):
        normalize(frame, {'ticker': 'symbol', 'company': 'symbol'}, percentage_units={})
    with pytest.raises(ValueError, match='not present'):
        normalize(frame, {'ticker': 'missing'}, percentage_units={})


def test_validation_reports_source_rows_and_duplicates():
    d = normalized([dict(ticker='A', period='2024 Q1', action='add', shares=-1, shares_change=-2),
                    dict(ticker='A', period='2024 Q1', action='sold_out', shares=10, price=10, value=1)])
    issues = validate(d, 'Reported position changes')
    assert 'error' in issues.severity.values
    assert issues.message.str.contains('Duplicate').sum() == 2
    assert issues.message.str.contains('Sold-out').any()
    assert issues.message.str.contains('2%').any()
    assert set(issues.source_row) == {2, 3}
    assert value_positions(pd.concat([holdings(), holdings()]), quotes())['uncovered'] == 4


def test_invalid_numeric_and_unknown_actions():
    raw = pd.DataFrame({'ticker': ['A'], 'shares': ['oops'], 'action': ['magic']})
    d, issues = normalize(raw, detect_mapping(raw), percentage_units={})
    assert issues[0]['source_row'] == 2
    assert d.action.iloc[0] == 'unknown'
    assert activity_summary(d)['events'].empty


def test_action_counts_reentry_and_incomplete_duration():
    raw = read_csv(Path('sample_data/quarterly_activity.csv').read_bytes())
    d, _ = normalize(raw, detect_mapping(raw), percentage_units={'weight': 'Percentage points', 'share_change_pct': 'Percentage points'})
    s = activity_summary(d)
    assert s['counts'].sum().to_dict() == dict(add=1, reduce=1, new_position=2, sold_out=1, initial_disclosure=1)
    assert s['reentries'].ticker.tolist() == ['DEMO']
    assert s['durations'].iloc[0].status == 'Incomplete: entry unobserved'
    assert positions_for_valuation(d, 'Reported position changes')[0].empty


def test_observed_duration_and_gap_breaks_streak():
    d = normalized([dict(ticker='A', date='2024 Q1', action='new_position'),
                    dict(ticker='A', date='2024 Q2', action='add'),
                    dict(ticker='A', date='2024 Q4', action='add'),
                    dict(ticker='A', date='2025 Q1', action='sold_out')])
    result = activity_summary(d)
    assert result['streaks'].empty
    assert result['durations'].iloc[0].days == 365


def test_snapshot_uses_one_complete_period_without_carrying_positions():
    d = normalized([dict(ticker='A', date='2024 Q1', shares=10), dict(ticker='B', date='2024 Q2', shares=5)])
    selected, note = positions_for_valuation(d, 'Complete historical snapshots')
    assert selected.ticker.tolist() == ['B'] and 'dated quantities' in note


def test_returns_drawdown_and_missing_values():
    prices = pd.DataFrame({'A': [100, 120, 90]}, index=pd.date_range('2024-01-01', periods=3))
    result = security_performance(prices)
    assert result['metrics'].loc['A', 'return_pct'] == pytest.approx(-10)
    assert result['metrics'].loc['A', 'max_drawdown_pct'] == pytest.approx(-25)
    assert pd.isna(result['metrics'].loc['A', 'annualized_volatility_pct'])
    assert security_performance(prices.iloc[:2])['metrics'].empty
    missing = pd.DataFrame({'A': [100, np.nan, 120, 90]}, index=pd.date_range('2024-01-01', periods=4))
    result = security_performance(missing)
    assert result['metrics'].loc['A', 'daily_return_observations'] == 1
    assert len(portfolio_return_requirements()) >= 3


def test_market_partial_failure_cache_and_mock():
    clear_cache()
    calls = []
    def fetch(symbol, start, end):
        calls.append(symbol)
        if symbol == 'BAD':
            raise RuntimeError('private details')
        return {'ticker': symbol, 'market_price': 100}, pd.Series([100, 110], name=symbol), 'Adjusted'
    result = get_market_data(['A', 'BAD'], '2024-01-01', '2024-02-01', fetch)
    assert result['quotes'].ticker.tolist() == ['A'] and 'BAD' in result['failures']
    get_market_data(['A'], '2024-01-01', '2024-02-01', fetch)
    assert calls.count('A') == 1
    assert 'private details' not in str(result)


def test_context_filters_new_upload_and_credentials():
    d = filter_data(holdings(), ['A'])
    context = build_context(d, 'Current holdings', {'tickers': ['A']})
    assert context['row_count'] == 1 and context['filters']['tickers'] == ['A']
    assert not context['actual_portfolio_returns']['available']
    assert ask_local('summary', [], d, 'Current holdings', {})['ok']
    state = dict(messages=['old'], market={'old': True}, data=holdings(), filters_tickers=['B'])
    activate(state, d, d, pd.DataFrame(), 'Current holdings', 'new')
    assert 'messages' not in state and 'market' not in state and 'filters_tickers' not in state


def test_ticker_only_and_csv_compatibility():
    raw = manual_watchlist('aapl, MSFT aapl')
    assert raw.ticker.tolist() == ['AAPL', 'MSFT']
    d, _ = normalize(raw, detect_mapping(raw), percentage_units={})
    assert d.shares.isna().all()
    path = Path('warren_buffett_historical_buys_sells.csv')
    if path.exists():
        raw = read_csv(path.read_bytes())
        d, parse_issues = normalize(raw, detect_mapping(raw), percentage_units={k: 'Percentage points' for k in ['weight', 'share_change_pct', 'portfolio_change_pct']})
        assert len(d) == len(raw)
        assert not parse_issues
        assert d.date.notna().all()
        assert not activity_summary(d)['events'].empty


def test_top_rankings_denominators_missing_basis_and_latest_period():
    from utils.analytics import top_holdings, reported_top_holdings
    positions = pd.DataFrame({'ticker': [f'T{i:02}' for i in range(12)], 'currency': ['USD'] * 12,
                              'position_value': [100] * 12, 'allocation_pct': [100 / 12] * 12,
                              'unrealized_gain_loss': [10] * 11 + [float('nan')]})
    result = top_holdings(positions)
    assert len(result['value']) == len(result['profit']) == 10
    assert result['profit'].profit_share_pct.sum() == pytest.approx(1000 / 11)
    assert result['missing_basis'] == 1
    positions['unrealized_gain_loss'] = -1
    assert top_holdings(positions)['profit'].empty
    d = normalized([dict(ticker='OLD', period='2024 Q1', portfolio_pct=90),
                    dict(ticker='NEW', period='2024 Q2', portfolio_pct=5)])
    assert reported_top_holdings(d).ticker.tolist() == ['OLD', 'NEW']


def test_reported_ranking_uses_latest_record_without_resurrecting_exits():
    from utils.analytics import reported_top_holdings
    d = normalized([
        dict(ticker='AAPL', period='2024 Q1', portfolio_pct=40),
        dict(ticker='AAPL', period='2025 Q4', portfolio_pct=22.6),
        dict(ticker='GOOGL', period='2026 Q2', portfolio_pct=9.41),
        dict(ticker='EXIT', period='2024 Q1', portfolio_pct=50),
        dict(ticker='EXIT', period='2025 Q1', action='sold_out', portfolio_pct=0),
        dict(ticker='MISSING', period='2024 Q1', portfolio_pct=60),
        dict(ticker='MISSING', period='2025 Q1', portfolio_pct=''),
    ])
    ranked = reported_top_holdings(d)
    assert ranked.ticker.tolist() == ['AAPL', 'GOOGL']
    assert ranked.iloc[0].weight == 22.6
    assert ranked.iloc[0].date == pd.Timestamp('2025-12-31')


def test_heatmap_readable_window_and_action_details():
    from utils.analytics import activity_heatmap_data
    events = pd.DataFrame([
        dict(ticker='AAPL', period=f'{year}Q1', action='add') for year in range(2010, 2026)
    ] + [dict(ticker='MSFT', period='2025Q1', action='reduce')])
    counts, details = activity_heatmap_data(events, '2025Q1', row_limit=15)
    assert counts.shape == (2, 12)
    assert counts.columns[0] == '2014Q1'
    assert details.loc['MSFT', '2025Q1'] == 'reduce: 1'
    assert 'No event reported' in details.loc['MSFT', '2014Q1']
    old, _ = activity_heatmap_data(events, '2012Q1', row_limit=1)
    assert old.columns.tolist() == ['2010Q1', '2011Q1', '2012Q1']


def test_yearly_heatmap_aggregates_quarters_without_losing_action_counts():
    from utils.analytics import activity_heatmap_data
    data = normalized([
        dict(ticker='AAPL', period='2024 Q1', action='initial_disclosure'),
        dict(ticker='AAPL', period='2024 Q2', action='add'),
        dict(ticker='AAPL', period='2024 Q3', action='add'),
        dict(ticker='AAPL', period='2024 Q4', action='reduce'),
        dict(ticker='AAPL', period='2025 Q1', action='reduce'),
    ])
    annual = activity_summary(data, 'Y')['events']
    counts, details = activity_heatmap_data(annual, '2025')
    assert counts.loc['AAPL'].tolist() == [4, 1]
    assert 'add: 2' in details.loc['AAPL', '2024']
    assert 'initial disclosure: 1' in details.loc['AAPL', '2024']
    quarterly = activity_summary(data, 'Q')['events']
    quarterly_counts, _ = activity_heatmap_data(quarterly, '2025Q1')
    assert quarterly_counts.loc['AAPL'].tolist() == [1, 1, 1, 1, 1]


def test_directional_heatmap_preserves_both_sides_and_excludes_disclosures():
    from utils.analytics import directional_heatmap_data
    events = pd.DataFrame([dict(ticker='AAPL', period='2024', action=a)
                           for a in ['initial_disclosure', 'add', 'new_position', 'reduce', 'sold_out']])
    counts, details, labels = directional_heatmap_data(events, '2024')
    assert counts.index.tolist() == ['AAPL']
    assert counts.loc['AAPL', '2024'] == 0
    assert labels.loc['AAPL', '2024'] == '↑2  ↓2'
    assert 'initial disclosure' not in str(details)
    assert 'sold out: 1' in details.loc['AAPL', '2024']

    events = pd.concat([events, pd.DataFrame([dict(ticker='AAPL', period='2025', action='add'), dict(ticker='MSFT', period='2025', action='reduce')])], ignore_index=True)
    counts, details, labels = directional_heatmap_data(events, '2025')
    assert counts.loc['AAPL', '2025'] == 1
    assert counts.loc['MSFT', '2025'] == -1
    assert labels.loc['MSFT', '2024'] == ''


def test_bubble_analysis_compresses_extremes_and_preserves_original_values():
    from utils.analytics import bubble_activity_analysis
    data = normalized([
        dict(ticker='SMALL', period='2024 Q1', action='add', shares_change_pct=90000, portfolio_pct=.1),
        dict(ticker='LARGE', period='2024 Q2', action='reduce', shares_change_pct=-25, portfolio_pct=40),
        dict(ticker='ZERO', period='2024 Q2', action='add', shares_change_pct=0, portfolio_pct=0),
        dict(ticker='MISSING', period='2024 Q2', action='add', portfolio_pct=2),
    ])
    result = bubble_activity_analysis(data)
    points = result['points'].set_index('ticker')
    assert points.loc['SMALL', 'share_change_pct'] == 90000
    assert points.loc['SMALL', 'change_axis'] == pytest.approx(np.log10(90001))
    assert points.loc['LARGE', 'change_axis'] < 0
    assert points.loc['ZERO', 'change_axis'] == 0
    assert points.loc['ZERO', 'bubble_area'] > 0
    assert result['omitted'] == 1
    assert 'SMALL' in result['insights'][0] and 'LARGE' in result['insights'][1]




def test_market_progress_counts_failures_and_cached_requests():
    clear_cache()
    progress = []
    def fetch(symbol, start, end):
        if symbol == 'BAD':
            raise ValueError('Unavailable')
        return {'ticker': symbol}, pd.Series([100], name=symbol), 'Adjusted'
    get_market_data(['A', 'BAD', 'A'], '2024-01-01', '2024-02-01', fetch,
                    progress_callback=lambda done, total: progress.append((done, total)))
    assert progress == [(0, 2), (1, 2), (2, 2)]
    progress.clear()
    get_market_data(['A'], '2024-01-01', '2024-02-01', fetch,
                    progress_callback=lambda done, total: progress.append((done, total)))
    assert progress == [(0, 1), (1, 1)]
