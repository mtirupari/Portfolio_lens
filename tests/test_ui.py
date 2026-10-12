"""UI checks for the upload-only flow, with mocked file bytes and providers."""
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
import pandas as pd
from streamlit.testing.v1 import AppTest


def widget(elements, label):
    return next(e for e in elements if e.label == label)


def app():
    return AppTest.from_file(Path(__file__).resolve().parents[1] / 'main.py')


def upload(name):
    return patch('streamlit.file_uploader', return_value=BytesIO(Path(f'sample_data/{name}.csv').read_bytes()))


def fake_market(*args, **kwargs):
    return {'quotes': pd.DataFrame([
        dict(ticker='AAPL', market_price=100, quote_currency='USD', sector='Technology', provider='Mock Yahoo', timestamp='2024-01-03'),
        dict(ticker='MSFT', market_price=200, quote_currency='USD', sector='Technology', provider='Mock Yahoo', timestamp='2024-01-03')]),
        'history': pd.DataFrame({'AAPL': [100, 120, 90], 'MSFT': [100, 110, 105], 'SPY': [100, 101, 102]}, index=pd.date_range('2024-01-01', periods=3)),
        'failures': {}, 'adjustments': {s: 'Yahoo adjusted close (splits/dividends)' for s in ['AAPL', 'MSFT', 'SPY']}}



def test_empty_and_exact_four_tabs():
    at = app().run(timeout=20)
    assert not at.exception and len(at.tabs) == 4
    tab = at.tabs[0]
    assert len(tab.get('file_uploader')) == 1
    assert len(tab.button) == 1 and tab.button[0].label == 'Fetch / refresh market data'
    assert not tab.selectbox and not tab.radio and not tab.expander


def test_upload_has_only_column_selection_and_auto_import():
    with upload('current_holdings'):
        at = app().run(timeout=20)
        tab = at.tabs[0]
        assert len(tab.multiselect) == 1 and tab.multiselect[0].label == 'Columns'
        assert len(tab.button) == 1 and tab.button[0].label == 'Fetch / refresh market data'
        assert not tab.selectbox and not tab.radio and not tab.expander
        assert not tab.dataframe
        assert at.session_state['data'].shares.tolist() == [10, 5]
        with patch('utils.market_data.get_market_data', fake_market):
            widget(at.button, 'Fetch / refresh market data').click().run(timeout=20)
        assert not at.exception
        assert any(m.value == '2,000.00' for m in at.metric)
        widget(at.multiselect, 'Columns').set_value(['ticker']).run()
        assert at.session_state['data'].shares.isna().all()
        assert 'market' not in at.session_state
        widget(at.multiselect, 'Columns').set_value([]).run()
        assert not at.exception


def test_activity_remains_activity_when_action_deselected():
    with upload('quarterly_activity'):
        at = app().run(timeout=20)
        assert not at.exception
        assert at.session_state['dataset_type'] == 'Reported position changes'
        assert any(m.label == 'Initial Disclosure' and m.value == '1' for m in at.metric)
        widget(at.multiselect, 'Columns').set_value(['ticker', 'shares_held_after']).run()
        assert not at.exception
        assert at.session_state['dataset_type'] == 'Reported position changes'
    with upload('watchlist'):
        at.run()
        assert at.session_state['data'].shares.isna().all()
    with patch('streamlit.file_uploader', return_value=None):
        at.run()
        assert 'data' not in at.session_state
        assert not at.exception


def test_dated_holdings_and_provider_failure():
    with upload('historical_snapshots'):
        at = app().run(timeout=20)
        assert at.session_state['dataset_type'] == 'Dated holdings'
        failure = {'quotes': pd.DataFrame(), 'history': pd.DataFrame(), 'failures': {'AAPL': 'No data available.'}, 'adjustments': {}}
        with patch('utils.market_data.get_market_data', return_value=failure):
            widget(at.button, 'Fetch / refresh market data').click().run(timeout=20)
        assert not at.exception
        assert not any('No data available' in element.value
                       for elements in [at.warning, at.error, at.info, at.caption]
                       for element in elements)
        assert any('Coverage:' in element.value for element in at.caption)


def test_bad_csv_blocks_analysis_without_discarding_rows():
    with patch('streamlit.file_uploader', return_value=BytesIO(b'ticker,shares\nAAPL,oops\n')):
        at = app().run(timeout=20)
        assert not at.exception
        assert 'data' not in at.session_state
        assert len(at.session_state['normalized']) == 1
        assert at.session_state['issues'].severity.eq('error').any()


def test_history_window_defaults_to_csv_and_accepts_custom_older_dates():
    from datetime import date
    csv = b'ticker,date,shares\nAAPL,2013 Q2,10\nAAPL,2026 Q2,12\n'
    with patch('streamlit.file_uploader', return_value=BytesIO(csv)):
        at = app().run(timeout=20)
        assert widget(at.date_input, 'Price-history start').value == date(2013, 6, 30)
        assert widget(at.date_input, 'Price-history end').value == date(2026, 6, 30)
        widget(at.date_input, 'Price-history start').set_value(date(2010, 1, 1)).run()
        widget(at.date_input, 'Price-history end').set_value(date(2014, 12, 31)).run()
        with patch('utils.market_data.get_market_data', side_effect=fake_market) as provider:
            widget(at.button, 'Fetch / refresh market data').click().run(timeout=20)
        assert not at.exception
        assert provider.call_args.args[1:] == (date(2010, 1, 1), date(2015, 1, 1))
        widget(at.radio, 'Show').set_value('Choose specific tickers').run()
        assert widget(at.date_input, 'Price-history start').value == date(2010, 1, 1)
        widget(at.date_input, 'Price-history start').set_value(date(2016, 1, 1)).run()
        with patch('utils.market_data.get_market_data') as provider:
            widget(at.button, 'Fetch / refresh market data').click().run()
        provider.assert_not_called()
        assert any('valid price-history' in e.value for e in at.error)
    with upload('historical_snapshots'):
        at.run()
        assert widget(at.date_input, 'Price-history start').value == date(2024, 3, 31)


def test_local_chat_enabled_without_credentials_and_clears():
    with upload('quarterly_activity'):
        at = app().run(timeout=20)
        assert not widget(at.button, 'Ask starter question').disabled
        widget(at.button, 'Ask starter question').click().run(timeout=20)
        assert not at.exception
        assert '20.00%' in at.session_state['messages'][-1]['content']
        widget(at.button, 'Clear chat').click().run()
        assert at.session_state['messages'] == []
