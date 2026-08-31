"""Portfolio metrics, correlation, overlap, and weight optimisation."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from portfolio.algotest_loader import load_algotest_csv
from portfolio.yearly import yearly_compare

CONFIG_PATH = Path(__file__).parent / "config.json"
TRADING_DAYS = 252


def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def compute_metrics(daily: pd.DataFrame, capital: float = 550_000) -> dict:
    pl = daily["PL"]
    wins = daily["Win"].sum()
    losses = len(daily) - wins
    win_pl = pl[pl > 0]
    loss_pl = pl[pl <= 0]
    roll_max = daily["Cumulative"].cummax()
    max_dd = (daily["Cumulative"] - roll_max).min()
    std = pl.std()
    sharpe = (pl.mean() / std * np.sqrt(TRADING_DAYS)) if std > 0 else 0.0
    gross_win = win_pl.sum() if len(win_pl) else 0
    gross_loss = abs(loss_pl.sum()) if len(loss_pl) else 0
    pf = (gross_win / gross_loss) if gross_loss > 0 else float("inf")

    gross_pl = daily["PL_gross"].sum() if "PL_gross" in daily.columns else pl.sum()
    total_charges = daily["Charges"].sum() if "Charges" in daily.columns else 0.0
    return_pct = (pl.sum() / capital) * 100 if capital else 0.0

    span_years = max((daily["Date"].max() - daily["Date"].min()).days / 365.25, 1 / 365.25)
    cagr = ((1 + pl.sum() / capital) ** (1 / span_years) - 1) * 100 if capital else 0.0

    return {
        "days": len(daily),
        "wins": int(wins),
        "losses": int(losses),
        "win_rate": wins / len(daily) * 100 if len(daily) else 0,
        "gross_pl": gross_pl,
        "total_charges": total_charges,
        "total_pl": pl.sum(),
        "return_pct": return_pct,
        "cagr": cagr,
        "avg_day": pl.mean(),
        "avg_win": win_pl.mean() if len(win_pl) else 0,
        "avg_loss": loss_pl.mean() if len(loss_pl) else 0,
        "best_day": pl.max(),
        "worst_day": pl.min(),
        "sharpe": sharpe,
        "profit_factor": pf,
        "max_drawdown": max_dd,
        "max_dd_pct": (max_dd / capital) * 100,
        "std_daily": std,
        "capital": capital,
    }


def trim_window(
    daily: pd.DataFrame,
    start: str | pd.Timestamp | None = None,
    end: str | pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Filter daily P&L to [start, end] and rebuild cumulative series."""
    df = daily.copy()
    if start is not None:
        df = df[df["Date"] >= pd.Timestamp(start)]
    if end is not None:
        df = df[df["Date"] <= pd.Timestamp(end)]
    df = df.sort_values("Date").reset_index(drop=True)
    df["Cumulative"] = df["PL"].cumsum()
    return df


def _trim_parent(parent: pd.DataFrame, start, end) -> pd.DataFrame:
    df = parent.copy()
    if start is not None:
        df = df[df["Date"] >= pd.Timestamp(start)]
    if end is not None:
        df = df[df["Date"] <= pd.Timestamp(end)]
    return df.reset_index(drop=True)


def align_to_merged(daily: pd.DataFrame, merged: pd.DataFrame) -> pd.DataFrame:
    """Keep only dates present in merged (inner-join alignment)."""
    df = daily[daily["Date"].isin(merged["Date"])].copy()
    df = df.sort_values("Date").reset_index(drop=True)
    df["Cumulative"] = df["PL"].cumsum()
    return df


def align_strategies(
    daily_a: pd.DataFrame,
    daily_b: pd.DataFrame,
    name_a: str = "A",
    name_b: str = "B",
) -> pd.DataFrame:
    """Inner-join on Date; columns PL_{name}, VIX, DOW from strategy A."""
    a = daily_a[["Date", "PL", "VIX", "DOW", "Win"]].rename(
        columns={"PL": f"PL_{name_a}", "Win": f"Win_{name_a}"}
    )
    b = daily_b[["Date", "PL", "Win"]].rename(
        columns={"PL": f"PL_{name_b}", "Win": f"Win_{name_b}"}
    )
    merged = a.merge(b, on="Date", how="inner").sort_values("Date").reset_index(drop=True)
    merged["PL_combined"] = merged[f"PL_{name_a}"] + merged[f"PL_{name_b}"]
    merged["Cumulative_combined"] = merged["PL_combined"].cumsum()
    merged["Win_combined"] = merged["PL_combined"] > 0
    return merged


def correlation_analysis(merged: pd.DataFrame, name_a: str, name_b: str) -> dict:
    pa, pb = merged[f"PL_{name_a}"], merged[f"PL_{name_b}"]
    pearson = pa.corr(pb)

    both_loss = ((pa < 0) & (pb < 0)).sum()
    either_loss = ((pa < 0) | (pb < 0)).sum()
    a_loss = (pa < 0).sum()
    b_loss = (pb < 0).sum()
    both_win = ((pa > 0) & (pb > 0)).sum()

    rolling = merged[["Date", f"PL_{name_a}", f"PL_{name_b}"]].copy()
    rolling["rolling_corr"] = (
        rolling[f"PL_{name_a}"].rolling(60, min_periods=30).corr(rolling[f"PL_{name_b}"])
    )

    # Tail overlap: worst 5% days for each strategy
    q_a = pa.quantile(0.05)
    q_b = pb.quantile(0.05)
    tail_a = set(merged.loc[pa <= q_a, "Date"])
    tail_b = set(merged.loc[pb <= q_b, "Date"])
    tail_overlap = len(tail_a & tail_b)

    return {
        "pearson": pearson,
        "days": len(merged),
        "both_win": int(both_win),
        "both_win_pct": both_win / len(merged) * 100,
        "both_loss": int(both_loss),
        "both_loss_pct": both_loss / len(merged) * 100,
        "either_loss": int(either_loss),
        "a_loss_days": int(a_loss),
        "b_loss_days": int(b_loss),
        "loss_overlap_given_a_loss": both_loss / a_loss * 100 if a_loss else 0,
        "loss_overlap_given_b_loss": both_loss / b_loss * 100 if b_loss else 0,
        "tail_overlap_days": tail_overlap,
        "rolling_corr": rolling[["Date", "rolling_corr"]],
    }


def regime_breakdown(merged: pd.DataFrame, name_a: str, name_b: str) -> pd.DataFrame:
    """Combined vs individual P&L by VIX bucket and day of week."""
    df = merged.copy()
    df["VIX_Bucket"] = pd.cut(
        df["VIX"],
        bins=[0, 12, 14, 16, 18, 20, 100],
        labels=["<12", "12–14", "14–16", "16–18", "18–20", ">20"],
    )
    rows = []
    for grp_col, rtype in [("VIX_Bucket", "VIX"), ("DOW", "DOW")]:
        for key, g in df.groupby(grp_col, observed=True):
            rows.append({
                "Regime": str(key),
                "Type": rtype,
                "Days": len(g),
                f"Avg_{name_a}": g[f"PL_{name_a}"].mean(),
                f"Avg_{name_b}": g[f"PL_{name_b}"].mean(),
                "Avg_Combined": g["PL_combined"].mean(),
                "WinRate_Combined": g["Win_combined"].mean() * 100,
            })
    return pd.DataFrame(rows)


def combined_metrics(merged: pd.DataFrame, capital: float = 500_000) -> dict:
    daily = merged[["Date", "PL_combined", "Cumulative_combined", "Win_combined"]].copy()
    daily.columns = ["Date", "PL", "Cumulative", "Win"]
    return compute_metrics(daily, capital)


def diversification_ratio(
    merged: pd.DataFrame, name_a: str, name_b: str, w_a: float = 1.0, w_b: float = 1.0
) -> float:
    combined = w_a * merged[f"PL_{name_a}"] + w_b * merged[f"PL_{name_b}"]
    vol_combined = combined.std()
    vol_weighted = (
        w_a * merged[f"PL_{name_a}"].std() + w_b * merged[f"PL_{name_b}"].std()
    )
    return vol_combined / vol_weighted if vol_weighted > 0 else 1.0


def optimise_weights(
    merged: pd.DataFrame,
    name_a: str,
    name_b: str,
    capital: float = 500_000,
    step: float = 0.05,
) -> pd.DataFrame:
    """Scan w_a in [0, 1]; w_b = 1 - w_a (capital split). Also include full-size both (1,1)."""
    rows = []
    for w_a in np.arange(0, 1.001, step):
        w_b = 1.0 - w_a
        pl = w_a * merged[f"PL_{name_a}"] + w_b * merged[f"PL_{name_b}"]
        cum = pl.cumsum()
        max_dd = (cum - cum.cummax()).min()
        std = pl.std()
        sharpe = (pl.mean() / std * np.sqrt(TRADING_DAYS)) if std > 0 else 0
        calmar = (pl.sum() / abs(max_dd)) if max_dd < 0 else float("inf")
        rows.append({
            "w_a": round(w_a, 2),
            "w_b": round(w_b, 2),
            "label": f"{int(w_a*100)}/{int(w_b*100)}",
            "total_pl": pl.sum(),
            "avg_day": pl.mean(),
            "sharpe": sharpe,
            "max_dd": max_dd,
            "max_dd_pct": max_dd / capital * 100,
            "calmar": calmar,
            "div_ratio": diversification_ratio(merged, name_a, name_b, w_a, w_b),
        })

    # Full size both strategies (additive, not capital-split)
    pl_full = merged[f"PL_{name_a}"] + merged[f"PL_{name_b}"]
    cum_full = pl_full.cumsum()
    max_dd_full = (cum_full - cum_full.cummax()).min()
    std_full = pl_full.std()
    sharpe_full = (pl_full.mean() / std_full * np.sqrt(TRADING_DAYS)) if std_full > 0 else 0
    rows.append({
        "w_a": 1.0,
        "w_b": 1.0,
        "label": "100/100 (full both)",
        "total_pl": pl_full.sum(),
        "avg_day": pl_full.mean(),
        "sharpe": sharpe_full,
        "max_dd": max_dd_full,
        "max_dd_pct": max_dd_full / capital * 100,
        "calmar": pl_full.sum() / abs(max_dd_full) if max_dd_full < 0 else float("inf"),
        "div_ratio": diversification_ratio(merged, name_a, name_b, 1.0, 1.0),
    })

    return pd.DataFrame(rows)


def load_portfolio_data(base_dir: Path | None = None) -> dict:
    """Load both strategies and run full analysis pipeline."""
    cfg = load_config()
    root = base_dir or Path(__file__).parent.parent
    cap_each = cfg.get("capital_per_strategy", cfg.get("capital", 550_000))
    cap_combined = cfg.get("capital_combined", cap_each * 2)
    charge_rates = cfg.get("charges", {})

    keys = list(cfg["strategies"].keys())
    s_a_cfg = cfg["strategies"][keys[0]]
    s_b_cfg = cfg["strategies"][keys[1]]

    daily_a, parent_a = load_algotest_csv(
        root / s_a_cfg["csv_path"],
        dayfirst=s_a_cfg.get("dayfirst", True),
        charge_rates=charge_rates,
    )
    daily_b, parent_b = load_algotest_csv(
        root / s_b_cfg["csv_path"],
        dayfirst=s_b_cfg.get("dayfirst", True),
        charge_rates=charge_rates,
    )

    window = cfg.get("comparison_window", {})
    win_start = window.get("start")
    win_end = window.get("end")
    if win_start or win_end:
        daily_a = trim_window(daily_a, win_start, win_end)
        daily_b = trim_window(daily_b, win_start, win_end)
        parent_a = _trim_parent(parent_a, win_start, win_end)
        parent_b = _trim_parent(parent_b, win_start, win_end)

    name_a = keys[0]
    name_b = keys[1]
    merged = align_strategies(daily_a, daily_b, name_a, name_b)
    daily_a = align_to_merged(daily_a, merged)
    daily_b = align_to_merged(daily_b, merged)
    overlap_start = merged["Date"].min()
    overlap_end = merged["Date"].max()

    charges_a = daily_a["Charges"].sum() if "Charges" in daily_a.columns else 0
    charges_b = daily_b["Charges"].sum() if "Charges" in daily_b.columns else 0

    return {
        "config": cfg,
        "capital_per_strategy": cap_each,
        "capital_combined": cap_combined,
        "capital": cap_each,
        "name_a": name_a,
        "name_b": name_b,
        "label_a": s_a_cfg["name"],
        "label_b": s_b_cfg["name"],
        "desc_a": s_a_cfg["description"],
        "desc_b": s_b_cfg["description"],
        "overlap_start": overlap_start,
        "overlap_end": overlap_end,
        "comparison_window": window,
        "aligned_days": len(merged),
        "daily_a": daily_a,
        "daily_b": daily_b,
        "parent_a": parent_a,
        "parent_b": parent_b,
        "merged": merged,
        "metrics_a": compute_metrics(daily_a, cap_each),
        "metrics_b": compute_metrics(daily_b, cap_each),
        "metrics_combined": combined_metrics(merged, cap_combined),
        "correlation": correlation_analysis(merged, name_a, name_b),
        "regime": regime_breakdown(merged, name_a, name_b),
        "weights": optimise_weights(merged, name_a, name_b, cap_combined),
        "yearly": yearly_compare(merged, name_a, name_b, cap_combined),
        "total_charges_a": charges_a,
        "total_charges_b": charges_b,
    }
