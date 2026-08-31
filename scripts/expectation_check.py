import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from portfolio.analysis import load_portfolio_data

d = load_portfolio_data()
cap = d["capital_per_strategy"]
cap_c = d["capital_combined"]
ma, mb, mc = d["metrics_a"], d["metrics_b"], d["metrics_combined"]
merged = d["merged"]
na, nb = d["name_a"], d["name_b"]
y = d["yearly"].copy()

y["Ret_Strangle_pct"] = y[f"PL_{na}"] / cap * 100
y["Ret_Theta_pct"] = y[f"PL_{nb}"] / cap * 100
y["Ret_Combined_pct"] = y["PL_Combined"] / cap_c * 100

print("=== YEARLY RETURN POST CHARGES ===")
print(y[["Year", "Days", "Ret_Strangle_pct", "Ret_Theta_pct", "Ret_Combined_pct"]].round(1).to_string(index=False))

print("\n=== DRAWDOWN (max DD as % of capital) ===")
print(f"Strangle alone: {ma['max_drawdown']:,.0f} ({ma['max_dd_pct']:.2f}%)")
print(f"Theta alone:    {mb['max_drawdown']:,.0f} ({mb['max_dd_pct']:.2f}%)")
print(f"Combined:       {mc['max_drawdown']:,.0f} ({mc['max_dd_pct']:.2f}%)")

daily_c = merged[["Date", "PL_combined"]].copy()
daily_c["Cum"] = daily_c["PL_combined"].cumsum()
daily_c["Peak"] = daily_c["Cum"].cummax()
daily_c["DD"] = daily_c["Cum"] - daily_c["Peak"]
daily_c["DD_pct"] = daily_c["DD"] / cap_c * 100

print("\nIntra-year max drawdown (combined on 11L):")
for yr in [2024, 2025, 2026]:
    g = daily_c[daily_c["Date"].dt.year == yr]
    if len(g):
        print(f"  {yr}: {g['DD'].min():,.0f} ({g['DD_pct'].min():.2f}%)")

span = (merged["Date"].max() - merged["Date"].min()).days / 365.25
print(f"\n=== CAGR (full {span:.2f}-yr window, post charges) ===")
for label, m, c in [("Strangle", ma, cap), ("Theta", mb, cap), ("Combined", mc, cap_c)]:
    cagr = ((1 + m["total_pl"] / c) ** (1 / span) - 1) * 100
    print(f"{label}: CAGR {cagr:.1f}%  (total return {m['return_pct']:.1f}%)")

print("\n=== 12% YEARLY FLOOR (combined, post charges) ===")
for _, r in y.iterrows():
    yr = int(r["Year"])
    ret = r["Ret_Combined_pct"]
    ann = ret * (252 / r["Days"]) if r["Days"] < 240 else ret
    if yr == 2026:
        status = "on pace" if ann >= 12 else "below pace (annualised)"
    else:
        status = "PASS" if ret >= 12 else "MISS"
    print(f"  {yr}: {ret:.1f}% calendar | annualised ~{ann:.1f}% -> {status}")

corr = d["correlation"]
print("\n=== DIVERSIFICATION ===")
print(f"Pearson daily correlation: {corr['pearson']:.3f}")
print(f"Combined Sharpe: {mc['sharpe']:.2f}  (Strangle {ma['sharpe']:.2f}, Theta {mb['sharpe']:.2f})")
print(f"DD reduction: Strangle {ma['max_dd_pct']:.2f}% -> Combined {mc['max_dd_pct']:.2f}% of capital")
