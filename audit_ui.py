"""Audit Log Viewer — Complete Event & Risk Trail."""

from __future__ import annotations

import json
import pandas as pd
import streamlit as st

from engine.calendar import format_timestamp_day
from engine.db import db_manager
from theme import page_header, render_table


def render_audit_page():
    page_header(
        "System & Strategy Audit Logs",
        subtitle="Immutable historical audit trail of state transitions, risk triggers, orders, and configuration updates",
        badge="live",
    )

    st.markdown("##### 📜 Audit Event Filter")
    c1, c2 = st.columns([2, 1])
    with c1:
        strategy_filter = st.selectbox("Filter by Strategy", ["All Strategies", "strangle_20d", "theta_shifting"], index=0)
    with c2:
        limit_val = st.selectbox("Max Records", [50, 100, 200, 500], index=1)

    strat_id_param = None if strategy_filter == "All Strategies" else strategy_filter
    logs = db_manager.get_audit_logs(limit=limit_val, strategy_id=strat_id_param)

    if not logs:
        st.info("No audit logs recorded yet.")
        return

    st.markdown(f"Showing **{len(logs)}** audit events:")

    display_rows = []
    for r in logs:
        display_rows.append({
            "Log ID": r["id"],
            "Timestamp": r["timestamp"],
            "Strategy": r["strategy_id"],
            "Event": r["event"],
            "Reason": r["reason"],
            "State Transition": f"{r['old_state']} → {r['new_state']}" if r["old_state"] or r["new_state"] else "—",
            "User": r["user"],
        })

    render_table(pd.DataFrame(display_rows))
