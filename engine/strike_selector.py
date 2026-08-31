"""Dynamic Strike Selection Engine for NIFTY and SENSEX Options.

Features:
- Dynamic ATM, OTM, ITM calculation based on underlying index spot.
- DTE-aware distance calculation (configurable OTM, Near-Expiry, and Hedge points).
- Hard safety check: SENSEX ATM short prevention.
- Generates main legs and hedge legs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from engine.calendar import calculate_dte, get_expiry_date
from engine.models import (
    LegType,
    OptionLeg,
    OptionType,
    StrategyConfig,
    TransactionType,
)


@dataclass
class StrikeSelectionResult:
    underlying: str
    spot_price: float
    atm_strike: float
    expiry: str
    dte: int
    ce_main_strike: float
    pe_main_strike: float
    ce_hedge_strike: Optional[float]
    pe_hedge_strike: Optional[float]
    is_valid: bool
    rejection_reason: str = ""


class StrikeSelector:
    STRIKE_STEPS = {
        "NIFTY": 50,
        "SENSEX": 100,
        "BANKNIFTY": 100,
    }

    LOT_SIZES = {
        "NIFTY": 65,  # active lot size (or 75 / 25 depending on contract)
        "SENSEX": 20, # active BSE lot size
        "BANKNIFTY": 15,
    }

    @classmethod
    def get_strike_step(cls, underlying: str) -> int:
        return cls.STRIKE_STEPS.get(underlying.upper().strip(), 50)

    @classmethod
    def get_lot_size(cls, underlying: str) -> int:
        return cls.LOT_SIZES.get(underlying.upper().strip(), 25)

    @classmethod
    def calculate_atm_strike(cls, underlying: str, spot_price: float) -> float:
        """Calculate the nearest At-The-Money (ATM) strike price."""
        step = cls.get_strike_step(underlying)
        return round(round(spot_price / step) * step, 2)

    @classmethod
    def select_strikes(
        cls,
        underlying: str,
        spot_price: float,
        trading_date: str,
        config: StrategyConfig,
        custom_expiry: Optional[str] = None,
    ) -> StrikeSelectionResult:
        """
        Dynamically determine strikes based on Spot, DTE, and Config.

        NIFTY Rules:
        - DTE > 1: OTM distance = nifty_otm_distance (default 200)
        - DTE <= 1: OTM distance = nifty_near_expiry_distance (default 100)
        - Hedge: nifty_hedge_distance (default 300)

        SENSEX Rules:
        - DTE > 1: OTM distance = sensex_otm_distance (default 300)
        - DTE <= 1: OTM distance = sensex_near_expiry_distance (default 100)
        - Hedge: sensex_hedge_distance (default 500)
        - SAFETY: ATM Short is PROHIBITED.
        """
        underlying = underlying.upper().strip()
        step = cls.get_strike_step(underlying)
        atm_strike = cls.calculate_atm_strike(underlying, spot_price)

        expiry_date = custom_expiry or get_expiry_date(underlying, trading_date)
        dte = calculate_dte(trading_date, expiry_date)

        if underlying == "NIFTY":
            otm_dist = config.nifty_near_expiry_distance if dte <= 1 else config.nifty_otm_distance
            hedge_dist = config.nifty_hedge_distance
        elif underlying == "SENSEX":
            otm_dist = config.sensex_near_expiry_distance if dte <= 1 else config.sensex_otm_distance
            hedge_dist = config.sensex_hedge_distance
        else:
            otm_dist = 200
            hedge_dist = 300

        # Adjust OTM distance to align with strike step
        otm_dist = round(round(otm_dist / step) * step)
        hedge_dist = round(round(hedge_dist / step) * step)

        ce_strike = atm_strike + otm_dist
        pe_strike = atm_strike - otm_dist

        # Safety Check: Never short SENSEX ATM
        if underlying == "SENSEX" and (ce_strike == atm_strike or pe_strike == atm_strike):
            return StrikeSelectionResult(
                underlying=underlying,
                spot_price=spot_price,
                atm_strike=atm_strike,
                expiry=str(expiry_date),
                dte=dte,
                ce_main_strike=ce_strike,
                pe_main_strike=pe_strike,
                ce_hedge_strike=None,
                pe_hedge_strike=None,
                is_valid=False,
                rejection_reason="SENSEX ATM SHORTING IS PROHIBITED BY STRATEGY RISK RULES.",
            )

        ce_hedge = (ce_strike + hedge_dist) if config.hedge_required else None
        pe_hedge = (pe_strike - hedge_dist) if config.hedge_required else None

        return StrikeSelectionResult(
            underlying=underlying,
            spot_price=spot_price,
            atm_strike=atm_strike,
            expiry=str(expiry_date),
            dte=dte,
            ce_main_strike=ce_strike,
            pe_main_strike=pe_strike,
            ce_hedge_strike=ce_hedge,
            pe_hedge_strike=pe_hedge,
            is_valid=True,
        )

    @classmethod
    def create_legs_from_selection(
        cls,
        selection: StrikeSelectionResult,
        config: StrategyConfig,
        entry_time_str: str,
        ce_main_premium: float,
        pe_main_premium: float,
        ce_hedge_premium: float = 0.0,
        pe_hedge_premium: float = 0.0,
        num_lots: int = 1,
    ) -> List[OptionLeg]:
        """Create OptionLeg objects with stop loss calculations for a new trade setup."""
        if not selection.is_valid:
            raise ValueError(f"Cannot create legs from invalid selection: {selection.rejection_reason}")

        lot_size = cls.get_lot_size(selection.underlying)
        total_qty = lot_size * num_lots
        legs = []

        # 1. Hedge Legs (if configured, placed first)
        if config.hedge_required and selection.ce_hedge_strike and selection.pe_hedge_strike:
            ce_h = OptionLeg(
                leg_id=f"{config.strategy_id}_{selection.underlying}_CE_HEDGE",
                strategy_id=config.strategy_id,
                underlying=selection.underlying,
                expiry=selection.expiry,
                strike=selection.ce_hedge_strike,
                option_type=OptionType.CE,
                transaction_type=TransactionType.BUY,
                leg_type=LegType.HEDGE,
                quantity=total_qty,
                entry_price=ce_hedge_premium,
                entry_time=entry_time_str,
                current_price=ce_hedge_premium,
                stop_loss_percent=config.stop_loss_percent,
                hard_stop_loss_percent=config.hard_stop_loss_percent,
                filled_quantity=total_qty,
            )
            ce_h.calculate_stop_loss_prices()
            legs.append(ce_h)

            pe_h = OptionLeg(
                leg_id=f"{config.strategy_id}_{selection.underlying}_PE_HEDGE",
                strategy_id=config.strategy_id,
                underlying=selection.underlying,
                expiry=selection.expiry,
                strike=selection.pe_hedge_strike,
                option_type=OptionType.PE,
                transaction_type=TransactionType.BUY,
                leg_type=LegType.HEDGE,
                quantity=total_qty,
                entry_price=pe_hedge_premium,
                entry_time=entry_time_str,
                current_price=pe_hedge_premium,
                stop_loss_percent=config.stop_loss_percent,
                hard_stop_loss_percent=config.hard_stop_loss_percent,
                filled_quantity=total_qty,
            )
            pe_h.calculate_stop_loss_prices()
            legs.append(pe_h)

        # 2. Main Short Strangle Legs
        ce_m = OptionLeg(
            leg_id=f"{config.strategy_id}_{selection.underlying}_CE_MAIN",
            strategy_id=config.strategy_id,
            underlying=selection.underlying,
            expiry=selection.expiry,
            strike=selection.ce_main_strike,
            option_type=OptionType.CE,
            transaction_type=TransactionType.SELL,
            leg_type=LegType.MAIN,
            quantity=total_qty,
            entry_price=ce_main_premium,
            entry_time=entry_time_str,
            current_price=ce_main_premium,
            stop_loss_percent=config.stop_loss_percent,
            hard_stop_loss_percent=config.hard_stop_loss_percent,
            filled_quantity=total_qty,
        )
        ce_m.calculate_stop_loss_prices()
        legs.append(ce_m)

        pe_m = OptionLeg(
            leg_id=f"{config.strategy_id}_{selection.underlying}_PE_MAIN",
            strategy_id=config.strategy_id,
            underlying=selection.underlying,
            expiry=selection.expiry,
            strike=selection.pe_main_strike,
            option_type=OptionType.PE,
            transaction_type=TransactionType.SELL,
            leg_type=LegType.MAIN,
            quantity=total_qty,
            entry_price=pe_main_premium,
            entry_time=entry_time_str,
            current_price=pe_main_premium,
            stop_loss_percent=config.stop_loss_percent,
            hard_stop_loss_percent=config.hard_stop_loss_percent,
            filled_quantity=total_qty,
        )
        pe_m.calculate_stop_loss_prices()
        legs.append(pe_m)

        return legs
