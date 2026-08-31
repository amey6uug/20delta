"""Load 20Δ Short Strangle backtest data (charge-aware, mirrors theta loader).

Ports the old inline ``app.py:load_backtest`` onto the shared, charge-aware
``portfolio.algotest_loader.load_algotest_csv`` so the strangle page's P&L is
net of Flattrade statutory charges — matching the theta and portfolio views.
Day categories are rebuilt from the NIFTY vs SENSEX instrument split.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from portfolio.algotest_loader import load_algotest_csv
from portfolio.analysis import load_config

SENSEX_STRIKE_FLOOR = 40_000


def _instrument_map(csv_path: str) -> dict[str, str]:
    """Map each parent trade index → 'NIFTY' or 'SENSEX' from child strikes.

    load_algotest_csv only returns parent + daily rows, so the child legs are
    re-read here to classify the instrument (SENSEX strikes are ~5-6 figure).
    """
    df = pd.read_csv(csv_path)
    df.columns = df.columns.str.strip()
    df["_idx"] = pd.to_numeric(df["Index"], errors="coerce")
    child = df[df["_idx"] != df["_idx"].apply(np.floor)].copy()
    if child.empty:
        return {}
    child["parent_idx"] = child["_idx"].apply(lambda x: str(int(np.floor(x))))
    child["Strike"] = pd.to_numeric(child["Strike"], errors="coerce")
    mean_strike = child.groupby("parent_idx")["Strike"].mean()
    return {
        idx: ("SENSEX" if s > SENSEX_STRIKE_FLOOR else "NIFTY")
        for idx, s in mean_strike.items()
    }


def _day_cat(row) -> str:
    n, s = row["N_SL"], row["S_SL"]
    if n == 0 and s == 0:
        return "Both Clean"
    if (n == 1 and s == 0) or (n == 0 and s == 1):
        return "1 Instr: 50% SL only"
    if n == 1 and s == 1:
        return "Both: 50% SL only"
    if (n == 2 and s == 0) or (n == 0 and s == 2):
        return "1 Instr: 50%+BE hit"
    if (n == 2 and s == 1) or (n == 1 and s == 2):
        return "Mixed: 50%+BE + 50%SL"
    if n == 2 and s == 2:
        return "Both: 50%+BE hit"
    return "Other"


def load_strangle_backtest():
    """Return daily, parent — same columns/shape as the theta loader."""
    cfg = load_config()
    s = cfg["strategies"]["strangle_20d"]
    rates = cfg.get("charges", {})
    window = cfg.get("comparison_window", {})
    csv_path = s["csv_path"]

    daily, parent = load_algotest_csv(
        csv_path, dayfirst=s.get("dayfirst", False), charge_rates=rates,
    )

    if window.get("start"):
        start = pd.Timestamp(window["start"])
        daily = daily[daily["Date"] >= start]
        parent = parent[parent["Date"] >= start]
    if window.get("end"):
        end = pd.Timestamp(window["end"])
        daily = daily[daily["Date"] <= end]
        parent = parent[parent["Date"] <= end]

    daily = daily.sort_values("Date").reset_index(drop=True)
    daily["Cumulative"] = daily["PL"].cumsum()
    daily["Win"] = daily["PL"] > 0
    if "DOW" not in daily.columns:
        daily["DOW"] = daily["Date"].dt.day_name()
    daily["DOW_num"] = daily["Date"].dt.dayofweek

    # ── Day categories from NIFTY/SENSEX instrument split ────────────────────────
    parent = parent.copy()
    parent["legs_stopped"] = parent.get("legs_stopped", 0)
    parent["legs_stopped"] = pd.to_numeric(parent["legs_stopped"], errors="coerce").fillna(0).astype(int)
    parent["Instrument"] = parent["idx_str"].map(_instrument_map(csv_path)).fillna("NIFTY")

    wide = parent.pivot_table(
        index="Date", columns="Instrument", values="legs_stopped", aggfunc="first",
    ).reset_index()
    wide.columns.name = None
    for col in ["NIFTY", "SENSEX"]:
        if col not in wide.columns:
            wide[col] = 0
    wide = wide.rename(columns={"NIFTY": "N_SL", "SENSEX": "S_SL"})
    wide["N_SL"] = wide["N_SL"].fillna(0).astype(int)
    wide["S_SL"] = wide["S_SL"].fillna(0).astype(int)
    wide["Day_Cat"] = wide.apply(_day_cat, axis=1)

    daily = daily.merge(wide[["Date", "Day_Cat"]], on="Date", how="left")
    daily["Day_Cat"] = daily["Day_Cat"].fillna("Other")

    return daily, parent
