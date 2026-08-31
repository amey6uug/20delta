"""Navigation registry — builds the st.Page objects for the AlgoTest OS multipage app."""

from __future__ import annotations

import streamlit as st

from audit_ui import render_audit_page
from backtest_ui import render_backtest_page
from calendar_ui import render_calendar_page
from compare_ui import render_compare_page
from deployment_ui import render_deployment_page
from home import render_home
from live_dashboard import render_live_dashboard
from live_test_ui import render_live_test_page
from margin_ui import render_margin_page
from portfolio.dashboard import render_portfolio_dashboard
from settings_ui import render_settings_page
from strangle.dashboard import render_strangle_dashboard
from theta.dashboard import render_theta_dashboard

CURRENT_STRATEGY_PAGES: dict = {}


def _portfolio_page():
    render_portfolio_dashboard(embedded=True)


def build_pages():
    """Create fresh st.Page objects for this script run."""
    global CURRENT_STRATEGY_PAGES

    home = st.Page(render_home, title="Overview", icon="📊", default=True, url_path="home")
    live_dash = st.Page(render_live_dashboard, title="Live Dashboard", icon="📈", url_path="live_dashboard")

    # Strategies
    strangle = st.Page(render_strangle_dashboard, title="20Δ Short Strangle", icon="📉", url_path="strangle")
    theta = st.Page(render_theta_dashboard, title="Theta Shifting", icon="🔀", url_path="theta")
    portfolio = st.Page(_portfolio_page, title="Portfolio Analytics", icon="🧬", url_path="portfolio")

    # Testing & Verification
    backtest = st.Page(render_backtest_page, title="Backtest Engine", icon="🧪", url_path="backtest")
    live_test = st.Page(render_live_test_page, title="Live Test (Paper)", icon="🟢", url_path="live_test")
    compare = st.Page(render_compare_page, title="Backtest vs Live", icon="🔍", url_path="compare")

    # Tools & Management
    margin = st.Page(render_margin_page, title="Margin Calculator", icon="🧮", url_path="margin")
    calendar = st.Page(render_calendar_page, title="Trading Calendar", icon="📅", url_path="calendar")
    settings = st.Page(render_settings_page, title="Strategy Settings", icon="⚙️", url_path="settings")
    audit = st.Page(render_audit_page, title="Audit Logs", icon="📜", url_path="audit")
    deployment = st.Page(render_deployment_page, title="Deployment", icon="🚀", url_path="deployment")

    pages = {
        "Control Center": [home, live_dash],
        "Strategies": [strangle, theta, portfolio],
        "Testing & Simulation": [backtest, live_test, compare],
        "Tools & Calendar": [margin, calendar],
        "Administration": [settings, audit, deployment],
    }
    CURRENT_STRATEGY_PAGES = {"strangle_20d": strangle, "theta_shifting": theta}
    return pages, CURRENT_STRATEGY_PAGES
