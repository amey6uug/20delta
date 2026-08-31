"""
Indian F&O statutory charges (Flattrade: brokerage = ₹0).

Sources (2024–2026):
- STT: Finance Act / NSE circular — options sell premium only
  · 0.0625% until 31 Mar 2023
  · 0.10% from 1 Apr 2023 – 31 Mar 2026
  · 0.15% from 1 Apr 2026
- Stamp: 0.003% on buy side (equity options, uniform)
- SEBI: ₹10 per crore of turnover (both sides)
- NSE index/stock options exchange: ₹35.03/lakh = 0.03503% per side (Oct 2024 flat rate)
- BSE Sensex/Bankex options: ₹3,250/crore = 0.0325% per side (from 1 Oct 2024)
- BSE Sensex/Bankex options before Oct 2024: ₹500/crore = 0.005% (minimum slab)
- IPFT (NSE): ₹50 per crore of premium turnover (both sides)
- GST: 18% on brokerage + exchange + SEBI (+ IPFT on NSE)
- STT and stamp duty are NOT in GST base
"""

from __future__ import annotations

from datetime import date

import pandas as pd

DEFAULT_RATES = {
    "brokerage_per_order": 0,
    "gst_rate": 0.18,
    "sebi_per_crore": 10,
    "stamp_buy_pct": 0.00003,           # 0.003% equity options, buy side
    "ipft_per_crore": 50,               # NSE IPFT on premium turnover
    "nse_options_exchange_pct": 0.0003503,   # ₹35.03 / lakh per side (Oct 2024+)
    "nse_options_exchange_pct_legacy": 0.000495,  # ₹4,950 / crore top slab (pre Oct 2024)
    "nse_exchange_change_date": "2024-10-01",
    "bse_sensex_options_exchange_pct": 0.000325,  # ₹3,250 / crore per side (Oct 2024+)
    "bse_sensex_options_exchange_pct_legacy": 0.00005,  # ₹500 / crore min slab (pre Oct 2024)
    "bse_exchange_change_date": "2024-10-01",
    "stt_sell_schedule": [
        ("2026-04-01", 0.0015),
        ("2023-04-01", 0.0010),
        ("1900-01-01", 0.000625),
    ],
}


def _exchange(strike: float) -> str:
    if pd.notna(strike) and strike > 40_000:
        return "bse"
    return "nse"


def stt_rate_on(trade_date: date | pd.Timestamp, rates: dict | None = None) -> float:
    """STT on sale of options — premium, sell side only."""
    rates = rates or DEFAULT_RATES
    d = pd.Timestamp(trade_date).date()
    for from_str, rate in rates["stt_sell_schedule"]:
        if d >= pd.Timestamp(from_str).date():
            return rate
    return 0.000625


def exchange_pct_on(trade_date: date | pd.Timestamp, exchange: str, rates: dict | None = None) -> float:
    rates = rates or DEFAULT_RATES
    d = pd.Timestamp(trade_date)
    if exchange == "nse":
        change = pd.Timestamp(rates.get("nse_exchange_change_date", "2024-10-01"))
        if d >= change:
            return rates["nse_options_exchange_pct"]
        return rates.get("nse_options_exchange_pct_legacy", rates["nse_options_exchange_pct"])
    change = pd.Timestamp(rates["bse_exchange_change_date"])
    if d >= change:
        return rates["bse_sensex_options_exchange_pct"]
    return rates["bse_sensex_options_exchange_pct_legacy"]


def leg_charges(
    entry_price: float,
    exit_price: float,
    qty: float,
    side: str,
    strike: float,
    trade_date: date | pd.Timestamp | None = None,
    rates: dict | None = None,
) -> dict:
    """
    Round-trip charges for one short option leg.
    Returns component breakdown + total.
    """
    rates = rates or DEFAULT_RATES
    if qty <= 0 or entry_price <= 0:
        return _empty_charges()

    trade_date = trade_date or pd.Timestamp("2024-01-01")
    exchange = _exchange(strike)
    ex_pct = exchange_pct_on(trade_date, exchange, rates)

    entry_turn = entry_price * qty
    exit_turn = max(exit_price, 0) * qty
    total_turn = entry_turn + exit_turn
    side = str(side).strip().lower()

    stt = stamp = exch = sebi = ipft = 0.0

    # Entry
    if side.startswith("s"):
        stt += entry_turn * stt_rate_on(trade_date, rates)
    else:
        stamp += entry_turn * rates["stamp_buy_pct"]
    exch += entry_turn * ex_pct
    sebi += entry_turn * rates["sebi_per_crore"] / 1e7

    # Exit (short options: buy to close)
    stamp += exit_turn * rates["stamp_buy_pct"]
    exch += exit_turn * ex_pct
    sebi += exit_turn * rates["sebi_per_crore"] / 1e7

    ipft += total_turn * rates["ipft_per_crore"] / 1e7

    gst_base = exch + sebi + rates["brokerage_per_order"] * 2
    gst = rates["gst_rate"] * gst_base

    total = stt + stamp + exch + sebi + ipft + gst
    return {
        "stt": stt,
        "stamp": stamp,
        "exchange": exch,
        "sebi": sebi,
        "ipft": ipft,
        "gst": gst,
        "total": total,
    }


def _empty_charges() -> dict:
    keys = ["stt", "stamp", "exchange", "sebi", "ipft", "gst", "total"]
    return dict.fromkeys(keys, 0.0)


def apply_charges_to_legs(child: pd.DataFrame, rates: dict | None = None, dayfirst: bool = True) -> pd.DataFrame:
    df = child.copy()
    df["Entry Price"] = pd.to_numeric(df["Entry Price"], errors="coerce")
    df["Exit Price"] = pd.to_numeric(df["Exit Price"], errors="coerce")
    df["Qty"] = pd.to_numeric(df["Qty"], errors="coerce")
    df["Strike"] = pd.to_numeric(df["Strike"], errors="coerce")
    df["Leg_PL"] = pd.to_numeric(df["P/L"], errors="coerce").fillna(0)
    df["TradeDate"] = pd.to_datetime(df["Entry Date"].astype(str).str.strip(), dayfirst=dayfirst)

    breakdowns = df.apply(
        lambda r: leg_charges(
            r["Entry Price"], r["Exit Price"], r["Qty"],
            r.get("B/S", "Sell"), r["Strike"], r["TradeDate"], rates,
        )
        if pd.notna(r["Entry Price"]) and pd.notna(r["Qty"]) else _empty_charges(),
        axis=1,
    )
    for key in ["stt", "stamp", "exchange", "sebi", "ipft", "gst", "total"]:
        df[key] = breakdowns.apply(lambda x, k=key: x[k])

    df["Charges"] = df["total"]
    df["Net_PL"] = df["Leg_PL"] - df["Charges"]
    return df


def daily_pl_with_charges(
    child: pd.DataFrame,
    parent: pd.DataFrame,
    dayfirst: bool = True,
    rates: dict | None = None,
) -> pd.DataFrame:
    legs = apply_charges_to_legs(child, rates, dayfirst=dayfirst)
    legs["Date"] = pd.to_datetime(legs["Entry Date"].astype(str).str.strip(), dayfirst=dayfirst)

    leg_daily = legs.groupby("Date").agg(
        PL_gross=("Leg_PL", "sum"),
        Charges=("Charges", "sum"),
        PL=("Net_PL", "sum"),
        STT=("stt", "sum"),
        Stamp=("stamp", "sum"),
        Exchange=("exchange", "sum"),
        SEBI=("sebi", "sum"),
        IPFT=("ipft", "sum"),
        GST=("gst", "sum"),
    ).reset_index()

    parent_daily = parent.groupby("Date").agg(VIX=("VIX", "first")).reset_index()
    daily = leg_daily.merge(parent_daily, on="Date", how="left")
    daily = daily.sort_values("Date").reset_index(drop=True)
    daily["Cumulative"] = daily["PL"].cumsum()
    daily["Win"] = daily["PL"] > 0
    daily["DOW"] = daily["Date"].dt.day_name()
    return daily


def charges_summary(legs: pd.DataFrame) -> pd.DataFrame:
    """Aggregate charge breakdown (Algotest-style)."""
    cols = ["stt", "stamp", "exchange", "sebi", "ipft", "gst", "Charges"]
    available = [c for c in cols if c in legs.columns]
    total = legs[available].sum()
    rows = [
        {"Component": "STT", "Amount": total.get("stt", 0)},
        {"Component": "Stamp Duty", "Amount": total.get("stamp", 0)},
        {"Component": "Exchange Charges", "Amount": total.get("exchange", 0)},
        {"Component": "SEBI Charges", "Amount": total.get("sebi", 0)},
        {"Component": "IPFT", "Amount": total.get("ipft", 0)},
        {"Component": "Clearing Charges", "Amount": 0.0},
        {"Component": "GST (18%)", "Amount": total.get("gst", 0)},
        {"Component": "Total", "Amount": total.get("Charges", total.get("total", 0))},
    ]
    return pd.DataFrame(rows)


def apply_charges_to_live(
    live: pd.DataFrame,
    rates: dict | None = None,
    *,
    instr_keys: list[str] | None = None,
) -> pd.DataFrame:
    """
    Net live_trades*.csv rows using the same Flattrade statutory model as backtest.

    CSV ``PL`` is treated as gross (sell premium − buy premium) × qty.
    Returns a copy with ``PL_gross``, ``Charges``, net ``PL``, and recomputed
    ``Instr_PL`` / ``Day_PL``. Idempotent if ``PL_gross`` already exists.
    """
    if live is None or live.empty:
        return live

    df = live.copy()
    rates = rates or DEFAULT_RATES

    if "PL_gross" in df.columns:
        gross = pd.to_numeric(df["PL_gross"], errors="coerce").fillna(0.0)
    else:
        gross = pd.to_numeric(df["PL"], errors="coerce").fillna(0.0)

    df["PL_gross"] = gross

    entry = pd.to_numeric(df["Entry_Price"], errors="coerce")
    exit_ = pd.to_numeric(df["Exit_Price"], errors="coerce")
    qty = pd.to_numeric(df["Qty"], errors="coerce")
    strike = pd.to_numeric(df["Strike"], errors="coerce")
    dates = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce")

    charges = []
    for i in range(len(df)):
        charges.append(
            leg_charges(
                float(entry.iloc[i] or 0),
                float(exit_.iloc[i] or 0),
                float(qty.iloc[i] or 0),
                "Sell",
                float(strike.iloc[i] or 0),
                dates.iloc[i],
                rates,
            )["total"]
        )
    df["Charges"] = charges
    df["PL"] = (df["PL_gross"] - df["Charges"]).round(2)

    # Rebuild instrument / day aggregates from net leg P&L
    if instr_keys is None:
        # Strangle: per index per day. Theta: per entry slot per day.
        if "Entry_Time" in df.columns and df["Index"].nunique() <= 1:
            slot = (
                df["Entry_Time"].astype(str).str.strip()
                .apply(lambda t: "9:45" if t.startswith("09:4") else (
                    "11:45" if t.startswith("11:4") else t
                ))
            )
            instr_group = [dates.dt.normalize(), slot]
        else:
            instr_group = [dates.dt.normalize(), df["Index"]]
    else:
        instr_group = instr_keys

    df["Instr_PL"] = df.groupby(instr_group, sort=False)["PL"].transform("sum").round(2)
    df["Day_PL"] = df.groupby(dates.dt.normalize(), sort=False)["PL"].transform("sum").round(2)
    return df
