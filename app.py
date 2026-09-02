"""AlgoTest OS — multi-strategy options dashboard (entry point).

Navigation shell only. Each page's logic lives in its own module:
  · Overview            → home.render_home
  · 20Δ Short Strangle  → strangle.dashboard.render_strangle_dashboard
  · Theta Shifting      → theta.dashboard.render_theta_dashboard
  · Portfolio           → portfolio.dashboard.render_portfolio_dashboard

Run:  streamlit run app.py
"""

# Broker credentials must be loaded before any module reads os.getenv().
# This previously happened only as a side effect of importing engine.alerts.
from dotenv import load_dotenv

load_dotenv()

import os

import streamlit as st

st.set_page_config(
    page_title="AlgoTest OS — Strategies",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# On Streamlit Cloud there is no .env - credentials arrive via st.secrets.
# The engine reads os.getenv() throughout, so mirror them into the environment
# rather than threading a second config path through every module.
try:
    for _k, _v in st.secrets.items():
        if isinstance(_v, str) and _k not in os.environ:
            os.environ[_k] = _v
except Exception:
    pass  # no secrets.toml locally, and st.secrets is absent under stlite


def _require_password() -> None:
    """
    Gate the app when APP_PASSWORD is set.

    A public deployment holds live broker credentials server-side; without a
    gate any visitor could drive this account. No password configured means no
    gate, so local runs are unaffected.
    """
    expected = os.environ.get("APP_PASSWORD", "").strip()
    if not expected or st.session_state.get("_authed"):
        return

    st.title("🔒 AlgoTest OS")
    st.caption("This deployment is connected to a live broker account.")
    entered = st.text_input("Password", type="password")
    if entered:
        if entered == expected:
            st.session_state["_authed"] = True
            st.rerun()
        else:
            st.error("Incorrect password.")
    st.stop()


_require_password()

from theme import inject_theme

inject_theme()

import nav

pages, _ = nav.build_pages()
st.navigation(pages, position="sidebar").run()
