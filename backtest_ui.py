"""Backtest Engine UI — Historical Replay with Real Risk Rules."""

from __future__ import annotations

from datetime import date
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from engine.backtest_engine import BacktestRunner
from engine.calendar import format_date_day
from engine.config_service import config_service
from theme import (
    BLUE, GREEN, RED, GOLD, PURPLE, MUTED, PLOT_LAYOUT, LEGEND,
    color_for, fmt_inr, page_header, render_table,
)


def render_backtest_page():
    page_header(
        "Historical Backtest Engine",
        subtitle="Replay historical market data with production risk rules, stop loss, and profit lock",
        badge="backtest",
    )

    strategies = config_service.list_configs()
    strat_map = {s.strategy_name: s.strategy_id for s in strategies}

    # ── Control Bar ────────────────────────────────────────────────────────────
    st.markdown("##### ⚙️ Backtest Parameters")
    with st.container(border=True):
        c1, c2, c3, c4 = st.columns([2, 1.5, 1.5, 1.5])
        with c1:
            selected_strat_name = st.selectbox("Strategy", list(strat_map.keys()), index=0)
            strat_id = strat_map[selected_strat_name]
        with c2:
            from_date = st.date_input("From Date", value=date(2024, 1, 1), min_value=date(2020, 1, 1), max_value=date(2027, 12, 31))
        with c3:
            to_date = st.date_input("To Date", value=date(2026, 6, 30), min_value=date(2020, 1, 1), max_value=date(2027, 12, 31))
        with c4:
            capital_val = st.number_input("Testing Capital (₹)", value=1_000_000, step=50_000)

        c_und, c_sl, c_lock, c_tgt = st.columns(4)
        with c_und:
            underlying_filter = st.selectbox("Underlying Index", ["BOTH (NIFTY + SENSEX)", "NIFTY", "SENSEX"], index=0)
        with c_sl:
            sl_pct = st.number_input("Per-Leg Stop Loss (%)", value=80.0, step=5.0, help="Calculated strictly on entry premium of each leg")
        with c_lock:
            lock_pct = st.number_input("Profit Lock Trigger (%)", value=1.0, step=0.5, help="Locks +1% floor on strategy capital")
        with c_tgt:
            tgt_pct = st.number_input("Profit Target (%)", value=2.0, step=0.5, help="Exits all legs at +2% target")

        run_btn = st.button("🚀 Run Backtest", type="primary", use_container_width=True)

    # ── Execution ──────────────────────────────────────────────────────────────
    if run_btn or "last_backtest_summary" not in st.session_state:
        # Clone and customize config for backtest
        base_cfg = config_service.get_config(strat_id)
        if base_cfg:
            base_cfg.capital = float(capital_val)
            base_cfg.stop_loss_percent = float(sl_pct)
            base_cfg.profit_lock_trigger_percent = float(lock_pct)
            base_cfg.profit_target_percent = float(tgt_pct)

        summary, err = BacktestRunner.run_backtest(
            strategy_id=strat_id,
            from_date=from_date,
            to_date=to_date,
            underlying_filter=underlying_filter,
            capital=float(capital_val),
            custom_config=base_cfg,
        )
        st.session_state["last_backtest_summary"] = summary
        st.session_state["last_backtest_err"] = err

    summary = st.session_state.get("last_backtest_summary")
    err = st.session_state.get("last_backtest_err")

    if err:
        st.error(f"⚠️ {err}")
        return

    if not summary:
        st.info("Select parameters and click 'Run Backtest' to view historical performance.")
        return

    st.markdown("<br>", unsafe_allow_html=True)

    # ── KPI Cards ──────────────────────────────────────────────────────────────
    st.markdown("##### 📈 Backtest Results Overview")
    k1, k2, k3, k4, k5, k6 = st.columns(6)
    k1.metric("Win Rate", f"{summary.win_rate:.1f}%", f"{summary.winning_days}W / {summary.losing_days}L")
    k2.metric("Net P&L", fmt_inr(summary.net_pnl), f"{summary.net_pnl_pct:+.1f}% on ₹{summary.capital/100_000:.1f}L")
    k3.metric("Profit Factor", f"{summary.profit_factor:.2f}", f"Gross {fmt_inr(summary.gross_profit)}")
    k4.metric("Max Drawdown", fmt_inr(summary.max_drawdown), f"{summary.max_drawdown_pct:.1f}% of capital")
    k5.metric("Avg Daily P&L", fmt_inr(summary.avg_daily_pnl), f"{summary.trading_days_executed} trading days")
    k6.metric("Best / Worst Day", f"{fmt_inr(summary.max_profit)}", f"Worst {fmt_inr(summary.max_loss)}")

    # ── Risk Events Summary ────────────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("##### 🛡️ Risk & Exit Event Statistics")
    e1, e2, e3, e4, e5 = st.columns(5)
    e1.metric("Profit Target Hits (2%)", str(summary.profit_target_hits), "All Legs Exited")
    e2.metric("Profit Lock Hits (1%)", str(summary.profit_lock_activations), "Floor Protected")
    e3.metric("Normal SL Hits (80%)", str(summary.normal_sl_hits), "Single Leg Stopped")
    e4.metric("Hard SL Hits (100%)", str(summary.hard_sl_hits), "Hard Stop Triggered")
    e5.metric("Forced 3:00 PM Exits", str(summary.forced_3pm_exits), "EOD Absolute Rule")

    # ── Equity Curve ───────────────────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("##### 📉 Cumulative Equity Curve")
    df_results = pd.DataFrame(summary.daily_results)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df_results["RawDate"],
        y=df_results["Cumulative (₹)"],
        mode="lines",
        line=dict(color=GREEN, width=2.5),
        fill="tozeroy",
        fillcolor="rgba(57,211,83,0.1)",
        name="Cumulative Net P&L",
        hovertemplate="%{x|%d %b %Y}<br>₹%{y:,.0f}<extra></extra>",
    ))
    fig.add_hline(y=0, line_color=MUTED, line_dash="dash", line_width=0.8)
    fig.update_layout(**PLOT_LAYOUT, height=320, legend=LEGEND, title=dict(text="Backtest Cumulative P&L (₹10,00,000 Capital)", font=dict(size=14)))
    fig.update_yaxes(tickprefix="₹", tickformat=",.0f")
    st.plotly_chart(fig, width="stretch")

    # ── Day-by-Day Results Table ───────────────────────────────────────────────
    st.markdown("##### 📋 Day-by-Day Trade Execution Log")
    display_cols = ["Date", "Underlying", "Entry_Time", "Exit_Time", "P&L (₹)", "P&L (%)", "Cumulative (₹)", "Exit_Reason", "VIX"]
    render_table(df_results[display_cols])
    st.caption(f"Data Source: {summary.data_source_note}")
