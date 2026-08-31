"""Theta Shifting dashboard — same widgets as the strangle tab."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from portfolio.analysis import load_config
from portfolio.charges import apply_charges_to_live
from strategy_dashboard import render_strategy_tabs
from theme import LEGEND as _LEGEND, PLOT_LAYOUT, page_header, render_table as _render_table
from theta.labels import DAY_CAT_ORDER, remap_legacy_labels
from theta.loader import load_theta_backtest

LIVE_CSV = Path("data/live_trades_theta.csv")

_CACHE_VER = "rs50-charges-v1"  # bump to invalidate Streamlit cache after label/charge changes


@st.cache_data
def _load_theta(_ver: str = _CACHE_VER):
    daily, parent = load_theta_backtest()
    daily = daily.copy()
    daily["Day_Cat"] = remap_legacy_labels(daily["Day_Cat"])
    cfg = load_config()
    cap = cfg.get("capital_per_strategy", 550_000)
    s = cfg["strategies"]["theta_shifting"]
    return daily, parent, cap, s


@st.cache_data(ttl=60)
def _load_live_theta(_ver: str = _CACHE_VER):
    if not LIVE_CSV.exists():
        return pd.DataFrame()
    df = pd.read_csv(LIVE_CSV)
    df["Date"] = pd.to_datetime(df["Date"], dayfirst=True)
    for col in ("Exit_Reason", "Instr_Category", "Day_Category"):
        if col in df.columns:
            df[col] = remap_legacy_labels(df[col])
    cfg = load_config()
    return apply_charges_to_live(df, cfg.get("charges"))


def render_theta_dashboard():
    bt, _parent, capital, s_cfg = _load_theta()
    live = _load_live_theta()

    live_daily = pd.DataFrame()
    if not live.empty:
        sum_cols = ["Date", "Day_PL", "Day_Category"]
        for c in ["VIX_Open", "VIX_Close", "VIX_Change_Pct"]:
            if c in live.columns:
                sum_cols.append(c)
        live_daily = live.drop_duplicates(subset=["Date"])[sum_cols].copy()
        live_daily = live_daily.sort_values("Date").reset_index(drop=True)
        live_daily["Cumulative"] = live_daily["Day_PL"].cumsum()
        live_daily["Win"] = live_daily["Day_PL"] > 0

    page_header(
        "SENSEX ATM Straddle &nbsp;|&nbsp; Theta Shifting &nbsp;|&nbsp; 9:45 + 11:45 Entry",
        subtitle="Backtest Jan 2024 – Jun 2026 (1 lot) &nbsp;|&nbsp; Live on your Flattrade",
        badge="live" if not live.empty else "backtest",
    )
    st.caption(s_cfg.get("description", ""))

    render_strategy_tabs(
        bt,
        live,
        live_daily,
        capital=capital,
        plot_layout=PLOT_LAYOUT,
        legend=_LEGEND,
        render_table=_render_table,
        expiry_days={"Thursday": "🟡 SENSEX"},
        dow_caption="Thursday = SENSEX weekly expiry  |  Day categories = 9:45 vs 11:45 entry slots",
        day_cat_caption=(
            "Categories: 9:45 slot = first · 11:45 slot = second "
            "(₹50 fixed leg SL / BE trail per straddle)"
        ),
        day_cat_order=DAY_CAT_ORDER,
        live_log_columns=[
            "Date", "Index", "Type", "Strike", "Entry_Price", "Entry_Time",
            "Exit_Price", "Exit_Time", "Exit_Reason", "PL", "Instr_Category", "Day_Category",
        ],
        live_empty_hint=(
            "Theta live tracking started Jul 2026. Trades will appear here once "
            "`data/live_trades_theta.csv` is populated from your Flattrade account."
        ),
    )
