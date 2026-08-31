"""
Portfolio diversification dashboard — compares strangle vs theta backtests.

Standalone:
    python -m streamlit run portfolio_app.py

The canonical entry point is now app.py, where this view is the "Portfolio"
page. This wrapper is kept for standalone/bookmarked use.
"""

import streamlit as st

from portfolio.dashboard import inject_portfolio_styles, render_portfolio_dashboard

st.set_page_config(
    page_title="Portfolio Diversification",
    page_icon="🔀",
    layout="wide",
    initial_sidebar_state="collapsed",
)

inject_portfolio_styles()
render_portfolio_dashboard(embedded=False)
