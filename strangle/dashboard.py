"""20Δ Short Strangle dashboard — Backtest / Live / Compare (shared renderer)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from portfolio.analysis import load_config
from portfolio.charges import apply_charges_to_live
from strategy_dashboard import render_strategy_tabs
from strangle.loader import load_strangle_backtest
from theme import LEGEND, PLOT_LAYOUT, page_header, render_table

LIVE_CSV = Path("data/live_trades.csv")
_CACHE_VER = "live-charges-v1"


@st.cache_data
def _load_strangle(_ver: str = _CACHE_VER):
    daily, parent = load_strangle_backtest()
    cfg = load_config()
    cap = cfg.get("capital_per_strategy", 550_000)
    s = cfg["strategies"]["strangle_20d"]
    return daily, parent, cap, s


@st.cache_data(ttl=60)
def _load_live_strangle(_ver: str = _CACHE_VER):
    if not LIVE_CSV.exists():
        return pd.DataFrame()
    df = pd.read_csv(LIVE_CSV)
    df["Date"] = pd.to_datetime(df["Date"], dayfirst=True)
    cfg = load_config()
    return apply_charges_to_live(df, cfg.get("charges"))


def render_strangle_dashboard():
    bt, _parent, capital, s_cfg = _load_strangle()
    live = _load_live_strangle()

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
        "NIFTY + SENSEX &nbsp;|&nbsp; 20&Delta; Short Strangle &nbsp;|&nbsp; 9:45 Entry",
        subtitle="Backtest Jan 2024 – Jun 2026 (1 lot) &nbsp;|&nbsp; Live on wife's Flattrade",
        badge="live" if not live.empty else "backtest",
    )
    st.caption(s_cfg.get("description", ""))

    render_strategy_tabs(
        bt,
        live,
        live_daily,
        capital=capital,
        plot_layout=PLOT_LAYOUT,
        legend=LEGEND,
        render_table=render_table,
        expiry_days={"Tuesday": "🟡 NIFTY", "Thursday": "🟡 SENSEX"},
        dow_caption="Tuesday = NIFTY weekly expiry  |  Thursday = SENSEX weekly expiry",
        day_cat_caption="Categories: N_SL = NIFTY legs stopped · S_SL = SENSEX legs stopped (50% SL / BE trail)",
        live_log_columns=[
            "Date", "Index", "Type", "Strike", "Entry_Price", "Entry_Time",
            "Exit_Price", "Exit_Time", "Exit_Reason", "PL", "Instr_Category", "Day_Category",
        ],
        live_empty_hint=(
            "Live trades will appear here as `data/live_trades.csv` is populated "
            "from the Flattrade account."
        ),
    )
