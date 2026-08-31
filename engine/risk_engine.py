"""Risk Engine — Per-Leg Stop Loss, Basket Profit Engine, and Safety Protection.

Rules:
1. Per-leg SL calculated strictly against entry premium (80% SL, 100% Hard SL).
2. Basket Net P&L = Realized P&L + Unrealized P&L - Charges.
3. 2% Profit Target on Strategy Capital -> Exit ALL legs.
4. 1% Profit Lock on Strategy Capital -> Activates lock. Falling back to floor -> Exit ALL legs.
5. 03:00 PM Forced Exit -> Exit ALL legs.
6. SENSEX ATM Short Prohibited -> Hard safety rejection.
"""

from __future__ import annotations

from datetime import datetime, time
from typing import Dict, List, Optional, Tuple

from engine.calendar import format_timestamp_day, get_current_ist_time
from engine.models import (
    BasketMetrics,
    ExitReason,
    LegStatus,
    OptionLeg,
    OptionType,
    StrategyConfig,
    StrategyState,
    TransactionType,
)


class RiskEngine:
    @staticmethod
    def validate_sensex_atm_short(
        underlying: str,
        transaction_type: TransactionType,
        strike: float,
        atm_strike: float,
    ) -> Tuple[bool, str]:
        """
        HARD SAFETY RULE: Never short SENSEX ATM options.
        Rejects sell orders on SENSEX ATM strikes across all engine layers.
        """
        if underlying.upper() == "SENSEX" and transaction_type == TransactionType.SELL:
            if abs(strike - atm_strike) < 1e-3:
                return False, "SENSEX ATM SHORTING IS PROHIBITED BY STRATEGY RISK RULES."
        return True, ""

    @staticmethod
    def evaluate_leg_stop_loss(leg: OptionLeg, current_ltp: float) -> Tuple[bool, Optional[ExitReason], str]:
        """
        Evaluate per-leg Stop Loss and Hard Stop Loss conditions against ENTRY PREMIUM.

        BUY Leg:
        - Entry: ₹100
        - 80% SL Price: ₹20 (loss when LTP <= ₹20)
        - 100% Hard SL Price: ₹0 (hard exit when LTP <= ₹0)

        SELL Leg:
        - Entry: ₹100
        - 80% SL Price: ₹180 (loss when LTP >= ₹180)
        - 100% Hard SL Price: ₹200 (hard exit when LTP >= ₹200)
        """
        if leg.status != LegStatus.OPEN or leg.entry_price <= 0:
            return False, None, ""

        leg.update_pnl(current_ltp)

        # 1. Hard Stop Loss Check (100% adverse move)
        if leg.transaction_type == TransactionType.SELL:
            if current_ltp >= leg.hard_stop_loss_price:
                return (
                    True,
                    ExitReason.HARD_STOP_LOSS,
                    f"Hard Stop Triggered: LTP ₹{current_ltp:.2f} >= Hard SL ₹{leg.hard_stop_loss_price:.2f} (100% loss)",
                )
        else:  # BUY Leg
            if current_ltp <= leg.hard_stop_loss_price:
                return (
                    True,
                    ExitReason.HARD_STOP_LOSS,
                    f"Hard Stop Triggered: LTP ₹{current_ltp:.2f} <= Hard SL ₹{leg.hard_stop_loss_price:.2f} (100% loss)",
                )

        # 2. Normal Stop Loss Check (80% adverse move)
        if leg.transaction_type == TransactionType.SELL:
            if current_ltp >= leg.stop_loss_price:
                return (
                    True,
                    ExitReason.NORMAL_STOP_LOSS,
                    f"Stop Loss Triggered: LTP ₹{current_ltp:.2f} >= SL ₹{leg.stop_loss_price:.2f} (80% loss)",
                )
        else:  # BUY Leg
            if current_ltp <= leg.stop_loss_price:
                return (
                    True,
                    ExitReason.NORMAL_STOP_LOSS,
                    f"Stop Loss Triggered: LTP ₹{current_ltp:.2f} <= SL ₹{leg.stop_loss_price:.2f} (80% loss)",
                )

        return False, None, ""

    @staticmethod
    def calculate_basket_metrics(
        legs: List[OptionLeg],
        config: StrategyConfig,
        profit_lock_active: bool = False,
        historical_peak_pnl: float = 0.0,
        historical_trough_pnl: float = 0.0,
    ) -> BasketMetrics:
        """
        Calculate total basket P&L and risk metrics.
        Basket Net P&L = Realized P&L + Unrealized P&L - Charges.
        """
        capital = config.capital
        target_amount = capital * (config.profit_target_percent / 100.0)
        lock_amount = capital * (config.profit_lock_trigger_percent / 100.0)

        realized = 0.0
        unrealized = 0.0
        total_charges = 0.0
        open_risk = 0.0

        for leg in legs:
            total_charges += leg.charges
            if leg.status == LegStatus.OPEN:
                unrealized += leg.pnl
                # Open risk: distance to stop loss
                if leg.transaction_type == TransactionType.SELL:
                    qty = leg.filled_quantity if leg.filled_quantity > 0 else leg.quantity
                    open_risk += max(0.0, (leg.stop_loss_price - leg.current_price) * qty)
                else:
                    qty = leg.filled_quantity if leg.filled_quantity > 0 else leg.quantity
                    open_risk += max(0.0, (leg.current_price - leg.stop_loss_price) * qty)
            else:
                realized += leg.pnl

        net_pnl = round(realized + unrealized - total_charges, 2)
        net_pnl_pct = round((net_pnl / capital) * 100.0, 2) if capital > 0 else 0.0

        # Check if profit lock becomes active
        if not profit_lock_active and net_pnl >= lock_amount:
            profit_lock_active = True

        dist_lock = max(0.0, lock_amount - net_pnl)
        dist_target = max(0.0, target_amount - net_pnl)

        max_profit = max(historical_peak_pnl, net_pnl)
        max_loss = min(historical_trough_pnl, net_pnl)
        max_drawdown = max_profit - net_pnl

        return BasketMetrics(
            capital=capital,
            realized_pnl=round(realized, 2),
            unrealized_pnl=round(unrealized, 2),
            charges=round(total_charges, 2),
            net_pnl=net_pnl,
            net_pnl_pct=net_pnl_pct,
            profit_lock_active=profit_lock_active,
            profit_lock_target=lock_amount,
            profit_target_amount=target_amount,
            distance_to_lock=dist_lock,
            distance_to_target=dist_target,
            max_profit=round(max_profit, 2),
            max_loss=round(max_loss, 2),
            max_drawdown=round(max_drawdown, 2),
            open_risk=round(open_risk, 2),
        )

    @staticmethod
    def evaluate_basket_exits(
        metrics: BasketMetrics,
        config: StrategyConfig,
        current_time_ist: Optional[datetime] = None,
    ) -> Tuple[bool, Optional[ExitReason], str, bool]:
        """
        Evaluate basket-level exit triggers.

        Returns (should_exit_all, exit_reason, message, is_lock_activated).
        """
        curr = current_time_ist or get_current_ist_time()
        curr_t = curr.time()

        # 1. Check Forced Exit Time (03:00 PM / 15:00 IST)
        xh, xm = map(int, config.forced_exit_time.split(":"))
        forced_exit_t = time(xh, xm)
        if curr_t >= forced_exit_t:
            return (
                True,
                ExitReason.TIME_EXIT,
                f"FORCED EXIT AT 03:00 PM IST: All open legs must exit at {curr_t.strftime('%I:%M:%S %p')}.",
                metrics.profit_lock_active,
            )

        # 2. Check Profit Target Hit (Default 2% = ₹20,000 on ₹10L)
        target_amount = config.capital * (config.profit_target_percent / 100.0)
        if metrics.net_pnl >= target_amount:
            return (
                True,
                ExitReason.PROFIT_TARGET,
                f"PROFIT TARGET REACHED: Net P&L ₹{metrics.net_pnl:,.2f} >= Target ₹{target_amount:,.2f} ({config.profit_target_percent}%). EXIT ALL LEGS.",
                metrics.profit_lock_active,
            )

        # 3. Check Profit Lock Activation and Floor Protection (Default 1% Trigger / 1% Floor = ₹10,000 on ₹10L)
        lock_trigger_amount = config.capital * (config.profit_lock_trigger_percent / 100.0)
        lock_floor_amount = config.capital * (config.profit_lock_floor_percent / 100.0)

        is_lock_active = metrics.profit_lock_active
        if not is_lock_active and metrics.net_pnl >= lock_trigger_amount:
            is_lock_active = True

        if is_lock_active:
            # If P&L falls back to or below the locked floor, exit all legs
            if metrics.net_pnl < lock_floor_amount:
                return (
                    True,
                    ExitReason.PROFIT_LOCK,
                    f"PROFIT LOCK FLOOR TRIGGERED: P&L dropped to ₹{metrics.net_pnl:,.2f} below floor ₹{lock_floor_amount:,.2f}. EXIT ALL LEGS.",
                    is_lock_active,
                )

        return False, None, "", is_lock_active
