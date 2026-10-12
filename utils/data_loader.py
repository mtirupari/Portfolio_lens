"""Lossless source preview and explicit, conservative CSV normalization."""
from io import BytesIO
import re
import pandas as pd

DATASET_TYPES = ['Current holdings', 'Complete historical snapshots', 'Reported position changes']
ALIASES = {
    'ticker': ['ticker', 'symbol', 'stock_symbol'],
    'company': ['company', 'company_name', 'name'],
    'date': ['date', 'period', 'quarter', 'as_of', 'transaction_date'],
    'action': ['action', 'activity', 'transaction_type'],
    'shares': ['shares', 'quantity', 'shares_held', 'shares_held_after'],
    'price': ['price', 'reported_price_usd', 'share_price'],
    'value': ['value', 'market_value', 'reported_value_usd'],
    'weight': ['weight', 'portfolio_pct', 'portfolio_weight'],
    'share_change': ['share_change', 'shares_change'],
    'share_change_pct': ['share_change_pct', 'shares_change_pct'],
    'portfolio_change_pct': ['portfolio_change_pct'],
    'cost_basis': ['cost_basis', 'purchase_cost', 'average_cost'],
    'currency': ['currency', 'currency_code'],
    'source_url': ['source_url', 'source'],
    'retrieved_date': ['retrieved_date', 'retrieval_date'],
    'activity_raw': ['activity_raw'], 'locked_fields': ['locked_fields'],
}
NUMERIC = ['shares', 'price', 'value', 'weight', 'share_change', 'share_change_pct', 'portfolio_change_pct', 'cost_basis']
PERCENT = ['weight', 'share_change_pct', 'portfolio_change_pct']
ACTIONS = {
    'add': 'add', 'addition': 'add', 'increase': 'add', 'buy': 'add',
    'reduce': 'reduce', 'reduction': 'reduce', 'decrease': 'reduce', 'sell': 'reduce',
    'new_position': 'new_position', 'new position': 'new_position', 'new': 'new_position',
    'sold_out': 'sold_out', 'sold out': 'sold_out', 'exit': 'sold_out',
    'initial_disclosure': 'initial_disclosure', 'initial disclosure': 'initial_disclosure',
    'new or own*': 'initial_disclosure',
}


def read_csv(content: bytes) -> pd.DataFrame:
    frame = pd.read_csv(BytesIO(content), dtype=str, keep_default_na=False, encoding='utf-8-sig')
    if frame.empty:
        raise ValueError('The CSV has no data rows.')
    if len(frame) > 100_000:
        raise ValueError('Please use a CSV with at most 100,000 rows.')
    return frame


def detect_mapping(frame):
    columns = {str(c).strip().lower().replace(' ', '_'): c for c in frame.columns}
    return {field: next((columns[a] for a in aliases if a in columns), None)
            for field, aliases in ALIASES.items()}


def parse_date(value, dayfirst=False):
    value = str(value).strip()
    match = re.fullmatch(r'(\d{4})\s*[-/]?\s*Q([1-4])', value, re.I)
    if match:
        return pd.Period(f'{match[1]}Q{match[2]}', freq='Q').end_time.normalize()
    if not value:
        return pd.NaT
    return pd.to_datetime(value, errors='coerce', dayfirst=dayfirst)


def number(value):
    text = str(value).strip().replace(',', '').replace('%', '')
    if text.startswith('(') and text.endswith(')'):
        text = '-' + text[1:-1]
    return pd.to_numeric(text, errors='coerce')


def normalize(frame, mapping, *, percentage_units, currency='USD', dayfirst=False, action_map=None):
    selected = [v for v in mapping.values() if v]
    if len(selected) != len(set(selected)):
        raise ValueError('Each source column can be mapped to only one field.')
    if any(c not in frame.columns for c in selected):
        raise ValueError('A mapped column is not present in this CSV.')
    out = pd.DataFrame(index=frame.index)
    out['source_row'] = range(2, len(frame) + 2)
    issues = []
    for field in ALIASES:
        col = mapping.get(field)
        out[field] = frame[col].astype(str).str.strip() if col else ''
    out['action_original'] = out['action']
    out['date_original'] = out['date']
    for field in NUMERIC:
        original = out[field].copy()
        out[field] = original.map(number)
        for idx in out.index[original.ne('') & out[field].isna()]:
            issues.append({'source_row': int(out.at[idx, 'source_row']), 'severity': 'error',
                           'field': field, 'message': f'Cannot parse number: {original.at[idx][:80]}'})
        if field in PERCENT and original.ne('').any():
            unit = percentage_units.get(field)
            if unit not in ('Percentage points', 'Fractions'):
                raise ValueError(f'Choose percentage units for {field}.')
            # Explicit percent suffix always denotes percentage points.
            if unit == 'Fractions':
                out.loc[~original.str.contains('%', regex=False), field] *= 100
    out['ticker'] = out['ticker'].str.upper()
    out['currency'] = out['currency'].replace('', currency).str.upper()
    out['date'] = out['date'].map(lambda v: parse_date(v, dayfirst))
    for idx in out.index[out['date_original'].ne('') & out['date'].isna()]:
        issues.append({'source_row': int(out.at[idx, 'source_row']), 'severity': 'error',
                       'field': 'date', 'message': 'Unrecognized date/period.'})
    labels = dict(ACTIONS)
    labels.update({str(k).strip().lower(): v for k, v in (action_map or {}).items()})
    out['action'] = out['action_original'].str.lower().map(labels).fillna('unknown')
    return out, issues


def manual_watchlist(text):
    symbols = list(dict.fromkeys(x.upper() for x in re.split(r'[,\s]+', text.strip()) if x))
    if not symbols or len(symbols) > 100:
        raise ValueError('Enter between 1 and 100 tickers, separated by commas or spaces.')
    if any(not re.fullmatch(r'[A-Z0-9.^=\-]{1,30}', x) for x in symbols):
        raise ValueError('A ticker contains unsupported characters.')
    return pd.DataFrame({'ticker': symbols})


def prepare_upload(raw, selected):
    """Infer conservatively from the source schema, even if columns are deselected."""
    from utils.validation import validate
    original_mapping = detect_mapping(raw)
    if original_mapping['action']:
        dataset_type = 'Reported position changes'
    elif original_mapping['date']:
        dataset_type = 'Dated holdings'
    else:
        dataset_type = 'Current holdings'
    mapping = detect_mapping(raw[selected])
    data, parsing_issues = normalize(raw, mapping,
                                     percentage_units={field: 'Percentage points' for field in PERCENT})
    # Generic bare weights do not establish a unit convention. Keep explicit %
    # values but leave ambiguous observations unavailable instead of guessing.
    for field in PERCENT:
        column = mapping.get(field)
        if column and not any(part in column.lower() for part in ['pct', 'percent']):
            values = raw[column].astype(str).str.strip()
            ambiguous = values.ne('') & ~values.str.endswith('%')
            data.loc[ambiguous, field] = float('nan')
            for row in data.loc[ambiguous, 'source_row']:
                parsing_issues.append(dict(source_row=int(row), severity='warning', field=field,
                                           message='Ambiguous percentage omitted from calculations. Use a % suffix or a _pct column with percentage-point values.'))
    return data, validate(data, dataset_type, parsing_issues), dataset_type
