"""Centered market-data action and honest request-completion progress."""
from datetime import timedelta
import re
import time
import streamlit as st
from utils.market_data import clear_cache


def render(tickers, start, end, benchmark, fetch_market):
    _, center, _ = st.columns([1, 2, 1])
    with center:
        clicked = st.button('Fetch / refresh market data', type='primary', use_container_width=True,
                            icon=':material/sync:', disabled=start is None)
        if not clicked:
            return
        if start >= end:
            st.error('Choose a valid price-history start and end date.')
            return
        if not re.fullmatch(r'[A-Z0-9.^=\-]{1,30}', benchmark):
            st.error('Enter a valid benchmark ticker.')
            return
        if not tickers or len(tickers) > 40:
            st.error('Choose between 1 and 40 tickers to price.')
            return
        progress = st.progress(0, text='0% · Preparing market data')
        def update(completed, total):
            percent = round(completed / total * 100) if total else 100
            progress.progress(percent, text=f'{percent}% · {completed}/{total} symbol requests completed')
        clear_cache()
        result = fetch_market(tickers + [benchmark], start, end + timedelta(days=1), progress_callback=update)
        st.session_state.market = result
        st.session_state.market_loaded_at = time.monotonic()
        progress.progress(100, text='100% · Fetch complete')
        st.caption(f'{len(result["quotes"])} symbols with available prices. Open the analysis tabs to explore. Completion tracks requests, not data coverage.')
