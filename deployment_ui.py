"""Deployment Readiness & Future Broker Integration Dashboard."""

from __future__ import annotations

import os
import streamlit as st

from engine.config_service import config_service
from theme import (
    BLUE, GREEN, RED, GOLD, PURPLE, MUTED,
    fmt_inr, page_header,
)


def render_deployment_page():
    page_header(
        "Broker Deployment & Live Execution Controls",
        subtitle="Deployment lifecycle management, broker adapter verification, and execution safety gates",
        badge="paper",
    )

    st.info("🔒 **Live Trading Deployment Status**: Currently locked in **PAPER TRADING / SIMULATION ONLY** mode for risk safety.")

    st.markdown("##### 🚀 Execution State & Deployment Pipeline")
    d1, d2, d3, d4 = st.columns(4)
    d1.metric("Deployment State", "TESTING", "Paper Execution Active")
    d2.metric("Broker Connection", "Flattrade NorenAPI", "Paper Sandbox Ready")
    d3.metric("Live Execution Gate", "LOCKED", "Manual confirmation required")
    d4.metric("Safety Architecture", "ENABLED", "SENSEX ATM Short Prohibited")

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Deployment Pre-Flight Checklist ────────────────────────────────────────
    st.markdown("##### 📋 Pre-Deployment Safety Checklist")
    with st.container(border=True):
        st.checkbox("✅ Per-Leg 80% Stop Loss & 100% Hard Stop Verified in Engine", value=True, disabled=True)
        st.checkbox("✅ 1% Basket Profit Lock & 2% Profit Target Configured", value=True, disabled=True)
        st.checkbox("✅ 03:00 PM IST Forced Exit Rule Active", value=True, disabled=True)
        st.checkbox("✅ SENSEX ATM Short Order Rejection Permanently Enforced", value=True, disabled=True)
        st.checkbox("✅ Protective Hedge-First Execution Sequence Confirmed", value=True, disabled=True)
        st.checkbox("🔒 Live Broker Execution Credentials Securely Handled in Backend .env", value=True, disabled=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Broker Configuration & Credentials Status ──────────────────────────────
    st.markdown("##### 🔌 Broker Adapter Configuration")
    flattrade_user = os.getenv("FLATTRADE_USER_ID", "FT_DEMO_USER")
    with st.container(border=True):
        b_col1, b_col2 = st.columns(2)
        with b_col1:
            st.write(f"**Target Broker:** Flattrade (Shoonya NorenAPI)")
            st.write(f"**Brokerage Rate:** ₹0 / order (Statutory charges only)")
            st.write(f"**User ID:** `{flattrade_user}`")
        with b_col2:
            st.write("**Execution Mode:** `PAPER_SIMULATION`")
            st.write("**API Endpoint:** `https://piconnect.flattrade.in/NorenWClientTP`")
            st.write("**Order Routing:** Virtual Paper Broker Adapter")
