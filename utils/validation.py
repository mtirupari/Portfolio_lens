"""Row-level validation without silently changing or removing records."""
import pandas as pd
import numpy as np
from utils.data_loader import NUMERIC

ISSUE_COLUMNS = ['source_row', 'severity', 'field', 'message']


def validate(data, dataset_type, parsing_issues=()):
    issues = list(parsing_issues)
    def flag(mask, field, message, severity='warning'):
        for row in data.loc[mask, 'source_row']:
            issues.append(dict(source_row=int(row), severity=severity, field=field, message=message))
    flag(data.ticker.eq(''), 'ticker', 'Missing ticker; market research unavailable for this row.')
    flag(~data.ticker.str.fullmatch(r'[A-Z0-9.^=\-]{1,30}') & data.ticker.ne(''),
         'ticker', 'Invalid ticker format.', 'error')
    for field in NUMERIC:
        flag(data[field].notna() & ~np.isfinite(data[field]), field, 'Infinite numeric values are unsupported.', 'error')
    for field in ['shares', 'price', 'value', 'cost_basis']:
        flag(data[field].lt(0), field, 'Negative amount is unsupported; resolve or exclude this row.', 'error')
    flag(data.weight.lt(0) | data.weight.gt(100), 'weight', 'Weight must be between 0 and 100 percentage points.', 'error')
    if dataset_type != 'Current holdings':
        flag(data.date.isna(), 'date', 'Missing period/date; historical analysis unavailable for this row.')
    if dataset_type == 'Reported position changes':
        flag(data.action.eq('unknown'), 'action', 'Unknown action; excluded from action-specific summaries until mapped.')
        flag(data.action.isin(['add', 'new_position']) & data.share_change.lt(0), 'share_change', 'Addition has negative share change.', 'error')
        flag(data.action.isin(['reduce', 'sold_out']) & data.share_change.gt(0), 'share_change', 'Reduction has positive share change.', 'error')
        flag(data.action.eq('sold_out') & data.shares.gt(0), 'shares', 'Sold-out event has a nonzero ending balance.', 'error')
    expected = data.shares * data.price
    tolerance = expected.abs() * .02 + 1
    flag((expected - data.value).abs().gt(tolerance), 'value', 'Reported value differs from shares × price by over 2% + 1 currency unit.')
    keys = ['ticker'] if dataset_type == 'Current holdings' else ['ticker', 'date']
    duplicates = data.duplicated(keys, keep=False) & data.ticker.ne('')
    flag(duplicates, 'ticker/date', 'Duplicate position candidate. Resolve before valuation; activity rows may describe multiple events.')
    if dataset_type == 'Reported position changes':
        ordered = data.sort_values(['ticker', 'date'])
        previous = ordered.groupby('ticker').shares.shift()
        difference = ordered.shares - previous
        inconsistent = previous.notna() & ordered.share_change.notna() & (difference - ordered.share_change).abs().gt(1)
        for row in ordered.loc[inconsistent, 'source_row']:
            issues.append(dict(source_row=int(row), severity='warning', field='share_change',
                               message='Share history is inconsistent: missing events, splits or other corporate actions may explain it.'))
    return pd.DataFrame(issues, columns=ISSUE_COLUMNS)


def capabilities(data, dataset_type):
    has = lambda col: data[col].notna().any() if col in data else False
    return {
        'Market research': 'Ready' if data.ticker.ne('').any() else 'Needs ticker',
        'Position valuation': 'Ready for supplied quantities' if has('shares') else 'Needs shares/quantity',
        'Historical activity': ('Ready for dated, recognized rows' if
            (data.ticker.ne('') & data.date.notna() & data.action.ne('unknown')).any()
            and dataset_type == 'Reported position changes' else 'Needs activity interpretation, ticker, date and recognized action'),
        'Unrealized gain/loss': 'Needs basis convention; shown only for valid positions' if has('cost_basis') else 'Needs cost basis',
        'Actual portfolio returns': 'Needs portfolio valuation history and dated external cash flows (not supported by this CSV schema)',
    }
