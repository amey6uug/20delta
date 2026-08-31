import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from portfolio.analysis import load_portfolio_data

d = load_portfolio_data()
ma, mb, mc = d["metrics_a"], d["metrics_b"], d["metrics_combined"]
print(f"Capital: {d['capital_per_strategy']:,} each | {d['capital_combined']:,} combined")
print(f"Strangle: Gross={ma['gross_pl']:,.0f} Charges={ma['total_charges']:,.0f} Net={ma['total_pl']:,.0f} Return={ma['return_pct']:.1f}% CAGR={ma['cagr']:.1f}%")
print(f"Theta:    Gross={mb['gross_pl']:,.0f} Charges={mb['total_charges']:,.0f} Net={mb['total_pl']:,.0f} Return={mb['return_pct']:.1f}% CAGR={mb['cagr']:.1f}%")
print(f"Combined: Net={mc['total_pl']:,.0f} Return={mc['return_pct']:.1f}% CAGR={mc['cagr']:.1f}% Sharpe={mc['sharpe']:.2f}")
