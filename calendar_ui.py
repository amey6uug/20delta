"""Trading Calendar UI — Indian Exchange Holidays, Expiries, and Session Status."""

from __future__ import annotations

from datetime import date, datetime, timedelta
import pandas as pd
import streamlit as st

from engine.calendar import (
    EXCHANGE_HOLIDAYS,
    calculate_dte,
    format_date_day,
    format_timestamp_day,
    get_current_ist_time,
    get_expiry_date,
    get_next_trading_day,
    get_previous_trading_day,
    is_holiday,
    is_trading_day,
    is_weekend,
)
from theme import (
    BLUE, GREEN, RED, GOLD, PURPLE, MUTED,
    color_for, page_header, render_table,
)


def render_calendar_page():
    page_header(
        "Exchange Trading Calendar & Expiries",
        subtitle="Authoritative NSE / BSE holiday reference, dynamic contract expiries, and session status",
        badge="live",
    )

    now_ist = get_current_ist_time()
    today_date = now_ist.date()

    st.markdown("##### 📅 Current Market Session")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Today's Date", format_date_day(today_date))
        is_today_td = is_trading_day(today_date)
        st.caption(f"Trading Day: {'✅ YES (Active)' if is_today_td else '❌ NO (Closed)'}")

    with c2:
        prev_td = get_previous_trading_day(today_date)
        st.metric("Previous Trading Day", format_date_day(prev_td))

    with c3:
        next_td = get_next_trading_day(today_date)
        st.metric("Next Trading Day", format_date_day(next_td))

    with c4:
        n_exp = get_expiry_date("NIFTY", today_date)
        s_exp = get_expiry_date("SENSEX", today_date)
        st.metric("Upcoming Expiry", format_date_day(n_exp))
        st.caption(f"NIFTY DTE: **{calculate_dte(today_date, n_exp)}** · SENSEX DTE: **{calculate_dte(today_date, s_exp)}**")

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Interactive Date Checker ───────────────────────────────────────────────
    st.markdown("##### 🔍 Date & Expiry Inspector")
    with st.container(border=True):
        col_in, col_res = st.columns([1.5, 2.5])
        with col_in:
            test_d = st.date_input("Select Date to Inspect", value=today_date)
            test_und = st.selectbox("Underlying", ["NIFTY", "SENSEX", "BANKNIFTY"], index=0)
        with col_res:
            holiday_status, holiday_name = is_holiday(test_d)
            resolved_exp = get_expiry_date(test_und, test_d)
            dte = calculate_dte(test_d, resolved_exp)

            st.write(f"**Formatted Date:** `{format_date_day(test_d)}`")
            if holiday_status:
                st.markdown(f"**Trading Status:** 🔴 **MARKET CLOSED** ({holiday_name})")
            else:
                st.markdown("**Trading Status:** 🟢 **ACTIVE TRADING DAY**")
            st.write(f"**Next Expiry for {test_und}:** `{format_date_day(resolved_exp)}` (DTE: **{dte}** days)")

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Full Exchange Holiday Table ────────────────────────────────────────────
    st.markdown("##### 🏛️ Official NSE / BSE Holiday Calendar (2024 – 2027)")
    holiday_rows = []
    for h_date, h_name in sorted(EXCHANGE_HOLIDAYS.items()):
        holiday_rows.append({
            "Holiday Date": format_date_day(h_date),
            "Year": h_date.year,
            "Occasion": h_name,
            "Exchange Status": "Trading Closed (NSE/BSE)",
        })

    df_holidays = pd.DataFrame(holiday_rows)
    selected_year = st.selectbox("Filter by Year", [2026, 2025, 2024, 2027, "All Years"], index=0)
    if selected_year != "All Years":
        df_holidays = df_holidays[df_holidays["Year"] == selected_year]

    render_table(df_holidays[["Holiday Date", "Occasion", "Exchange Status"]])
