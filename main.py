"""Streamlit entry point: state, shared filters and four tab renderers."""
from datetime import date, timedelta
from pathlib import Path
import base64
import time
import streamlit as st
from dotenv import load_dotenv
from components import csv_upload, portfolio_overview, historical_activity, performance_chatbot, style, market_fetch
from utils.analytics import filter_data
from utils.market_data import get_market_data, TTL_SECONDS
from utils.state import invalidate

load_dotenv()
st.set_page_config(page_title='Portfolio Lens', page_icon='◈', layout='wide')
style.render()
header_icon = base64.b64encode((Path(__file__).parent / 'assets' / 'robot_lens.png').read_bytes()).decode('ascii')
st.html(f'''<div style="display:flex;align-items:center;gap:18px;flex-wrap:wrap">
    <img src="data:image/png;base64,{header_icon}" width="104" height="104"
         alt="Cheerful robot looking through a gold magnifying glass"
         style="object-fit:contain;flex-shrink:0">
    <h1 style="margin:0;padding:0">Portfolio Lens</h1>
</div>''')
st.caption('Your holdings, clearly observed. Explore CSV data, reported activity and market history.')
tabs = st.tabs(['📤 CSV Upload', 'Current Stock Prices and Portfolio Overview',
                'Historical Buys and Sells Analysis', 'Performance, Risk and Chatbot'])
with tabs[0]:
    csv_upload.render()

active = st.session_state.get('data')
filtered, market = None, None
filters = {}
research_symbols, benchmark, market_range = [], "SPY", (None, None)
with st.sidebar:
    st.header('Analysis scope')
    issues = st.session_state.get('issues')
    if issues is not None and not issues.empty:
        with st.expander('CSV validation', expanded=bool(issues.severity.eq('error').any())):
            st.caption('Correct flagged errors in your CSV and upload it again. No records are silently removed.')
            st.dataframe(issues, hide_index=True)
    if active is None:
        st.info('Upload a CSV to begin, or correct the flagged errors.')
    else:
        st.caption('Detected: ' + st.session_state.dataset_type)
        st.caption('Import conventions: missing currency = USD; dates = month first; cost basis = per share; _pct/percent columns = percentage points.')
        symbols = sorted(active.loc[active.ticker.ne(''), 'ticker'].unique())
        ticker_scope = st.radio('Show', ['All tickers', 'Choose specific tickers'], key='ticker_scope')
        if ticker_scope == 'All tickers':
            selected = symbols
        else:
            selected = st.multiselect('Choose tickers', symbols, default=[], key='filters_tickers',
                                      placeholder='Search for AAPL or another ticker')
            if not selected:
                st.info('Choose one or more tickers to view.')
        dates = active.date.dropna()
        start = end = None
        if not dates.empty:
            interval = st.date_input('Observation dates', value=(dates.min().date(), dates.max().date()),
                                     min_value=dates.min().date(), max_value=dates.max().date(), key='filters_dates')
            if len(interval) == 2:
                start, end = interval
            else:
                st.info('Choose both observation dates.')
        filtered = filter_data(active, selected, start, end)
        st.caption(f'{len(filtered):,} matching rows. Date filtering excludes undated rows.')
        st.divider()
        st.subheader('Market research')
        today = date.today()
        default_end = min(dates.max().date(), today) if not dates.empty else today
        default_start = dates.min().date() if not dates.empty else today - timedelta(days=365)
        if default_start >= default_end:
            default_start = default_end - timedelta(days=365)
        earliest = min(date(1900, 1, 1), default_start)
        st.caption('Price-history window · choose any dates, independently of observation filters.')
        history_start = st.date_input('Price-history start', value=default_start,
                                      min_value=earliest, max_value=today, key='market_start')
        history_end = st.date_input('Price-history end', value=default_end,
                                    min_value=earliest, max_value=today, key='market_end')
        market_range = (history_start, history_end)
        benchmark = st.text_input('Benchmark ticker', value='SPY').strip().upper()
        research_symbols = st.multiselect('Tickers to price (up to 40)', selected, default=selected[:10])
        st.caption('Unpriced positions stay visible as uncovered. No automatic currency conversion.')
        filters = dict(tickers=selected, observation_start=str(start), observation_end=str(end),
                       market_window=[str(x) for x in market_range], benchmark=benchmark,
                       priced_tickers=research_symbols, excluded_rows=st.session_state.excluded_count)
        query_key = str((st.session_state.dataset_id, filters))
        if st.session_state.get('query_key') != query_key:
            invalidate(st.session_state)
            st.session_state.query_key = query_key
        if st.session_state.get('market') is not None and time.monotonic() - st.session_state.get('market_loaded_at', 0) > TTL_SECONDS:
            invalidate(st.session_state)
            st.info('Market data expired after five minutes. Refresh to load new observations.')
        market = st.session_state.get('market')
        st.caption('Yahoo Finance via yfinance · five-minute request cache · daily bars, not live quotes')
with tabs[0]:
    market_fetch.render(research_symbols, market_range[0], market_range[1], benchmark, get_market_data)
market = st.session_state.get('market')
with tabs[1]:
    valuation = portfolio_overview.render(filtered, st.session_state.get('dataset_type'), market)
with tabs[2]:
    historical_activity.render(filtered, st.session_state.get('dataset_type'))
with tabs[3]:
    performance_chatbot.render(filtered, st.session_state.get('dataset_type'), market, valuation, filters)
