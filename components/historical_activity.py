import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from utils.analytics import activity_summary, directional_heatmap_data, bubble_activity_analysis


ACTION_COLORS = {'add': '#16A34A', 'new_position': '#86CF9A', 'reduce': '#DC2626',
                 'sold_out': '#F28C8C', 'initial_disclosure': '#94A3B8'}

def render(data, dataset_type):
    st.subheader('Historical buys & sells')
    if data is None or data.empty:
        st.info('Upload dated activity records to explore reported changes.')
        return
    if dataset_type != 'Reported position changes':
        st.info('Select the reported position changes interpretation for action analysis. Holdings snapshots are not transaction records.')
        return
    st.caption('Reported position changes, not individual trades. Initial disclosures are shown separately from purchases. Missing events do not prove no holding or trading.')
    frequency = st.radio('Group events by', ['Quarter', 'Year'], horizontal=True)
    summary = activity_summary(data, 'Q' if frequency == 'Quarter' else 'Y')
    events = summary['events']
    if events.empty:
        st.info('No rows with ticker, valid date and recognized action match the filters.')
        return
    counts = summary['counts']
    total = events.action.value_counts()
    cols = st.columns(5)
    for column, action in zip(cols, ['add', 'reduce', 'new_position', 'sold_out', 'initial_disclosure']):
        column.metric(action.replace('_', ' ').title(), int(total.get(action, 0)))
    st.plotly_chart(px.bar(counts, barmode='stack', color_discrete_map=ACTION_COLORS, labels={'value': 'Reported events', 'period': 'Observed period'}, title='Activity through time'), use_container_width=True)
    st.subheader('Reported activity at a glance')
    heatmap_view = st.radio('Heatmap view', ['Yearly totals', 'Quarterly detail'], horizontal=True)
    heatmap_events = activity_summary(data, 'Y' if heatmap_view == 'Yearly totals' else 'Q')['events']
    controls = st.columns(2)
    periods = sorted(heatmap_events.period.unique())
    ending = controls[0].selectbox('Heatmap ending period', periods, index=len(periods) - 1,
                                  help='Shows up to 12 observed periods ending here. Choose an earlier period to explore history.')
    row_limit = controls[1].selectbox('Stocks to display', [10, 15, 25], index=1)
    heat, descriptions, cell_labels = directional_heatmap_data(heatmap_events, ending, row_limit)
    st.markdown('🔴 **More reductions** &nbsp; → &nbsp; **Balanced** &nbsp; → &nbsp; 🟢 **More additions**')
    if not heat.empty:
        labels = [p.replace('Q', ' · Q') for p in heat.columns]
        maximum = max(1, int(abs(heat.to_numpy()).max()))
        fig = go.Figure(go.Heatmap(
            z=heat.to_numpy(), x=labels, y=heat.index.tolist(),
            text=cell_labels.to_numpy(),
            customdata=descriptions.to_numpy(),
            hovertemplate='<b>%{y}</b> · %{x}<br>Reported events: %{text}<br>%{customdata}<extra></extra>',
            colorscale=[[0, '#B91C1C'], [.24, '#EF7777'], [.49, '#FDE8E8'],
                        [.5, '#F1F5F9'], [.51, '#DCFCE7'], [.76, '#55BE7B'], [1, '#15803D']],
            zmin=-maximum, zmax=maximum, xgap=0, ygap=0, showscale=False,
        ))
        fig.update_layout(height=max(300, len(heat) * 38 + 110),
                          margin=dict(l=10, r=25, t=15, b=60),
                          paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='white',
                          font=dict(size=16, color='#294456'))
        fig.update_xaxes(tickmode='array', tickvals=labels,
                         ticktext=[p.replace(' · ', '<br>') for p in labels],
                         tickangle=0, side='bottom', showgrid=False, zeroline=False, showline=False, ticks='', title=None)
        fig.update_yaxes(tickmode='array', tickvals=heat.index.tolist(),
                         autorange='reversed', showgrid=False, zeroline=False, showline=False, ticks='', title=None)
        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
        if heatmap_view == 'Yearly totals':
            st.caption('Each cell combines the selected quarters in that year. Years may be incomplete because of filters or source coverage.')
        st.caption('↑ = additions/new positions; ↓ = reductions/exits. Color shows additions minus reductions by event count, not shares or money. Equal counts are neutral. Hover to see both counts and the action breakdown.')
        st.caption(f'{len(heat)} most active stocks in this {len(heat.columns)}-period view. Hover for reported-event counts and action details. Neutral cells can mean balanced counts or no reported events; the tooltip distinguishes them. Missing events do not prove no shares were held or traded. Initial disclosures are excluded from this chart because they are not purchases; they remain in the timeline and event table. Only observed periods are shown.')
    else:
        st.info('No additions or reductions are reported in this heatmap window.')
    busiest = counts.sum(axis=1).idxmax()
    buys = int(total.get('add', 0) + total.get('new_position', 0))
    sells = int(total.get('reduce', 0) + total.get('sold_out', 0))
    st.write(f'Busiest observed period: **{busiest}**. Buying-related events: **{buys}**; selling-related events: **{sells}**. These counts are not dollar flows or turnover.')
    st.caption('Period coverage is unverified. Boundary periods can be partial, especially with date filters; absent periods are not filled with zero activity.')
    left, right = st.columns(2)
    with left:
        st.write('Most frequently adjusted securities')
        st.dataframe(summary['frequent'].head(15), hide_index=True)
    with right:
        st.write('Latest observed period')
        latest_period = events.period.max()
        st.dataframe(events[events.period.eq(latest_period)][['ticker', 'date', 'action', 'weight', 'share_change']], hide_index=True)
    st.subheader('Position changes · size and exposure')
    analysis = bubble_activity_analysis(events)
    scatter = analysis['points']
    if not scatter.empty:
        fig = px.scatter(scatter, x='change_axis', y='weight', size='bubble_area', size_max=48,
                         color='action', color_discrete_map=ACTION_COLORS,
                         custom_data=['ticker', 'date', 'share_change_pct', 'weight', 'action'],
                         labels={'change_axis': 'Change in shares (%) · compressed scale',
                                 'weight': 'Ending portfolio weight (%)', 'action': 'Reported action'})
        fig.update_traces(marker=dict(opacity=.65, line=dict(width=1, color='white')),
                          hovertemplate='<b>%{customdata[0]}</b> · %{customdata[4]}<br>Observed: %{customdata[1]|%b %d, %Y}<br>Share change: %{customdata[2]:+,.2f}%<br>Portfolio weight: %{customdata[3]:.2f}%<extra></extra>')
        ticks = [-10000, -1000, -100, -10, 0, 10, 100, 1000, 10000, 100000, 1000000]
        low, high = scatter.change_axis.min(), scatter.change_axis.max()
        ticks = [v for v in ticks if low - .35 <= np.sign(v) * np.log10(1 + abs(v)) <= high + .35 or v == 0]
        fig.update_xaxes(tickvals=[np.sign(v) * np.log10(1 + abs(v)) for v in ticks],
                         ticktext=[f'{v:+,}%' if v else '0%' for v in ticks], showgrid=False, zeroline=False)
        fig.update_yaxes(gridcolor='#E8EDF2', zeroline=False, rangemode='tozero')
        fig.add_vline(x=0, line_dash='dot', line_color='#94A3B8', line_width=1)
        fig.update_layout(height=490, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='#F8FAFC',
                          margin=dict(l=15, r=20, t=50, b=30),
                          legend=dict(orientation='h', y=1.13, x=0, title=None),
                          font=dict(size=16, color='#294456'))
        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
        st.caption('Green = more shares held. Red = fewer shares held. Bigger bubbles = a larger part of the portfolio. Hover over a bubble to see the stock and date.')
        st.write('What this means in simple terms')
        for insight in analysis['insights']:
            title, explanation = insight.split(' — ', 1)
            st.markdown(f'**{title}:** {explanation}')
        st.caption('These takeaways describe the records shown, from different dates—not today’s portfolio or investment profits.')
        with st.expander('How to read the scale and data limits'):
            st.write('The horizontal scale compresses very large changes so smaller ones stay readable. Hover shows the original percentage. Tiny or rounded-zero holdings use a minimum bubble size so they remain visible.')
            st.caption('Horizontal position = sign(x) × log₁₀(1 + |x|), where x is the percentage change in shares.')
            st.caption(f'{analysis["omitted"]} records could not be plotted because the needed values or action type were unavailable. Large percentage increases can start from small holdings. Splits or gaps in reporting can also affect share changes; these figures do not explain why a decision was made.')
    else:
        st.caption('The bubble chart needs both percentage share changes and ending portfolio weights.')
    with st.expander('Starting allocations and maximum observed weights'):
        st.dataframe(events[events.action.eq('new_position')][['ticker', 'date', 'weight']], hide_index=True)
        st.dataframe(summary['max_weights'], hide_index=True)
        st.caption('Weights are dated observations. They can change because of prices and changes elsewhere in the portfolio; a rounded zero weight does not erase a position.')
    ticker = st.selectbox('Security drilldown', sorted(events.ticker.unique()))
    detail = events[events.ticker.eq(ticker)]
    st.dataframe(detail[['date', 'company', 'action_original', 'action', 'shares', 'share_change', 'weight', 'source_url']], hide_index=True)
    if detail.weight.notna().any():
        st.plotly_chart(px.scatter(detail, x='date', y='weight', color='action', color_discrete_map=ACTION_COLORS, title=f'{ticker} observed weight (%)'), use_container_width=True)
    with st.expander('Re-entries, observed durations and repeated actions'):
        for title, key in [('Exits followed by re-entry', 'reentries'), ('Observed entry-to-exit durations', 'durations'), ('Consecutive-quarter reported actions', 'streaks')]:
            st.write(title)
            if summary[key].empty:
                st.caption('No qualifying observations in this filtered data.')
            else:
                st.dataframe(summary[key], hide_index=True)
        st.caption('Durations use observed dates (quarter-end for quarterly labels), not execution dates. Initial disclosures do not establish original entry dates. Streaks require events in adjacent calendar quarters and do not establish continuous holdings or complete reporting.')
    query = st.text_input('Search events by ticker, company or action')
    visible = events
    if query:
        mask = events[['ticker', 'company', 'action_original']].astype(str).apply(lambda s: s.str.contains(query, case=False, regex=False)).any(axis=1)
        visible = events[mask]
    st.dataframe(visible, hide_index=True)
    st.download_button('Download filtered reported events', visible.to_csv(index=False), 'reported_position_changes.csv', 'text/csv')
    st.caption('Reported changes cannot establish execution prices, realized profits, cash balances or who made a manager’s investment decisions. Check validation findings for inconsistent share histories and possible corporate actions.')
