"""Margin Calculator UI — Options Margin and Hedge Benefit Estimator."""

from __future__ import annotations

from datetime import date
import pandas as pd
import streamlit as st

from engine.calendar import format_date_day, get_expiry_date
from engine.margin_calc import MarginCalculator
from theme import (
    BLUE, GREEN, RED, GOLD, PURPLE, MUTED,
    color_for, fmt_inr, page_header, render_table,
)


def render_margin_page():
    page_header(
        "Options Margin & Hedge Benefit Calculator",
        subtitle="Estimate SPAN/exposure requirements, hedge relief benefits, and capital headroom",
        badge="backtest",
    )

    st.markdown("##### 🧮 Position & Margin Parameters")
    with st.container(border=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            underlying = st.selectbox("Underlying Index", ["NIFTY", "SENSEX", "BANKNIFTY"], index=0)
        with c2:
            default_exp = get_expiry_date(underlying, date.today())
            expiry_val = st.date_input("Expiry Date", value=default_exp)
        with c3:
            strategy_capital = st.number_input("Testing Capital (₹)", value=1_000_000, step=50_000)

        st.markdown("---")
        st.markdown("**Main Short Leg:**")
        s1, s2, s3, s4 = st.columns(4)
        with s1:
            short_strike = st.number_input("Short Strike", value=24400 if underlying == "NIFTY" else 77700, step=50 if underlying == "NIFTY" else 100)
        with s2:
            short_opt = st.selectbox("Option Type (Short)", ["CE", "PE"], index=0)
        with s3:
            short_qty = st.number_input("Short Quantity", value=65 if underlying == "NIFTY" else 20, step=65 if underlying == "NIFTY" else 20)
        with s4:
            short_prem = st.number_input("Short Premium (₹)", value=48.0, step=1.0)

        st.markdown("---")
        st.markdown("**Protective Hedge Leg (Optional / Recommended):**")
        h1, h2, h3, h4 = st.columns(4)
        with h1:
            hedge_strike = st.number_input("Hedge Strike", value=24700 if underlying == "NIFTY" else 78200, step=50 if underlying == "NIFTY" else 100)
        with h2:
            hedge_opt = st.selectbox("Option Type (Hedge)", ["CE", "PE"], index=0)
        with h3:
            hedge_qty = st.number_input("Hedge Quantity", value=65 if underlying == "NIFTY" else 20, step=65 if underlying == "NIFTY" else 20)
        with h4:
            hedge_prem = st.number_input("Hedge Premium (₹)", value=12.0, step=0.5)

    # ── Calculation ────────────────────────────────────────────────────────────
    hedge_dist = abs(hedge_strike - short_strike)
    breakdown = MarginCalculator.calculate_margin(
        underlying=underlying,
        short_quantity=int(short_qty),
        short_premium=float(short_prem),
        hedge_quantity=int(hedge_qty),
        hedge_premium=float(hedge_prem),
        hedge_distance_points=float(hedge_dist),
        strategy_capital=float(strategy_capital),
    )

    st.markdown("<br>", unsafe_allow_html=True)

    # ── KPI Breakdown ──────────────────────────────────────────────────────────
    st.markdown("##### 📊 Margin Requirement & Capital Utilization")
    st.caption(f"Status: **{breakdown.status_label}**")

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Naked Short Margin", fmt_inr(breakdown.naked_short_margin), "Without hedge")
    m2.metric("Hedge Benefit", f"-{fmt_inr(breakdown.hedge_benefit)}", "Margin relief")
    m3.metric("Net Margin Required", fmt_inr(breakdown.net_margin_required), f"{breakdown.margin_utilization_pct:.1f}% of capital")
    m4.metric("Available Capital", fmt_inr(breakdown.available_capital_after_trade), "Headroom remaining")
    m5.metric("Net Premium Flow", fmt_inr(breakdown.premium_receivable_or_payable), "Credit received" if breakdown.premium_receivable_or_payable > 0 else "Debit paid")

    st.markdown("<br>", unsafe_allow_html=True)

    # Summary table
    table_data = [
        {"Parameter": "Underlying Asset", "Value": breakdown.underlying},
        {"Parameter": "Strategy Capital", "Value": fmt_inr(breakdown.total_capital)},
        {"Parameter": "Naked Position Margin", "Value": fmt_inr(breakdown.naked_short_margin)},
        {"Parameter": "Protective Hedge Relief", "Value": f"-{fmt_inr(breakdown.hedge_benefit)}"},
        {"Parameter": "Net Estimated Margin", "Value": fmt_inr(breakdown.net_margin_required)},
        {"Parameter": "Gross Premium Exposure", "Value": fmt_inr(breakdown.gross_exposure)},
        {"Parameter": "Remaining Available Capital", "Value": fmt_inr(breakdown.available_capital_after_trade)},
        {"Parameter": "Capital Sufficiency", "Value": "✅ SUFFICIENT CAPITAL" if breakdown.is_sufficient_capital else "❌ INSUFFICIENT CAPITAL"},
    ]
    render_table(pd.DataFrame(table_data))
