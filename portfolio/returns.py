"""Returns analysis — net of charges, capital-based metrics, period breakdowns."""

from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS = 252


def _span_years(daily: pd.DataFrame) -> float:
    return max((daily["Date"].max() - daily["Date"].min()).days / 365.25, 1 / 365.25)


def _sortino(pl: pd.Series, capital: float) -> float:
    downside = pl[pl < 0]
    if len(downside) == 0 or capital == 0:
        return float("inf") if pl.mean() > 0 else 0.0
    dd_std = downside.std()
    if dd_std <= 0:
        return 0.0
    return (pl.mean() / dd_std) * np.sqrt(TRADING_DAYS)


def _calmar(total_pl: float, max_dd: float, years: float, capital: float) -> float:
    if max_dd >= 0 or capital == 0 or years <= 0:
        return float("inf") if total_pl > 0 else 0.0
    cagr = ((1 + total_pl / capital) ** (1 / years) - 1)
    return cagr / abs(max_dd / capital)


def enrich_daily_returns(daily: pd.DataFrame, capital: float) -> pd.DataFrame:
    df = daily.copy()
    df["Return_pct"] = df["PL"] / capital * 100
    df["CumReturn_pct"] = df["Return_pct"].cumsum()
    if "PL_gross" in df.columns:
        df["GrossReturn_pct"] = df["PL_gross"] / capital * 100
    roll_max = df["Cumulative"].cummax()
    df["Drawdown"] = df["Cumulative"] - roll_max
    df["Drawdown_pct"] = df["Drawdown"] / capital * 100
    return df


def _daily_merge_cols(daily: pd.DataFrame) -> pd.DataFrame:
    """Date, PL, Charges, PL_gross — safe when charges not computed."""
    cols = daily[["Date", "PL"]].copy()
    cols["Charges"] = daily["Charges"] if "Charges" in daily.columns else 0.0
    cols["PL_gross"] = daily["PL_gross"] if "PL_gross" in daily.columns else daily["PL"]
    return cols


def enrich_merged(merged: pd.DataFrame, daily_a: pd.DataFrame, daily_b: pd.DataFrame, name_a: str, name_b: str) -> pd.DataFrame:
    m = merged.copy()
    for daily, name in [(daily_a, name_a), (daily_b, name_b)]:
        cols = _daily_merge_cols(daily)
        cols = cols.rename(columns={
            "PL": f"PL_{name}",
            "Charges": f"Charges_{name}",
            "PL_gross": f"Gross_{name}",
        })
        m = m.merge(cols, on="Date", how="left")
    m["Charges_combined"] = m[f"Charges_{name_a}"].fillna(0) + m[f"Charges_{name_b}"].fillna(0)
    m["Gross_combined"] = m[f"Gross_{name_a}"].fillna(0) + m[f"Gross_{name_b}"].fillna(0)
    return m


def summary_comparison(
    metrics_a: dict,
    metrics_b: dict,
    metrics_c: dict,
    label_a: str,
    label_b: str,
    cap_a: float,
    cap_b: float,
    cap_c: float,
) -> pd.DataFrame:
    years_a = metrics_a.get("days", 1) / TRADING_DAYS
    years_b = metrics_b.get("days", 1) / TRADING_DAYS

    def row(label, m, cap):
        yrs = max(m["days"] / TRADING_DAYS, 1 / TRADING_DAYS)
        return {
            "Strategy": label,
            "Capital (₹)": int(cap),
            "Days": m["days"],
            "Gross P&L (₹)": int(m.get("gross_pl", m["total_pl"])),
            "Charges (₹)": int(m.get("total_charges", 0)),
            "Net P&L (₹)": int(m["total_pl"]),
            "Total Return (%)": round(m.get("return_pct", 0), 2),
            "CAGR (%)": round(m.get("cagr", 0), 2),
            "Avg/Day (₹)": int(m["avg_day"]),
            "Avg/Day (%)": round(m["avg_day"] / cap * 100, 3) if cap else 0,
            "Win Rate (%)": round(m["win_rate"], 1),
            "Sharpe": round(m["sharpe"], 2),
            "Max DD (₹)": int(m["max_drawdown"]),
            "Max DD (%)": round(m["max_dd_pct"], 2),
            "Profit Factor": round(m["profit_factor"], 2),
            "Charges / Gross (%)": round(m.get("total_charges", 0) / m.get("gross_pl", 1) * 100, 2)
            if m.get("gross_pl", 0) else 0,
            "Net / Capital (×)": round(m["total_pl"] / cap, 2) if cap else 0,
        }

    return pd.DataFrame([
        row(label_a, metrics_a, cap_a),
        row(label_b, metrics_b, cap_b),
        row("Combined (both full)", metrics_c, cap_c),
    ])


def monthly_returns(daily: pd.DataFrame, capital: float) -> pd.DataFrame:
    df = daily.copy()
    df["Month"] = df["Date"].dt.to_period("M")
    g = df.groupby("Month").agg(
        Net_PL=("PL", "sum"),
        Gross_PL=("PL_gross", "sum") if "PL_gross" in df.columns else ("PL", "sum"),
        Charges=("Charges", "sum") if "Charges" in df.columns else ("PL", lambda x: 0),
        Days=("PL", "count"),
        Wins=("Win", "sum"),
    ).reset_index()
    g["Month_str"] = g["Month"].astype(str)
    g["Return (%)"] = g["Net_PL"] / capital * 100
    g["Win Rate (%)"] = g["Wins"] / g["Days"] * 100
    g["Cum Return (%)"] = g["Return (%)"].cumsum()
    return g.rename(columns={"Net_PL": "Net P&L (₹)", "Gross_PL": "Gross P&L (₹)", "Charges": "Charges (₹)"})


def monthly_comparison(daily_a, daily_b, merged, cap_a, cap_b, cap_c, name_a, name_b, label_a, label_b):
    ma = monthly_returns(daily_a, cap_a)[["Month_str", "Net P&L (₹)", "Return (%)"]].rename(
        columns={"Net P&L (₹)": f"{label_a} P&L", "Return (%)": f"{label_a} Ret %"}
    )
    mb = monthly_returns(daily_b, cap_b)[["Month_str", "Net P&L (₹)", "Return (%)"]].rename(
        columns={"Net P&L (₹)": f"{label_b} P&L", "Return (%)": f"{label_b} Ret %"}
    )
    mc = monthly_returns(
        merged.rename(columns={"PL_combined": "PL", "Win_combined": "Win"}).assign(
            PL_gross=merged.get("Gross_combined", merged["PL_combined"]),
            Charges=merged.get("Charges_combined", 0),
        ),
        cap_c,
    )[["Month_str", "Net P&L (₹)", "Return (%)"]].rename(
        columns={"Net P&L (₹)": "Combined P&L", "Return (%)": "Combined Ret %"}
    )
    out = ma.merge(mb, on="Month_str").merge(mc, on="Month_str")
    return out


def yearly_returns_pct(daily: pd.DataFrame, capital: float) -> pd.DataFrame:
    df = daily.copy()
    df["Year"] = df["Date"].dt.year
    rows = []
    for year, g in df.groupby("Year"):
        net = g["PL"].sum()
        gross = g["PL_gross"].sum() if "PL_gross" in g.columns else net
        ch = g["Charges"].sum() if "Charges" in g.columns else 0
        rows.append({
            "Year": int(year),
            "Days": len(g),
            "Gross P&L (₹)": int(gross),
            "Charges (₹)": int(ch),
            "Net P&L (₹)": int(net),
            "Return (%)": round(net / capital * 100, 2),
            "Win Rate (%)": round(g["Win"].mean() * 100, 1),
        })
    return pd.DataFrame(rows)


def rolling_metrics(daily: pd.DataFrame, capital: float, window: int = 60) -> pd.DataFrame:
    df = daily.copy()
    df["RollReturn_pct"] = df["PL"].rolling(window).sum() / capital * 100
    roll_std = df["PL"].rolling(window).std()
    df["RollSharpe"] = (df["PL"].rolling(window).mean() / roll_std * np.sqrt(TRADING_DAYS)).where(roll_std > 0)
    return df[["Date", "RollReturn_pct", "RollSharpe"]]


def charges_breakdown(daily_a, daily_b, cap_a, cap_b, label_a, label_b):
    return pd.DataFrame([
        {
            "Strategy": label_a,
            "Capital": int(cap_a),
            "Gross P&L": int(daily_a["PL_gross"].sum() if "PL_gross" in daily_a.columns else daily_a["PL"].sum()),
            "Total Charges": int(daily_a["Charges"].sum() if "Charges" in daily_a.columns else 0),
            "Net P&L": int(daily_a["PL"].sum()),
            "Charge Drag (%)": round(daily_a["Charges"].sum() / daily_a["PL_gross"].sum() * 100, 2)
            if "PL_gross" in daily_a.columns and daily_a["PL_gross"].sum() else 0,
            "Return Before Charges (%)": round(daily_a["PL_gross"].sum() / cap_a * 100, 2)
            if "PL_gross" in daily_a.columns else 0,
            "Return After Charges (%)": round(daily_a["PL"].sum() / cap_a * 100, 2),
        },
        {
            "Strategy": label_b,
            "Capital": int(cap_b),
            "Gross P&L": int(daily_b["PL_gross"].sum() if "PL_gross" in daily_b.columns else daily_b["PL"].sum()),
            "Total Charges": int(daily_b["Charges"].sum() if "Charges" in daily_b.columns else 0),
            "Net P&L": int(daily_b["PL"].sum()),
            "Charge Drag (%)": round(daily_b["Charges"].sum() / daily_b["PL_gross"].sum() * 100, 2)
            if "PL_gross" in daily_b.columns and daily_b["PL_gross"].sum() else 0,
            "Return Before Charges (%)": round(daily_b["PL_gross"].sum() / cap_b * 100, 2)
            if "PL_gross" in daily_b.columns else 0,
            "Return After Charges (%)": round(daily_b["PL"].sum() / cap_b * 100, 2),
        },
    ])


def _resolve_capitals(data: dict) -> tuple[float, float]:
    cfg = data.get("config", {})
    cap_each = data.get(
        "capital_per_strategy",
        cfg.get("capital_per_strategy", cfg.get("capital", 550_000)),
    )
    cap_combined = data.get("capital_combined", cfg.get("capital_combined", cap_each * 2))
    return float(cap_each), float(cap_combined)


def build_returns_analysis(data: dict) -> dict:
    """Full returns bundle from load_portfolio_data() output."""
    daily_a = data["daily_a"]
    daily_b = data["daily_b"]
    merged = data["merged"]
    na, nb = data["name_a"], data["name_b"]
    la, lb = data["label_a"], data["label_b"]
    cap_a, cap_c = _resolve_capitals(data)
    cap_b = cap_a

    merged_enriched = enrich_merged(merged, daily_a, daily_b, na, nb)
    combined_daily = merged_enriched[["Date", "PL_combined", "Win_combined", "Cumulative_combined"]].copy()
    combined_daily.columns = ["Date", "PL", "Win", "Cumulative"]
    if "Gross_combined" in merged_enriched.columns:
        combined_daily["PL_gross"] = merged_enriched["Gross_combined"]
    if "Charges_combined" in merged_enriched.columns:
        combined_daily["Charges"] = merged_enriched["Charges_combined"]

    ret_a = enrich_daily_returns(daily_a, cap_a)
    ret_b = enrich_daily_returns(daily_b, cap_b)
    ret_c = enrich_daily_returns(combined_daily, cap_c)

    def risk_row(label, daily, m, cap):
        yrs = _span_years(daily)
        mon = monthly_returns(daily, cap)
        return {
            "Strategy": label,
            "Sortino": round(_sortino(daily["PL"], cap), 2),
            "Calmar": round(_calmar(m["total_pl"], m["max_drawdown"], yrs, cap), 2),
            "Ann. Vol (%)": round(daily["PL"].std() / cap * np.sqrt(TRADING_DAYS) * 100, 2),
            "Best Month (₹)": int(mon["Net P&L (₹)"].max()),
            "Worst Month (₹)": int(mon["Net P&L (₹)"].min()),
            "+ve Months": f"{int((mon['Net P&L (₹)'] > 0).sum())}/{len(mon)}",
            "Avg Month Ret (%)": round(mon["Return (%)"].mean(), 2),
        }

    risk_df = pd.DataFrame([
        risk_row(la, daily_a, data["metrics_a"], cap_a),
        risk_row(lb, daily_b, data["metrics_b"], cap_b),
        risk_row("Combined", combined_daily, data["metrics_combined"], cap_c),
    ])

    return {
        "summary": summary_comparison(
            data["metrics_a"], data["metrics_b"], data["metrics_combined"],
            la, lb, cap_a, cap_b, cap_c,
        ),
        "risk_adjusted": risk_df,
        "charges": charges_breakdown(daily_a, daily_b, cap_a, cap_b, la, lb),
        "monthly_a": monthly_returns(daily_a, cap_a),
        "monthly_b": monthly_returns(daily_b, cap_b),
        "monthly_c": monthly_returns(combined_daily, cap_c),
        "monthly_compare": monthly_comparison(
            daily_a, daily_b, merged_enriched, cap_a, cap_b, cap_c, na, nb, la, lb,
        ),
        "yearly_a": yearly_returns_pct(daily_a, cap_a),
        "yearly_b": yearly_returns_pct(daily_b, cap_b),
        "yearly_c": yearly_returns_pct(combined_daily, cap_c),
        "rolling_a": rolling_metrics(daily_a, cap_a),
        "rolling_b": rolling_metrics(daily_b, cap_b),
        "rolling_c": rolling_metrics(combined_daily, cap_c),
        "equity_a": ret_a,
        "equity_b": ret_b,
        "equity_c": ret_c,
        "merged_enriched": merged_enriched,
        "combined_daily": combined_daily,
    }
