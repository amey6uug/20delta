"""AlgoTest OS — multi-strategy options dashboard (entry point).

Navigation shell only. Each page's logic lives in its own module:
  · Overview            → home.render_home
  · 20Δ Short Strangle  → strangle.dashboard.render_strangle_dashboard
  · Theta Shifting      → theta.dashboard.render_theta_dashboard
  · Portfolio           → portfolio.dashboard.render_portfolio_dashboard

Run:  streamlit run app.py
"""

import streamlit as st

st.set_page_config(
    page_title="AlgoTest OS — Strategies",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

from theme import inject_theme

inject_theme()

import nav

pages, _ = nav.build_pages()
st.navigation(pages, position="sidebar").run()
