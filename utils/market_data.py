"""Yahoo access with per-symbol isolation and a five-minute process cache."""
from datetime import datetime, timezone
import time
import threading
import pandas as pd

_CACHE = {}
_LOCK = threading.Lock()
TTL_SECONDS = 300


def clear_cache():
    with _LOCK:
        _CACHE.clear()


def _fetch(symbol, start, end):
    import yfinance as yf
    security = yf.Ticker(symbol)
    history = security.history(start=str(start), end=str(end), auto_adjust=False, actions=True, timeout=10)
    recent = security.history(period='5d', auto_adjust=False, actions=False, timeout=10)
    try:
        info = security.get_info() or {}
    except Exception:
        info = {}
    currency = info.get('currency', 'Unknown')
    if recent.empty or 'Close' not in recent:
        raise ValueError('No recent prices')
    close = recent.Close.dropna()
    if close.empty:
        raise ValueError('No recent prices')
    latest = float(close.iloc[-1])
    previous = info.get('regularMarketPreviousClose')
    if previous is None and len(close) > 1:
        previous = float(close.iloc[-2])
    delta = latest - previous if previous else None
    timestamp = close.index[-1].isoformat()
    quote = dict(ticker=symbol, market_price=latest, quote_currency=currency,
                 daily_change=delta, daily_change_pct=delta / previous * 100 if previous and delta is not None else None,
                 timestamp=timestamp, provider='Yahoo Finance via yfinance', sector=info.get('sector'),
                 fetched_at=datetime.now(timezone.utc).isoformat(),
                 freshness='Delayed/end-of-day; observation timestamp shown, not a live quote')
    series = pd.Series(dtype=float, name=symbol)
    adjustment = 'Unavailable'
    if not history.empty:
        column = 'Adj Close' if 'Adj Close' in history and history['Adj Close'].notna().any() else 'Close'
        series = history[column].copy()
        series.index = pd.DatetimeIndex(series.index).tz_localize(None).normalize()
        series = series[~series.index.duplicated(keep='last')]
        series.name = symbol
        adjustment = 'Yahoo adjusted close (splits/dividends)' if column == 'Adj Close' else 'Price-only close'
    return quote, series, adjustment


def get_market_data(tickers, start, end, fetcher=None, progress_callback=None):
    fetcher = fetcher or _fetch
    quotes, histories, failures, adjustments = [], [], {}, {}
    symbols = sorted(set(tickers))
    if progress_callback:
        progress_callback(0, len(symbols))
    for completed, symbol in enumerate(symbols, 1):
        key = (symbol, str(start), str(end))
        try:
            with _LOCK:
                cached = _CACHE.get(key)
            if cached and time.monotonic() - cached[0] < TTL_SECONDS:
                quote, history, adjustment = cached[1]
            else:
                quote, history, adjustment = fetcher(symbol, start, end)
                with _LOCK:
                    _CACHE[key] = (time.monotonic(), (quote, history, adjustment))
            quotes.append(quote)
            if not history.empty:
                histories.append(history)
            adjustments[symbol] = adjustment
        except Exception:
            failures[symbol] = 'No data available. Check the symbol or retry later.'
        if progress_callback:
            progress_callback(completed, len(symbols))
    return {'quotes': pd.DataFrame(quotes), 'history': pd.concat(histories, axis=1) if histories else pd.DataFrame(),
            'failures': failures, 'adjustments': adjustments}
