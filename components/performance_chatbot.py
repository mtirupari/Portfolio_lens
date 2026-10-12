import hashlib
import json
import plotly.express as px
import streamlit as st
from utils.analytics import security_performance, portfolio_return_requirements
from utils.chatbot import build_context, ask_local


def render(data, dataset_type, market, valuation, filters):
    st.subheader('Performance, risk & research assistant')
    performance = None
    if data is None or data.empty:
        st.info('Apply a dataset and filters to enable performance research and grounded chat.')
        return
    if market is not None and not market['history'].empty:
        adjustments = set(market['adjustments'].get(c) for c in market['history'].columns)
        if len(adjustments) > 1:
            st.warning('Price histories have inconsistent adjustment methods. Comparison is disabled; retry with compatible securities.')
        elif filters['benchmark'] not in market['history']:
            st.warning('Benchmark history is unavailable. Choose another benchmark or retry before comparing returns.')
        else:
            performance = security_performance(market['history'])
            st.caption('Security returns only. Adjustment: ' + ', '.join(str(x) for x in adjustments))
            st.caption(performance['note'])
            if not performance['metrics'].empty:
                st.dataframe(performance['metrics'])
                st.plotly_chart(px.line(performance['cumulative'], labels={'value': 'Compounded return (%)', 'index': 'Date', 'variable': 'Ticker'}, title='Security and benchmark comparison'), use_container_width=True)
                st.download_button('Download security risk metrics', performance['metrics'].to_csv(), 'security_risk.csv', 'text/csv')
    else:
        st.info('Fetch market data from the CSV Upload tab to compare security returns and risk.')
    st.write('Actual portfolio returns are unavailable for this input.')
    with st.expander('Why portfolio returns need more data'):
        st.write('Security prices and historical activity alone do not measure account performance. This app does not calculate time-weighted or money-weighted portfolio returns. Required inputs:')
        for requirement in portfolio_return_requirements():
            st.write('• ' + requirement)
    st.divider()
    st.subheader('Ask about your data')
    st.caption('Local CSV assistant · no API key required. Answers use your validated data and active filters; chat sends no data to external services. Supports common portfolio questions, not unrestricted AI conversation.')
    context = build_context(data, dataset_type, filters, valuation, performance, market)
    signature = hashlib.sha256((st.session_state.dataset_id + json.dumps(context, default=str, sort_keys=True)).encode()).hexdigest()
    if st.session_state.get('context_key') != signature:
        st.session_state.messages = []
        st.session_state.pop('chat_error', None)
        st.session_state.context_key = signature
    messages = st.session_state.setdefault('messages', [])
    if st.button('Clear chat'):
        st.session_state.messages = []
        st.session_state.pop('chat_error', None)
        st.rerun()
    starter = st.selectbox('Starter question', ['Which stocks were increased most?', 'What changed in the latest quarter?', 'Which holdings dominate the portfolio?', 'Why can’t returns be calculated from this file?'])
    question = starter if st.button('Ask starter question') else None
    for message in messages:
        with st.chat_message(message['role']):
            st.write(message['content'])
    entered = st.chat_input('Ask about the active data and charts', max_chars=4000)
    question = entered or question
    if question:
        with st.spinner('Reviewing the selected data…'):
            result = ask_local(question, messages, data, dataset_type, filters, valuation, performance)
        if result['ok']:
            st.session_state.messages += [{'role': 'user', 'content': question}, {'role': 'assistant', 'content': result['message']}]
            st.session_state.pop('chat_error', None)
        else:
            st.session_state.chat_error = {'message': result['message'], 'question': question}
        st.rerun()
