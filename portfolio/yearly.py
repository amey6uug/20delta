"""Year-wise strategy comparison within the configured comparison window."""

from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS = 252


def yearly_compare(
    merged: pd.DataFrame,
    name_a: str,
    name_b: str,
    capital: float = 500_000,
) -> pd.DataFrame:
    """
    Calendar-year breakdown inside the comparison window.

    Example for Jan 2024 – Jun 2026:
    - 2024: all trading days in 2024 (~245)
    - 2025: all trading days in 2025 (~247)
    - 2026: Jan–Jun only (~119)
    """
    df = merged.copy()
    df["Year"] = df["Date"].dt.year
    rows = []

    for year, g in df.groupby("Year"):
        days = len(g)
        pl_a, pl_b, pl_c = g[f"PL_{name_a}"], g[f"PL_{name_b}"], g["PL_combined"]
        std_c = pl_c.std()
        sharpe_c = (pl_c.mean() / std_c * np.sqrt(TRADING_DAYS)) if std_c > 0 else 0.0
        cum_c = pl_c.cumsum()
        max_dd_c = (cum_c - cum_c.cummax()).min()

        win_start = g["Date"].min()
        win_end = g["Date"].max()
        span_days = (win_end - win_start).days
        period = "Full calendar year" if span_days > 200 else "Partial year (H1)"

        rows.append({
            "Year": int(year),
            "Period": period,
            "Window Start": win_start.strftime("%d-%b-%Y"),
            "Window End": win_end.strftime("%d-%b-%Y"),
            "Days": days,
            f"Days_{name_a}_W": int(g[f"Win_{name_a}"].sum()),
            f"Days_{name_b}_W": int(g[f"Win_{name_b}"].sum()),
            "Days_Combined_W": int(g["Win_combined"].sum()),
            f"WR_{name_a}": g[f"Win_{name_a}"].mean() * 100,
            f"WR_{name_b}": g[f"Win_{name_b}"].mean() * 100,
            "WR_Combined": g["Win_combined"].mean() * 100,
            f"PL_{name_a}": pl_a.sum(),
            f"PL_{name_b}": pl_b.sum(),
            "PL_Combined": pl_c.sum(),
            f"Avg_{name_a}": pl_a.mean(),
            f"Avg_{name_b}": pl_b.mean(),
            "Avg_Combined": pl_c.mean(),
            "Sharpe_Combined": sharpe_c,
            "MaxDD_Combined": max_dd_c,
        })

    return pd.DataFrame(rows)
