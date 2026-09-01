"""Data models, Enums, and Dataclasses for AlgoTest OS Strategy and Risk Engine."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, time
from enum import Enum
from typing import Any, Dict, List, Optional


class InstrumentType(str, Enum):
    NIFTY = "NIFTY"
    SENSEX = "SENSEX"
    BANKNIFTY = "BANKNIFTY"


class OptionType(str, Enum):
    CE = "CE"
    PE = "PE"


class TransactionType(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class LegType(str, Enum):
    MAIN = "MAIN"
    HEDGE = "HEDGE"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    PARTIAL = "PARTIAL"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


class LegStatus(str, Enum):
    PENDING = "PENDING"
    OPEN = "OPEN"
    STOPPED_OUT = "STOPPED_OUT"
    HARD_STOPPED = "HARD_STOPPED"
    PROFIT_TARGET_EXIT = "PROFIT_TARGET_EXIT"
    PROFIT_LOCK_EXIT = "PROFIT_LOCK_EXIT"
    TIME_EXITED = "TIME_EXITED"
    MANUAL_EXITED = "MANUAL_EXITED"
    CLOSED = "CLOSED"


class StrategyState(str, Enum):
    IDLE = "IDLE"
    WAITING_FOR_ENTRY = "WAITING_FOR_ENTRY"
    ENTRY_ALLOWED = "ENTRY_ALLOWED"
    ENTERING = "ENTERING"
    HEDGE_PENDING = "HEDGE_PENDING"
    ACTIVE = "ACTIVE"
    PROFIT_LOCK_ACTIVE = "PROFIT_LOCK_ACTIVE"
    STOP_LOSS_TRIGGERED = "STOP_LOSS_TRIGGERED"
    HARD_STOP_TRIGGERED = "HARD_STOP_TRIGGERED"
    TARGET_REACHED = "TARGET_REACHED"
    FORCED_EXIT = "FORCED_EXIT"
    EXITING = "EXITING"
    COMPLETED = "COMPLETED"
    ERROR = "ERROR"
    DISABLED = "DISABLED"
    HEDGE_FAILURE = "HEDGE_FAILURE"


class ExitReason(str, Enum):
    NORMAL_STOP_LOSS = "NORMAL_STOP_LOSS"
    HARD_STOP_LOSS = "HARD_STOP_LOSS"
    PROFIT_TARGET = "PROFIT_TARGET"
    PROFIT_LOCK = "PROFIT_LOCK"
    TIME_EXIT = "TIME_EXIT"
    MANUAL_EXIT = "MANUAL_EXIT"
    SYSTEM_EXIT = "SYSTEM_EXIT"
    BROKER_REJECTION = "BROKER_REJECTION"
    DATA_FAILURE = "DATA_FAILURE"
    STRATEGY_DISABLE = "STRATEGY_DISABLE"
    HEDGE_FAILURE = "HEDGE_FAILURE"
    REJECTED_SAFETY = "REJECTED_SAFETY"


class MarketDataStatus(str, Enum):
    LIVE = "LIVE"
    STALE = "STALE"
    UNAVAILABLE = "UNAVAILABLE"
    DEMO = "DEMO"


@dataclass
class StrategyConfig:
    strategy_id: str
    strategy_name: str
    underlying: str = "NIFTY"
    enabled: bool = True
    capital: float = 1_000_000.0  # ₹10,00,000 default

    # Risk parameters (strictly per-leg entry premium)
    stop_loss_percent: float = 80.0  # 80% default
    hard_stop_loss_percent: float = 100.0  # 100% default

    # Profit parameters (basket capital %)
    profit_lock_trigger_percent: float = 1.0  # 1% (₹10,000 on ₹10L)
    profit_lock_floor_percent: float = 1.0  # 1% floor
    profit_target_percent: float = 2.0  # 2% (₹20,000 on ₹10L)

    # Time parameters (Asia/Kolkata)
    entry_time: str = "09:45"  # 09:45 AM
    forced_exit_time: str = "15:00"  # 03:00 PM

    # Hedge & Strike selection
    hedge_required: bool = True
    nifty_otm_distance: int = 200
    nifty_near_expiry_distance: int = 100
    nifty_hedge_distance: int = 300

    sensex_otm_distance: int = 300
    sensex_near_expiry_distance: int = 100
    sensex_hedge_distance: int = 500

    strike_selection_mode: str = "DYNAMIC_DTE"
    strike_distance_points: int = 200

    allow_atm_short: bool = False  # NEVER allow SENSEX ATM short
    allow_reentry: bool = False
    max_positions: int = 4

    version: int = 1
    created_at: str = ""
    updated_at: str = ""
    updated_by: str = "admin"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class OptionLeg:
    leg_id: str
    strategy_id: str
    underlying: str
    expiry: str
    strike: float
    option_type: OptionType
    transaction_type: TransactionType  # BUY or SELL
    leg_type: LegType  # MAIN or HEDGE
    quantity: int
    entry_price: float
    entry_time: str
    current_price: float = 0.0
    stop_loss_price: float = 0.0
    hard_stop_loss_price: float = 0.0
    stop_loss_percent: float = 80.0
    hard_stop_loss_percent: float = 100.0
    status: LegStatus = LegStatus.OPEN
    exit_price: Optional[float] = None
    exit_time: Optional[str] = None
    exit_reason: Optional[ExitReason] = None
    pnl: float = 0.0
    pnl_pct: float = 0.0
    filled_quantity: int = 0
    charges: float = 0.0

    def calculate_stop_loss_prices(self):
        """Calculate exact stop loss and hard stop prices based on entry premium."""
        if self.transaction_type == TransactionType.SELL:
            # Short leg: loss occurs when price rises
            self.stop_loss_price = round(self.entry_price * (1.0 + self.stop_loss_percent / 100.0), 2)
            self.hard_stop_loss_price = round(self.entry_price * (1.0 + self.hard_stop_loss_percent / 100.0), 2)
        else:
            # Buy leg: loss occurs when price drops
            self.stop_loss_price = round(max(0.0, self.entry_price * (1.0 - self.stop_loss_percent / 100.0)), 2)
            self.hard_stop_loss_price = round(max(0.0, self.entry_price * (1.0 - self.hard_stop_loss_percent / 100.0)), 2)

    def update_pnl(self, current_ltp: float):
        """Update leg PnL based on current LTP and filled quantity."""
        self.current_price = current_ltp
        qty = self.filled_quantity if self.filled_quantity > 0 else self.quantity
        if self.status == LegStatus.OPEN:
            if self.transaction_type == TransactionType.SELL:
                self.pnl = round((self.entry_price - current_ltp) * qty, 2)
                self.pnl_pct = round(((self.entry_price - current_ltp) / self.entry_price) * 100.0, 2) if self.entry_price else 0.0
            else:
                self.pnl = round((current_ltp - self.entry_price) * qty, 2)
                self.pnl_pct = round(((current_ltp - self.entry_price) / self.entry_price) * 100.0, 2) if self.entry_price else 0.0
        elif self.exit_price is not None:
            if self.transaction_type == TransactionType.SELL:
                self.pnl = round((self.entry_price - self.exit_price) * qty, 2)
                self.pnl_pct = round(((self.entry_price - self.exit_price) / self.entry_price) * 100.0, 2) if self.entry_price else 0.0
            else:
                self.pnl = round((self.exit_price - self.entry_price) * qty, 2)
                self.pnl_pct = round(((self.exit_price - self.entry_price) / self.entry_price) * 100.0, 2) if self.entry_price else 0.0


@dataclass
class Order:
    order_id: str
    strategy_id: str
    run_id: str
    leg_id: str
    timestamp: str
    underlying: str
    expiry: str
    strike: float
    option_type: OptionType
    transaction_type: TransactionType
    quantity: int
    requested_price: float
    executed_price: float = 0.0
    filled_quantity: int = 0
    remaining_quantity: int = 0
    status: OrderStatus = OrderStatus.PENDING
    reason: str = ""
    source: str = "SYSTEM"
    broker_order_id: str = ""  # id returned by the live broker


@dataclass
class BasketMetrics:
    capital: float = 1_000_000.0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    charges: float = 0.0
    net_pnl: float = 0.0
    net_pnl_pct: float = 0.0
    profit_lock_active: bool = False
    profit_lock_target: float = 10_000.0
    profit_target_amount: float = 20_000.0
    distance_to_lock: float = 10_000.0
    distance_to_target: float = 20_000.0
    max_profit: float = 0.0
    max_loss: float = 0.0
    max_drawdown: float = 0.0
    open_risk: float = 0.0


@dataclass
class MarketQuote:
    symbol: str
    underlying: str
    strike: float
    option_type: OptionType
    expiry: str
    ltp: float
    bid: float = 0.0
    ask: float = 0.0
    volume: int = 0
    oi: int = 0
    timestamp: str = ""
    status: MarketDataStatus = MarketDataStatus.LIVE


@dataclass
class AuditRecord:
    id: Optional[int] = None
    timestamp: str = ""
    date_formatted: str = ""  # e.g., "10-09-2026, Thursday"
    strategy_id: str = ""
    run_id: str = ""
    event: str = ""
    reason: str = ""
    old_state: str = ""
    new_state: str = ""
    user: str = "system"
    metadata: Dict[str, Any] = field(default_factory=dict)
