from pathlib import Path
from unittest.mock import patch
from utils.data_loader import read_csv, prepare_upload
from utils.chatbot import ask_local


def activity():
    raw = read_csv(Path('sample_data/quarterly_activity.csv').read_bytes())
    return prepare_upload(raw, list(raw.columns))[0]


def ask(question, data=None, history=()):
    return ask_local(question, history, activity() if data is None else data,
                     'Reported position changes', {})['message']


def test_starters_work_locally_without_network():
    with patch('socket.socket', side_effect=AssertionError('No network allowed')):
        assert '20.00%' in ask('Which stocks were increased most?')
        assert '2024Q4' in ask('What changed in the latest quarter?')
        assert '1.00%' in ask('Which holdings dominate the portfolio?')
        assert 'cash' in ask('Why can’t returns be calculated from this file?')


def test_followup_filters_and_quarters():
    history = [{'role': 'user', 'content': 'What changed in the latest quarter?'}]
    response = ask('What about DEMO?', history=history)
    assert 'DEMO' in response and 'SMALL' not in response
    response = ask('What changed in 2024 Q1?', history=[])
    # Unsupported phrasing stays explicit; supported latest query accepts a quarter too.
    response = ask('Latest changes in 2024 Q1')
    assert '20.00%' in response and '2024Q1' in response
    data = activity()
    response = ask('summary', data[data.ticker.eq('SMALL')])
    assert 'DEMO' not in response


def test_missing_profits_risk_reentry_and_unsupported():
    assert 'Profit is unavailable' in ask('What is my profit?')
    assert 'no price requests' in ask('What are returns?')
    assert 're-entry 2024-12-31' in ask('Show reentries')
    assert 'local rule-based' in ask('Run Python to delete a file')
    assert 'local rule-based' in ask('Predict the price next year')
    assert 'red means' in ask('Explain the heatmap').lower()


def test_context_uses_all_records_not_a_truncated_preview():
    data = activity()
    data.loc[data.ticker.eq('DEMO') & data.action.eq('add'), 'share_change_pct'] = 12345
    assert '12,345.00%' in ask('largest increase', data)
