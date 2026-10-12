"""Shared gold and sage presentation, including reduced-motion support."""
import streamlit as st
import plotly.io as pio
import plotly.graph_objects as go


def render():
    pio.templates['portfolio_editorial'] = go.layout.Template(layout=dict(
        font=dict(family='Georgia, Times New Roman, serif', size=16, color='#24392c'),
        title=dict(font=dict(family='Georgia, Times New Roman, serif', size=24)),
        hoverlabel=dict(font=dict(family='Arial, sans-serif', size=16)),
        legend=dict(font=dict(size=16)),
    ))
    pio.templates.default = 'plotly_white+portfolio_editorial'
    st.markdown('''<style>
    html {font-size: 18px;}
    .stApp {font-family: Georgia, "Times New Roman", serif;}
    .stApp h1, .stApp h2, .stApp h3 {
      font-family: Georgia, "Times New Roman", serif; font-weight: 800;
      color: #25362b; letter-spacing: -.025em; line-height: 1.2;}
    .stApp h1 {font-size: clamp(2.4rem, 4vw, 3.4rem);}
    .stApp h2 {font-size: clamp(1.8rem, 3vw, 2.3rem);}
    .stApp h3 {font-size: clamp(1.4rem, 2.4vw, 1.8rem);}
    [data-testid="stMarkdownContainer"] p,
    [data-testid="stMarkdownContainer"] li {font-size: 1rem; line-height: 1.65; font-weight: 600;}
    [data-testid="stCaptionContainer"] p {font-size: .9rem; line-height: 1.55; font-weight: 500;}
    [data-testid="stWidgetLabel"] p {font-size: 1rem; font-weight: 700;}
    button[data-baseweb="tab"] p {
      font-family: Georgia, "Times New Roman", serif; font-size: 1.1rem;
      font-weight: 800; line-height: 1.35; white-space: normal;}
    button[data-baseweb="tab"] {flex-shrink: 0; max-width: 360px;}
    button[kind="primary"] [data-testid="stMarkdownContainer"] p {
      font-family: Georgia, "Times New Roman", serif;
      font-size: clamp(1.15rem, 2vw, 1.4rem); font-weight: 800;
      line-height: 1.3; letter-spacing: .01em; color: #302504;}
    [data-testid="stMetricValue"] {font-family: Georgia, "Times New Roman", serif; font-weight: 800;}
    .stApp {background: linear-gradient(135deg, #fffdf5 0%, #f3f9ef 100%); color: #24392c;}
    [data-testid="stSidebar"] {background: #edf5e8; border-right: 1px solid #d6dfc8;}
    [data-baseweb="tab-list"] {gap: 8px; padding: 8px; background: #eef5e8; border-radius: 16px; overflow-x: auto;}
    button[data-baseweb="tab"] {background: #fffaf0; border: 1px solid #d9c58a; border-radius: 11px;
      padding: 10px 16px; height: auto; color: #655018; transition: background .2s;}
    button[data-baseweb="tab"][aria-selected="true"] {background: linear-gradient(110deg,#dfb847,#f8dc84);
      color: #342704; border-color: #b98c22; box-shadow: 0 3px 10px #aa812322;}
    [data-baseweb="tab-highlight"] {background: #b98c22;}
    button[kind="primary"] {background: linear-gradient(110deg,#c99a2e,#f4d575);
      color: #302504; border: 1px solid #b48824; border-radius: 12px; font-weight: 700;
      min-height: 64px; padding: 12px 20px; box-shadow: 0 4px 12px #95701728;}
    button[kind="primary"]:hover {background: #f0cf6a; color: #302504; border-color: #927017;}
    button:focus-visible {outline: 3px solid #7b9b62; outline-offset: 3px;}
    [data-testid="stMetric"] {background: #f5faee; border: 1px solid #dfd5ad; border-radius: 14px; padding: 14px;}
    [data-testid="stProgress"] [role="progressbar"] {height: 20px; border-radius: 7px; background: #e5eddc;}
    [data-testid="stProgress"] [role="progressbar"] > div {
      background: repeating-linear-gradient(110deg,#c99a2e 0px,#c99a2e 14px,#f6d67a 14px,#f6d67a 28px);
      background-size: 56px 100%; animation: gold-charge 1.1s linear infinite;
      box-shadow: 0 0 12px #dfb84755; transition: width .3s ease;}
    @keyframes gold-charge {to {background-position: 56px 0;}}
    @media (prefers-reduced-motion: reduce) {
      [data-testid="stProgress"] [role="progressbar"] > div {animation: none; transition: none;}
    }
    </style>''', unsafe_allow_html=True)
