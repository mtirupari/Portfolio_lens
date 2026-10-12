"""Upload and column selection only; imports update automatically."""
from hashlib import sha256
import pandas as pd
import streamlit as st
from utils.data_loader import read_csv, prepare_upload
from utils.state import activate, invalidate


def render():
    uploaded = st.file_uploader('Upload CSV', type=['csv'])
    payload = uploaded.getvalue() if uploaded is not None else None
    token = sha256(payload).hexdigest() if payload is not None else None
    if st.session_state.get('source_token') != token:
        invalidate(st.session_state, clear_dataset=True)
        st.session_state.pop('raw', None)
        st.session_state.pop('import_selection', None)
        st.session_state.source_token = token
    if payload is None:
        return
    try:
        raw = read_csv(payload)
    except (ValueError, UnicodeError, pd.errors.ParserError) as exc:
        st.error(str(exc))
        return
    selected = st.multiselect('Columns', list(raw.columns), default=list(raw.columns), key=f'columns_{token}')
    signature = sha256((token + repr(selected)).encode()).hexdigest()
    if st.session_state.get('import_selection') == signature:
        return
    data, issues, dataset_type = prepare_upload(raw, selected)
    activate(st.session_state, data, data.copy(), issues, dataset_type, signature)
    st.session_state.raw = raw.copy()
    st.session_state.basis_type = 'Per share'
    st.session_state.import_selection = signature
    if issues.severity.eq('error').any():
        # Keep the full normalized source for review; do not silently discard bad rows.
        st.session_state.pop('data', None)
