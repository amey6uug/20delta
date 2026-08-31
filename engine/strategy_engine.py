"""Unified Strategy Engine and State Machine.

Shared execution engine used by:
1. Backtest Engine (via Historical Data Provider)
2. Live Market Test (via Live Market Data & Paper Broker)
3. Future Live Trading (via Real Broker Adapter)

Implements:
- Explicit State Machine transitions with audit logging.
- Hedge-first placement and confirmation.
- Per-leg stop loss & hard stop execution.
- Basket profit target, profit lock & floor exits.
- 03:00 PM Asia/Kolkata forced exit.
- SENSEX ATM short safety prevention.
- Partial fill tracking.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from engine import alerts
from engine.broker_adapter import BrokerAdapter, PaperBrokerAdapter
from engine.calendar import format_timestamp_day, get_current_ist_time, is_within_strategy_window
from engine.db import db_manager
from engine.models import (
    AuditRecord,
    BasketMetrics,
    ExitReason,
    LegStatus,
    LegType,
    OptionLeg,
    Order,
    OrderStatus,
    StrategyConfig,
    StrategyState,
    TransactionType,
)
from engine.risk_engine import RiskEngine
from engine.strike_selector import StrikeSelectionResult, StrikeSelector


class StrategyExecutionSession:
    def __init__(
        self,
        config: StrategyConfig,
        run_id: Optional[str] = None,
        broker_adapter: Optional[BrokerAdapter] = None,
    ):
        self.config = config
        self.run_id = run_id or f"RUN_{config.strategy_id}_{uuid.uuid4().hex[:8]}"
        self.broker = broker_adapter or PaperBrokerAdapter(initial_capital=config.capital)
        self.state = StrategyState.IDLE
        self.legs: List[OptionLeg] = []
        self.orders: List[Order] = []
        self.metrics = BasketMetrics(capital=config.capital)
        self.peak_pnl = 0.0
        self.trough_pnl = 0.0
        self.exit_reason: Optional[ExitReason] = None
        self._transition_to(StrategyState.IDLE, "Session initialized")

    def _transition_to(self, new_state: StrategyState, reason: str = ""):
        old_state = self.state.value
        self.state = new_state
        db_manager.log_audit(
            AuditRecord(
                strategy_id=self.config.strategy_id,
                run_id=self.run_id,
                event="STATE_TRANSITION",
                reason=reason,
                old_state=old_state,
                new_state=new_state.value,
                metadata={"capital": self.config.capital, "net_pnl": self.metrics.net_pnl},
            )
        )
        alerts.alert_state(
            strategy_name=self.config.strategy_name,
            run_id=self.run_id,
            old_state=old_state,
            new_state=new_state.value,
            reason=reason,
            net_pnl=self.metrics.net_pnl,
        )

    def execute_entry(
        self,
        spot_price: float,
        trading_date: str,
        entry_time_str: str,
        ce_main_premium: float,
        pe_main_premium: float,
        ce_hedge_premium: float = 0.0,
        pe_hedge_premium: float = 0.0,
        num_lots: int = 1,
        current_datetime: Optional[datetime] = None,
    ) -> Tuple[bool, str]:
        """
        Execute strategy entry with strict safety validations.
        """
        self._transition_to(StrategyState.WAITING_FOR_ENTRY, "Evaluating entry conditions")

        # 1. Validate Strategy Entry Time Window (Cannot enter before 09:45 AM)
        is_window_ok, window_msg = is_within_strategy_window(
            self.config.entry_time, self.config.forced_exit_time, now=current_datetime
        )
        if not is_window_ok:
            self._transition_to(StrategyState.IDLE, f"Entry rejected: {window_msg}")
            return False, f"Entry Rejected: {window_msg}"

        self._transition_to(StrategyState.ENTRY_ALLOWED, "Entry window verified (>= 09:45 AM)")
        self._transition_to(StrategyState.ENTERING, "Selecting strikes and creating legs")

        # 2. Dynamic Strike Selection & SENSEX ATM Short Safety Validation
        selection = StrikeSelector.select_strikes(
            underlying=self.config.underlying,
            spot_price=spot_price,
            trading_date=trading_date,
            config=self.config,
        )

        if not selection.is_valid:
            self._transition_to(StrategyState.ERROR, selection.rejection_reason)
            return False, selection.rejection_reason

        # 3. Create Option Legs
        try:
            created_legs = StrikeSelector.create_legs_from_selection(
                selection=selection,
                config=self.config,
                entry_time_str=entry_time_str,
                ce_main_premium=ce_main_premium,
                pe_main_premium=pe_main_premium,
                ce_hedge_premium=ce_hedge_premium,
                pe_hedge_premium=pe_hedge_premium,
                num_lots=num_lots,
            )
        except Exception as e:
            self._transition_to(StrategyState.ERROR, str(e))
            return False, f"Leg creation error: {e}"

        # 4. Hedge Protection Execution (Hedge legs placed and confirmed first)
        hedge_legs = [leg for leg in created_legs if leg.leg_type == LegType.HEDGE]
        main_legs = [leg for leg in created_legs if leg.leg_type == LegType.MAIN]

        if self.config.hedge_required and hedge_legs:
            self._transition_to(StrategyState.HEDGE_PENDING, "Placing required protective hedge legs")
            for h_leg in hedge_legs:
                order = Order(
                    order_id=f"ORD_{h_leg.leg_id}_{uuid.uuid4().hex[:6]}",
                    strategy_id=self.config.strategy_id,
                    run_id=self.run_id,
                    leg_id=h_leg.leg_id,
                    timestamp=format_timestamp_day(current_datetime),
                    underlying=h_leg.underlying,
                    expiry=h_leg.expiry,
                    strike=h_leg.strike,
                    option_type=h_leg.option_type,
                    transaction_type=h_leg.transaction_type,
                    quantity=h_leg.quantity,
                    requested_price=h_leg.entry_price,
                )
                placed = self.broker.place_order(order)
                self.orders.append(placed)
                db_manager.save_order(placed)

                if placed.status != OrderStatus.FILLED and placed.status != OrderStatus.PARTIAL:
                    # Hedge placement failed -> abort short exposure
                    self._transition_to(StrategyState.HEDGE_FAILURE, f"Hedge order failed for {h_leg.strike} {h_leg.option_type.value}")
                    return False, "Hedge Placement Failed: Strategy aborted without naked short exposure."

                h_leg.filled_quantity = placed.filled_quantity
                db_manager.save_position_leg(h_leg, self.run_id)

        # 5. Place Main Short Legs
        for m_leg in main_legs:
            order = Order(
                order_id=f"ORD_{m_leg.leg_id}_{uuid.uuid4().hex[:6]}",
                strategy_id=self.config.strategy_id,
                run_id=self.run_id,
                leg_id=m_leg.leg_id,
                timestamp=format_timestamp_day(current_datetime),
                underlying=m_leg.underlying,
                expiry=m_leg.expiry,
                strike=m_leg.strike,
                option_type=m_leg.option_type,
                transaction_type=m_leg.transaction_type,
                quantity=m_leg.quantity,
                requested_price=m_leg.entry_price,
            )
            placed = self.broker.place_order(order)
            self.orders.append(placed)
            db_manager.save_order(placed)

            if placed.status != OrderStatus.FILLED and placed.status != OrderStatus.PARTIAL:
                self._transition_to(StrategyState.ERROR, f"Main leg order rejected: {m_leg.strike} {m_leg.option_type.value}")
                return False, f"Main Leg Order Rejected: {m_leg.strike} {m_leg.option_type.value}"

            m_leg.filled_quantity = placed.filled_quantity
            db_manager.save_position_leg(m_leg, self.run_id)

        self.legs = created_legs
        self._transition_to(StrategyState.ACTIVE, "All legs entered and active")
        return True, "Strategy Entry Successful"

    def process_tick(
        self,
        current_prices: Dict[str, float],
        current_datetime: Optional[datetime] = None,
    ) -> StrategyState:
        """
        Process a new market price tick and enforce all risk rules.
        """
        if self.state not in (StrategyState.ACTIVE, StrategyState.PROFIT_LOCK_ACTIVE, StrategyState.STOP_LOSS_TRIGGERED):
            return self.state

        curr_dt = current_datetime or get_current_ist_time()

        # 1. Update individual leg prices and evaluate per-leg Stop Loss
        for leg in self.legs:
            if leg.status == LegStatus.OPEN:
                ltp = current_prices.get(leg.leg_id, leg.current_price)
                sl_hit, exit_reason, reason_msg = RiskEngine.evaluate_leg_stop_loss(leg, ltp)

                if sl_hit:
                    # Exit that single leg immediately
                    leg.exit_price = ltp
                    leg.exit_time = format_timestamp_day(curr_dt)
                    leg.exit_reason = exit_reason
                    leg.status = LegStatus.STOPPED_OUT if exit_reason == ExitReason.NORMAL_STOP_LOSS else LegStatus.HARD_STOPPED
                    leg.update_pnl(ltp)
                    db_manager.save_position_leg(leg, self.run_id)

                    new_st = StrategyState.HARD_STOP_TRIGGERED if exit_reason == ExitReason.HARD_STOP_LOSS else StrategyState.STOP_LOSS_TRIGGERED
                    self._transition_to(new_st, f"Leg {leg.strike} {leg.option_type.value}: {reason_msg}")

        # 2. Update Basket Metrics
        self.metrics = RiskEngine.calculate_basket_metrics(
            legs=self.legs,
            config=self.config,
            profit_lock_active=self.metrics.profit_lock_active,
            historical_peak_pnl=self.peak_pnl,
            historical_trough_pnl=self.trough_pnl,
        )
        self.peak_pnl = max(self.peak_pnl, self.metrics.net_pnl)
        self.trough_pnl = min(self.trough_pnl, self.metrics.net_pnl)

        # Transition to PROFIT_LOCK_ACTIVE if newly activated
        if self.metrics.profit_lock_active and self.state == StrategyState.ACTIVE:
            self._transition_to(StrategyState.PROFIT_LOCK_ACTIVE, "1% Profit Lock Trigger Hit (+₹10,000)")

        # 3. Evaluate Basket Exits (Profit Target, Profit Lock Floor, or 03:00 PM Forced Exit)
        should_exit_all, b_exit_reason, b_reason_msg, is_lock = RiskEngine.evaluate_basket_exits(
            metrics=self.metrics,
            config=self.config,
            current_time_ist=curr_dt,
        )

        if should_exit_all:
            self.exit_all_open_legs(
                exit_reason=b_exit_reason,
                reason_msg=b_reason_msg,
                current_prices=current_prices,
                current_datetime=curr_dt,
            )

        return self.state

    def exit_all_open_legs(
        self,
        exit_reason: ExitReason,
        reason_msg: str,
        current_prices: Dict[str, float],
        current_datetime: Optional[datetime] = None,
    ):
        """
        Exit ALL open legs simultaneously (used for Target Reached, Profit Lock Floor, or 3 PM Exit).
        """
        curr_dt = current_datetime or get_current_ist_time()
        self._transition_to(StrategyState.EXITING, reason_msg)

        for leg in self.legs:
            if leg.status == LegStatus.OPEN:
                ltp = current_prices.get(leg.leg_id, leg.current_price)
                leg.exit_price = ltp
                leg.exit_time = format_timestamp_day(curr_dt)
                leg.exit_reason = exit_reason

                if exit_reason == ExitReason.PROFIT_TARGET:
                    leg.status = LegStatus.PROFIT_TARGET_EXIT
                elif exit_reason == ExitReason.PROFIT_LOCK:
                    leg.status = LegStatus.PROFIT_LOCK_EXIT
                elif exit_reason == ExitReason.TIME_EXIT:
                    leg.status = LegStatus.TIME_EXITED
                else:
                    leg.status = LegStatus.CLOSED

                leg.update_pnl(ltp)
                db_manager.save_position_leg(leg, self.run_id)

        # Recalculate final basket metrics
        self.metrics = RiskEngine.calculate_basket_metrics(
            legs=self.legs,
            config=self.config,
            profit_lock_active=self.metrics.profit_lock_active,
            historical_peak_pnl=self.peak_pnl,
            historical_trough_pnl=self.trough_pnl,
        )

        if exit_reason == ExitReason.PROFIT_TARGET:
            self._transition_to(StrategyState.TARGET_REACHED, reason_msg)
        elif exit_reason == ExitReason.TIME_EXIT:
            self._transition_to(StrategyState.FORCED_EXIT, reason_msg)

        self._transition_to(StrategyState.COMPLETED, f"All legs exited: {reason_msg}")
