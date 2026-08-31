"""Admin Strategy Settings UI — Live Configuration & Version History."""

from __future__ import annotations

import json
import pandas as pd
import streamlit as st

from engine.calendar import format_timestamp_day
from engine.config_service import config_service
from engine.db import db_manager
from engine.models import StrategyConfig
from theme import (
    BLUE, GREEN, RED, GOLD, PURPLE, MUTED,
    color_for, fmt_inr, page_header, render_table,
)


def render_settings_page():
    page_header(
        "Strategy Risk & Execution Settings",
        subtitle="Manage strategy parameters, risk thresholds, strike distances, and version history",
        badge="live",
    )

    strategies = config_service.list_configs()
    strat_map = {s.strategy_name: s.strategy_id for s in strategies}

    selected_name = st.selectbox("Select Strategy to Configure", list(strat_map.keys()), index=0)
    strat_id = strat_map[selected_name]
    cfg = config_service.get_config(strat_id)

    if not cfg:
        st.error("Strategy configuration not found.")
        return

    st.markdown(
        f'<div style="background:#161b22; border:1px solid #30363d; border-radius:8px; padding:12px 18px; margin-bottom:16px; display:flex; justify-content:space-between; align-items:center;">'
        f'<div><b>Current Version:</b> <span style="color:#58a6ff; font-weight:700;">v{cfg.version}</span> &nbsp;|&nbsp; <b>Last Updated:</b> {cfg.updated_at or "Initial Setup"} by <i>{cfg.updated_by}</i></div>'
        f'<div>Status: <b style="color:{"#39d353" if cfg.enabled else "#f85149"}">{"ENABLED" if cfg.enabled else "DISABLED"}</b></div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    with st.form("strategy_settings_form"):
        tab_gen, tab_risk, tab_profit, tab_time, tab_strike, tab_safety, tab_test = st.tabs([
            "📌 General", "🛡️ Risk Engine", "💰 Profit & Locks", "⏰ Market Timing", "🎯 Strike Selection", "🔒 Safety Rules", "🧪 Capital"
        ])

        # ── 1. GENERAL ─────────────────────────────────────────────────────────
        with tab_gen:
            st.markdown("##### General Configuration")
            g1, g2, g3 = st.columns(3)
            with g1:
                name_val = st.text_input("Strategy Name", value=cfg.strategy_name)
            with g2:
                und_val = st.selectbox("Default Underlying", ["NIFTY", "SENSEX", "BOTH"], index=0 if cfg.underlying == "NIFTY" else 1)
            with g3:
                enabled_val = st.checkbox("Strategy Enabled", value=cfg.enabled)

        # ── 2. RISK ────────────────────────────────────────────────────────────
        with tab_risk:
            st.markdown("##### Per-Leg Stop Loss Engine")
            st.caption("Stop loss percentages are calculated STRICTLY against the entry premium of each individual option leg.")
            r1, r2 = st.columns(2)
            with r1:
                sl_val = st.number_input("Normal Stop Loss (%)", value=float(cfg.stop_loss_percent), min_value=1.0, max_value=500.0, step=5.0, help="Default: 80% adverse premium move")
            with r2:
                hard_sl_val = st.number_input("Hard Stop Loss (%)", value=float(cfg.hard_stop_loss_percent), min_value=float(sl_val), max_value=1000.0, step=5.0, help="Default: 100% adverse premium move (hard cutoff)")

        # ── 3. PROFIT ──────────────────────────────────────────────────────────
        with tab_profit:
            st.markdown("##### Basket Profit & Lock Engine")
            st.caption("Profit percentages are calculated on total Strategy Capital.")
            p1, p2, p3 = st.columns(3)
            with p1:
                lock_trig_val = st.number_input("Profit Lock Trigger (%)", value=float(cfg.profit_lock_trigger_percent), min_value=0.1, max_value=50.0, step=0.5, help="Default: 1% (₹10,000 on ₹10L)")
            with p2:
                lock_floor_val = st.number_input("Profit Lock Floor (%)", value=float(cfg.profit_lock_floor_percent), min_value=0.1, max_value=float(lock_trig_val), step=0.5, help="Floor protected once lock is triggered")
            with p3:
                target_val = st.number_input("Profit Target (%)", value=float(cfg.profit_target_percent), min_value=float(lock_trig_val) + 0.1, max_value=100.0, step=0.5, help="Default: 2% (₹20,000 on ₹10L) -> Exits all legs")

        # ── 4. TIME ────────────────────────────────────────────────────────────
        with tab_time:
            st.markdown("##### Strategy Execution Window (Asia/Kolkata)")
            t1, t2 = st.columns(2)
            with t1:
                entry_t_val = st.text_input("Entry Window Start (HH:MM)", value=cfg.entry_time, help="Strategy will NOT enter before 09:45 AM")
            with t2:
                exit_t_val = st.text_input("Forced Exit Time (HH:MM)", value=cfg.forced_exit_time, help="Absolute exit at 03:00 PM (15:00)")

        # ── 5. STRIKE ──────────────────────────────────────────────────────────
        with tab_strike:
            st.markdown("##### Strike Selection & Distances (Points)")
            s_n1, s_n2, s_n3 = st.columns(3)
            with s_n1:
                n_otm_val = st.number_input("NIFTY OTM Distance (DTE > 1)", value=int(cfg.nifty_otm_distance), step=50)
            with s_n2:
                n_near_val = st.number_input("NIFTY Near Expiry (DTE <= 1)", value=int(cfg.nifty_near_expiry_distance), step=50)
            with s_n3:
                n_hdg_val = st.number_input("NIFTY Hedge Distance", value=int(cfg.nifty_hedge_distance), step=50)

            s_s1, s_s2, s_s3 = st.columns(3)
            with s_s1:
                s_otm_val = st.number_input("SENSEX OTM Distance (DTE > 1)", value=int(cfg.sensex_otm_distance), step=100)
            with s_s2:
                s_near_val = st.number_input("SENSEX Near Expiry (DTE <= 1)", value=int(cfg.sensex_near_expiry_distance), step=100)
            with s_s3:
                s_hdg_val = st.number_input("SENSEX Hedge Distance", value=int(cfg.sensex_hedge_distance), step=100)

        # ── 6. SAFETY ──────────────────────────────────────────────────────────
        with tab_safety:
            st.markdown("##### Hard Safety Constraints")
            st.warning("⚠️ **SENSEX ATM SHORTING IS PROHIBITED**: This safety rule is permanently enforced in the engine core.")
            safe1, safe2, safe3 = st.columns(3)
            with safe1:
                hdg_req_val = st.checkbox("Hedge Required (Hedge-First Fill)", value=cfg.hedge_required)
            with safe2:
                atm_short_val = st.checkbox("Allow SENSEX ATM Short (Permanently Locked)", value=False, disabled=True)
            with safe3:
                reentry_val = st.checkbox("Allow Intraday Re-entry", value=cfg.allow_reentry)

        # ── 7. TESTING CAPITAL ─────────────────────────────────────────────────
        with tab_test:
            st.markdown("##### Strategy Testing Capital")
            cap_val = st.number_input("Strategy Capital (₹)", value=float(cfg.capital), min_value=50_000.0, step=50_000.0, help="Default: ₹10,00,000")

        st.markdown("<br>", unsafe_allow_html=True)
        col_btn1, col_btn2 = st.columns([2, 1])
        with col_btn1:
            save_btn = st.form_submit_button("💾 Save Strategy Settings", type="primary", use_container_width=True)
        with col_btn2:
            reset_btn = st.form_submit_button("🔄 Reset to Default Parameters", use_container_width=True)

    # Handle Actions
    if save_btn:
        updated_cfg = StrategyConfig(
            strategy_id=strat_id,
            strategy_name=name_val,
            underlying=und_val,
            enabled=enabled_val,
            capital=float(cap_val),
            stop_loss_percent=float(sl_val),
            hard_stop_loss_percent=float(hard_sl_val),
            profit_lock_trigger_percent=float(lock_trig_val),
            profit_lock_floor_percent=float(lock_floor_val),
            profit_target_percent=float(target_val),
            entry_time=entry_t_val,
            forced_exit_time=exit_t_val,
            hedge_required=hdg_req_val,
            nifty_otm_distance=int(n_otm_val),
            nifty_near_expiry_distance=int(n_near_val),
            nifty_hedge_distance=int(n_hdg_val),
            sensex_otm_distance=int(s_otm_val),
            sensex_near_expiry_distance=int(s_near_val),
            sensex_hedge_distance=int(s_hdg_val),
            allow_atm_short=False,
            allow_reentry=reentry_val,
            max_positions=4,
        )
        success, msg, new_ver = config_service.update_config(updated_cfg, user="admin_user")
        if success:
            st.success(f"✅ {msg}")
            st.rerun()
        else:
            st.error(f"❌ Validation Error: {msg}")

    if reset_btn:
        success, msg = config_service.reset_to_defaults(strat_id, user="admin_user")
        if success:
            st.success(f"✅ {msg}")
            st.rerun()
        else:
            st.error(f"❌ {msg}")
