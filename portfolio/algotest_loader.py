"""Load Algotest CSV exports into a normalised daily P&L series."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from portfolio.charges import DEFAULT_RATES, daily_pl_with_charges

VIX_BINS = [0, 12, 14, 16, 18, 20, 100]
VIX_LABELS = ["<12", "12–14", "14–16", "16–18", "18–20", ">20"]


def load_algotest_csv(
    csv_path: str | Path,
    dayfirst: bool = True,
    apply_charges: bool = True,
    charge_rates: dict | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Parse an Algotest backtest CSV (parent + child rows).

    Returns
    -------
    daily : Date, PL, VIX, Cumulative, Win, DOW, VIX_Bucket
    parent : one row per parent Index (trade group)
    """
    df = pd.read_csv(csv_path)
    df.columns = df.columns.str.strip()
    df["_idx"] = pd.to_numeric(df["Index"], errors="coerce")

    parent = df[df["_idx"] == df["_idx"].apply(np.floor)].copy()
    child = df[df["_idx"] != df["_idx"].apply(np.floor)].copy()

    parent["PL"] = pd.to_numeric(parent["P/L"], errors="coerce")
    parent["Date"] = pd.to_datetime(parent["Entry Date"].astype(str).str.strip(), dayfirst=dayfirst)
    parent["VIX"] = pd.to_numeric(parent["Vix"].replace("NA", np.nan), errors="coerce")
    parent["idx_str"] = parent["_idx"].astype(int).astype(str)

    if not child.empty:
        child["parent_idx"] = child["_idx"].apply(lambda x: str(int(np.floor(x))))
        child["Strike"] = pd.to_numeric(child["Strike"], errors="coerce")
        child["sl_hit"] = child["Exit Time"].astype(str).str.strip() != "3:15:00 PM"
        sl_pp = child.groupby("parent_idx")["sl_hit"].sum().reset_index()
        sl_pp.columns = ["idx_str", "legs_stopped"]
        parent = parent.merge(sl_pp, on="idx_str", how="left")
        parent["legs_stopped"] = parent["legs_stopped"].fillna(0).astype(int)
    else:
        parent["legs_stopped"] = 0

    rates = charge_rates or DEFAULT_RATES

    if not child.empty and apply_charges:
        daily = daily_pl_with_charges(child, parent, dayfirst=dayfirst, rates=rates)
    else:
        daily = (
            parent.groupby("Date")
            .agg(PL=("PL", "sum"), VIX=("VIX", "first"))
            .reset_index()
            .sort_values("Date")
        )
        daily = daily.dropna(subset=["PL"]).reset_index(drop=True)
        daily["PL_gross"] = daily["PL"]
        daily["Charges"] = 0.0
        daily["Cumulative"] = daily["PL"].cumsum()
        daily["Win"] = daily["PL"] > 0
        daily["DOW"] = daily["Date"].dt.day_name()

    if "VIX_Bucket" not in daily.columns:
        daily["VIX_Bucket"] = pd.cut(daily["VIX"], bins=VIX_BINS, labels=VIX_LABELS)

    return daily, parent
