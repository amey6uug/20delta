"""Margin Calculator for Options Portfolios.

Provides estimated SPAN & Exposure margins, hedge benefits, premium turnover,
and capital utilization (clearly labeled as 'Estimated Margin').
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class MarginBreakdown:
    underlying: str
    gross_exposure: float
    naked_short_margin: float
    hedge_benefit: float
    net_margin_required: float
    premium_receivable_or_payable: float
    total_capital: float
    available_capital_after_trade: float
    margin_utilization_pct: float
    is_sufficient_capital: bool
    status_label: str = "Estimated Margin (Indicative, Non-Certified)"


class MarginCalculator:
    # Approximate base margin rates per lot for Indian Index Options
    # NIFTY ~ ₹1.2L naked short per lot, with OTM hedge reducing to ~₹40k-50k
    # SENSEX ~ ₹1.4L naked short per lot, with OTM hedge reducing to ~₹50k-60k
    BASE_NAKED_MARGIN_PER_LOT = {
        "NIFTY": 125_000.0,
        "SENSEX": 140_000.0,
        "BANKNIFTY": 110_000.0,
    }

    LOT_SIZES = {
        "NIFTY": 65,
        "SENSEX": 20,
        "BANKNIFTY": 15,
    }

    @classmethod
    def calculate_margin(
        cls,
        underlying: str,
        short_quantity: int,
        short_premium: float,
        hedge_quantity: int = 0,
        hedge_premium: float = 0.0,
        hedge_distance_points: float = 300.0,
        strategy_capital: float = 1_000_000.0,
    ) -> MarginBreakdown:
        """
        Calculate estimated margin required, hedge relief, and capital availability.
        """
        underlying = underlying.upper().strip()
        lot_size = cls.LOT_SIZES.get(underlying, 25)
        base_per_lot = cls.BASE_NAKED_MARGIN_PER_LOT.get(underlying, 125_000.0)

        num_short_lots = max(1, short_quantity // lot_size) if short_quantity > 0 else 0
        num_hedge_lots = max(1, hedge_quantity // lot_size) if hedge_quantity > 0 else 0

        naked_margin = num_short_lots * base_per_lot

        # Hedge benefit calculation based on distance and hedge lot coverage
        if num_hedge_lots > 0 and num_short_lots > 0:
            covered_lots = min(num_short_lots, num_hedge_lots)
            # Closer hedge gives higher relief (up to ~65% relief)
            relief_ratio = max(0.40, min(0.70, 1.0 - (hedge_distance_points / 1000.0)))
            hedge_benefit = covered_lots * base_per_lot * relief_ratio
        else:
            hedge_benefit = 0.0

        net_margin = max(0.0, naked_margin - hedge_benefit)

        # Net premium cash flow
        premium_flow = (short_premium * short_quantity) - (hedge_premium * hedge_quantity)
        gross_exposure = (short_premium * short_quantity) + (hedge_premium * hedge_quantity)

        available_after = strategy_capital - net_margin
        utilization_pct = (net_margin / strategy_capital * 100.0) if strategy_capital > 0 else 0.0
        sufficient = available_after >= 0

        return MarginBreakdown(
            underlying=underlying,
            gross_exposure=round(gross_exposure, 2),
            naked_short_margin=round(naked_margin, 2),
            hedge_benefit=round(hedge_benefit, 2),
            net_margin_required=round(net_margin, 2),
            premium_receivable_or_payable=round(premium_flow, 2),
            total_capital=round(strategy_capital, 2),
            available_capital_after_trade=round(available_after, 2),
            margin_utilization_pct=round(utilization_pct, 2),
            is_sufficient_capital=sufficient,
        )
