import pandas as pd
import plotly.express as px
import streamlit as st
from utils.analytics import positions_for_valuation, value_positions, top_holdings, reported_top_holdings


def ranking_chart(frame, metric, title, color, percentage=False):
    """Horizontal rankings with direct labels and portfolio context on hover."""
    ordered = frame.sort_values([metric, 'ticker'], ascending=[True, False]).copy()
    labels = {'weight': 'Reported portfolio share (%)', 'position_value': 'Holding value',
              'allocation_pct': 'Covered portfolio share (%)', 'profit_share_pct': 'Share of positive profits (%)',
              'unrealized_gain_loss': 'Unrealized profit', 'ticker': 'Ticker', 'company': 'Company',
              'date': 'Observed on', 'currency': 'Currency', 'value': 'Reported value'}
    hover = {c: ':.2f' for c in ['allocation_pct', 'profit_share_pct'] if c in ordered}
    hover.update({c: True for c in ['company', 'date', 'currency', 'value'] if c in ordered})
    fig = px.bar(ordered, x=metric, y='ticker', orientation='h', text=metric,
                 hover_data=hover, labels=labels, title=title, color_discrete_sequence=[color])
    fig.update_traces(texttemplate='%{x:.2f}%' if percentage else '%{x:,.2f}',
                      textposition='outside', cliponaxis=False, marker_line_width=0,
                      width=.62)
    fig.update_layout(height=max(300, 44 * len(ordered) + 100), showlegend=False,
                      paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                      margin=dict(l=10, r=90, t=60, b=35), font=dict(size=16),
                      title_font=dict(size=24), bargap=.3)
    fig.update_yaxes(title=None, showgrid=False, categoryorder='array', categoryarray=ordered.ticker.tolist())
    fig.update_xaxes(showgrid=True, gridcolor='#E8EDF2', zeroline=False,
                     rangemode='tozero', ticksuffix='%' if percentage else '')
    return fig


def render(data, dataset_type, market):
    st.subheader('Prices & portfolio overview')
    if data is None or data.empty:
        st.info('Upload a CSV, then choose your tickers in the sidebar.')
        return None
    reported = reported_top_holdings(data)
    if not reported.empty:
        st.subheader('Top 10 by latest reported share across quarters')
        st.caption('Uses each ticker’s latest record across all selected quarters; hover to see its observation date. Dates may differ, so these historical weights are not a current portfolio allocation and are not added or renormalized. Latest reported exits are excluded; missing or ambiguous latest weights remain unavailable.')
        st.plotly_chart(ranking_chart(reported, 'weight', 'Latest reported weight per ticker · mixed observation dates', '#087F8C', percentage=True), use_container_width=True)
    if market is None:
        st.info('Select “Fetch / refresh market data” in the CSV Upload tab to load Yahoo prices. Tickers and the selected date range will be sent to Yahoo Finance.')
        return None
    quotes = market['quotes']
    if not quotes.empty:
        st.caption('Latest available daily closes, which may be delayed. Quote timestamps refer to the provider’s daily bars. Requests are cached for five minutes; refresh forces a new request.')
        with st.expander('Price details'):
            st.dataframe(quotes, hide_index=True)
    history = market['history']
    if not history.empty:
        st.plotly_chart(px.line(history, labels={'value': 'Price (native currency)', 'index': 'Date', 'variable': 'Ticker'}, title='Historical prices'), use_container_width=True)
        st.caption('Native-currency levels are not directly comparable across currencies. Adjustments: ' + '; '.join(f'{s}: {a}' for s, a in market['adjustments'].items()))
    positions, note = positions_for_valuation(data, dataset_type)
    st.info(note)
    if positions.empty or not positions.shares.notna().any():
        st.caption('Current value and profit rankings are unavailable: supplied current or dated holding quantities and valid cost basis are needed. Reported activity alone cannot establish them.')
        return None
    with st.expander('Confirmed company grouping (optional)'):
        grouping_text = st.text_area('One ticker=company identifier per line', key='company_grouping',
                                    placeholder='GOOG=Alphabet\nGOOGL=Alphabet')
        confirmed = st.checkbox('I confirm that these securities belong to the same listed companies', key='confirm_groups')
    groups = {}
    if confirmed:
        for line in grouping_text.splitlines():
            if '=' in line:
                ticker, company = line.split('=', 1)
                if company.strip():
                    groups[ticker.strip().upper()] = company.strip()
    result = value_positions(positions, quotes, st.session_state.get('basis_type', 'Per share'), groups)
    holdings = result['positions']
    for total in result['totals'].itertuples():
        st.metric(f'{total.currency} · {total.label}', f'{total.covered_value:,.2f}' if pd.notna(total.covered_value) else 'Unavailable')
        st.caption(f'{total.priced_positions}/{total.supplied_positions} supplied positions priced. Allocation weights use only covered value in this currency; filtered scope applies.')
        subset = holdings[holdings.currency.eq(total.currency) & holdings.position_value.gt(0)]
        if not subset.empty:
            st.plotly_chart(px.pie(subset, names='ticker', values='position_value', title=f'{total.currency} covered allocation', hole=.55), use_container_width=True)
            rankings = top_holdings(subset)
            left, right = st.columns(2)
            with left:
                st.subheader(f'Top 10 by value · {total.currency}')
                st.caption('Portfolio share is based on all covered value in this currency and active filter scope, not just the top 10.')
                ranked = rankings['value']
                st.plotly_chart(ranking_chart(ranked, 'allocation_pct', f'Portfolio share by value · {total.currency}', '#087F8C', percentage=True), use_container_width=True)
                st.plotly_chart(ranking_chart(ranked, 'position_value', f'Holding value · {total.currency}', '#5967BA'), use_container_width=True)
            with right:
                st.subheader(f'Top 10 by unrealized profit · {total.currency}')
                ranked = rankings['profit']
                if ranked.empty:
                    st.info('No positive unrealized profits available. A valid cost basis and priced holding are required; missing profits are not treated as zero.')
                else:
                    st.plotly_chart(ranking_chart(ranked, 'profit_share_pct', f'Share of positive profits · {total.currency}', '#199C78', percentage=True), use_container_width=True)
                    st.plotly_chart(ranking_chart(ranked, 'unrealized_gain_loss', f'Unrealized profit · {total.currency}', '#23866E'), use_container_width=True)
                st.caption(f'Profit share uses all positive unrealized gains with known basis in this currency and filter scope. {rankings["missing_basis"]} holdings lack basis; {rankings["losses"]} loss-making holdings are excluded from this profit ranking and remain in the holdings table. These are not realized profits or portfolio returns.')

            sectors = subset.assign(sector=subset.sector.fillna('Unclassified')).groupby('sector').position_value.sum().reset_index()
            if subset.sector.notna().any():
                st.plotly_chart(px.bar(sectors, x='sector', y='position_value', title=f'{total.currency} sector exposure'), use_container_width=True)
            if confirmed and groups:
                st.dataframe(subset.groupby('company_group').position_value.sum().sort_values(ascending=False).rename(f'{total.currency} company exposure'))
    if result['uncovered']:
        st.caption(f'Coverage: totals include priced, unambiguous positions only; {result["uncovered"]} positions are not included. No FX conversion is assumed.')
    st.caption(f'Cost basis is interpreted as {st.session_state.get("basis_type", "Per share").lower()} in the position currency. Gain/loss requires a valid basis and a covered valuation.')
    with st.expander('Holdings details'):
        st.dataframe(holdings, hide_index=True)
    st.download_button('Download covered valuation and source fields', holdings.to_csv(index=False), 'filtered_valuation.csv', 'text/csv')
    return result
