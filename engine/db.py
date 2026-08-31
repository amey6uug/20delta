"""SQLite Database Persistence Layer for AlgoTest OS.

Persists:
- Strategy Configurations and Version History
- Strategy Runs and Sessions
- Positions and Option Legs
- Orders and Execution logs
- Real-time P&L snapshots
- Audit Logs
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from engine.calendar import format_date_day, format_timestamp_day, get_current_ist_time
from engine.models import (
    AuditRecord,
    ExitReason,
    LegStatus,
    LegType,
    OptionLeg,
    OptionType,
    Order,
    OrderStatus,
    StrategyConfig,
    StrategyState,
    TransactionType,
)

DB_DIR = Path("data")
DB_PATH = DB_DIR / "options_os.db"


class DatabaseManager:
    def __init__(self, db_path: Path | str = DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self.get_connection() as conn:
            cur = conn.cursor()

            # Strategy Configurations
            cur.execute("""
            CREATE TABLE IF NOT EXISTS strategy_configs (
                strategy_id TEXT PRIMARY KEY,
                strategy_name TEXT NOT NULL,
                underlying TEXT NOT NULL,
                enabled INTEGER DEFAULT 1,
                capital REAL DEFAULT 1000000.0,
                stop_loss_percent REAL DEFAULT 80.0,
                hard_stop_loss_percent REAL DEFAULT 100.0,
                profit_lock_trigger_percent REAL DEFAULT 1.0,
                profit_lock_floor_percent REAL DEFAULT 1.0,
                profit_target_percent REAL DEFAULT 2.0,
                entry_time TEXT DEFAULT '09:45',
                forced_exit_time TEXT DEFAULT '15:00',
                hedge_required INTEGER DEFAULT 1,
                nifty_otm_distance INTEGER DEFAULT 200,
                nifty_near_expiry_distance INTEGER DEFAULT 100,
                nifty_hedge_distance INTEGER DEFAULT 300,
                sensex_otm_distance INTEGER DEFAULT 300,
                sensex_near_expiry_distance INTEGER DEFAULT 100,
                sensex_hedge_distance INTEGER DEFAULT 500,
                strike_selection_mode TEXT DEFAULT 'DYNAMIC_DTE',
                strike_distance_points INTEGER DEFAULT 200,
                allow_atm_short INTEGER DEFAULT 0,
                allow_reentry INTEGER DEFAULT 0,
                max_positions INTEGER DEFAULT 4,
                version INTEGER DEFAULT 1,
                created_at TEXT,
                updated_at TEXT,
                updated_by TEXT DEFAULT 'admin'
            )
            """)

            # Config Version History
            cur.execute("""
            CREATE TABLE IF NOT EXISTS config_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_id TEXT NOT NULL,
                version INTEGER NOT NULL,
                config_json TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                updated_by TEXT NOT NULL
            )
            """)

            # Strategy Runs
            cur.execute("""
            CREATE TABLE IF NOT EXISTS strategy_runs (
                run_id TEXT PRIMARY KEY,
                strategy_id TEXT NOT NULL,
                run_type TEXT NOT NULL, -- 'LIVE_TEST' or 'BACKTEST' or 'LIVE'
                trading_date TEXT NOT NULL,
                date_formatted TEXT NOT NULL,
                status TEXT NOT NULL,
                capital REAL NOT NULL,
                realized_pnl REAL DEFAULT 0.0,
                unrealized_pnl REAL DEFAULT 0.0,
                charges REAL DEFAULT 0.0,
                net_pnl REAL DEFAULT 0.0,
                net_pnl_pct REAL DEFAULT 0.0,
                profit_lock_hit INTEGER DEFAULT 0,
                target_hit INTEGER DEFAULT 0,
                sl_hit INTEGER DEFAULT 0,
                hard_sl_hit INTEGER DEFAULT 0,
                forced_exit INTEGER DEFAULT 0,
                start_time TEXT,
                end_time TEXT,
                config_snapshot TEXT
            )
            """)

            # Option Legs / Positions
            cur.execute("""
            CREATE TABLE IF NOT EXISTS position_legs (
                leg_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                strategy_id TEXT NOT NULL,
                underlying TEXT NOT NULL,
                expiry TEXT NOT NULL,
                strike REAL NOT NULL,
                option_type TEXT NOT NULL,
                transaction_type TEXT NOT NULL,
                leg_type TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                entry_price REAL NOT NULL,
                entry_time TEXT NOT NULL,
                current_price REAL DEFAULT 0.0,
                stop_loss_price REAL DEFAULT 0.0,
                hard_stop_loss_price REAL DEFAULT 0.0,
                stop_loss_percent REAL DEFAULT 80.0,
                hard_stop_loss_percent REAL DEFAULT 100.0,
                status TEXT NOT NULL,
                exit_price REAL,
                exit_time TEXT,
                exit_reason TEXT,
                pnl REAL DEFAULT 0.0,
                pnl_pct REAL DEFAULT 0.0,
                filled_quantity INTEGER DEFAULT 0,
                charges REAL DEFAULT 0.0
            )
            """)

            # Orders
            cur.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                order_id TEXT PRIMARY KEY,
                strategy_id TEXT NOT NULL,
                run_id TEXT NOT NULL,
                leg_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                underlying TEXT NOT NULL,
                expiry TEXT NOT NULL,
                strike REAL NOT NULL,
                option_type TEXT NOT NULL,
                transaction_type TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                requested_price REAL NOT NULL,
                executed_price REAL DEFAULT 0.0,
                filled_quantity INTEGER DEFAULT 0,
                remaining_quantity INTEGER DEFAULT 0,
                status TEXT NOT NULL,
                reason TEXT,
                source TEXT DEFAULT 'SYSTEM'
            )
            """)

            # Audit Logs
            cur.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                date_formatted TEXT NOT NULL,
                strategy_id TEXT NOT NULL,
                run_id TEXT NOT NULL,
                event TEXT NOT NULL,
                reason TEXT,
                old_state TEXT,
                new_state TEXT,
                user TEXT DEFAULT 'system',
                metadata TEXT
            )
            """)

            conn.commit()

    # ── Strategy Config Methods ───────────────────────────────────────────────

    def save_strategy_config(self, cfg: StrategyConfig, user: str = "admin") -> int:
        now_str = format_timestamp_day()
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT version FROM strategy_configs WHERE strategy_id = ?", (cfg.strategy_id,))
            row = cur.fetchone()

            new_version = (row["version"] + 1) if row else 1
            cfg.version = new_version
            cfg.updated_at = now_str
            cfg.updated_by = user
            if not cfg.created_at:
                cfg.created_at = now_str

            cur.execute("""
            INSERT INTO strategy_configs (
                strategy_id, strategy_name, underlying, enabled, capital,
                stop_loss_percent, hard_stop_loss_percent,
                profit_lock_trigger_percent, profit_lock_floor_percent, profit_target_percent,
                entry_time, forced_exit_time, hedge_required,
                nifty_otm_distance, nifty_near_expiry_distance, nifty_hedge_distance,
                sensex_otm_distance, sensex_near_expiry_distance, sensex_hedge_distance,
                strike_selection_mode, strike_distance_points, allow_atm_short, allow_reentry,
                max_positions, version, created_at, updated_at, updated_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(strategy_id) DO UPDATE SET
                strategy_name = excluded.strategy_name,
                underlying = excluded.underlying,
                enabled = excluded.enabled,
                capital = excluded.capital,
                stop_loss_percent = excluded.stop_loss_percent,
                hard_stop_loss_percent = excluded.hard_stop_loss_percent,
                profit_lock_trigger_percent = excluded.profit_lock_trigger_percent,
                profit_lock_floor_percent = excluded.profit_lock_floor_percent,
                profit_target_percent = excluded.profit_target_percent,
                entry_time = excluded.entry_time,
                forced_exit_time = excluded.forced_exit_time,
                hedge_required = excluded.hedge_required,
                nifty_otm_distance = excluded.nifty_otm_distance,
                nifty_near_expiry_distance = excluded.nifty_near_expiry_distance,
                nifty_hedge_distance = excluded.nifty_hedge_distance,
                sensex_otm_distance = excluded.sensex_otm_distance,
                sensex_near_expiry_distance = excluded.sensex_near_expiry_distance,
                sensex_hedge_distance = excluded.sensex_hedge_distance,
                strike_selection_mode = excluded.strike_selection_mode,
                strike_distance_points = excluded.strike_distance_points,
                allow_atm_short = excluded.allow_atm_short,
                allow_reentry = excluded.allow_reentry,
                max_positions = excluded.max_positions,
                version = excluded.version,
                updated_at = excluded.updated_at,
                updated_by = excluded.updated_by
            """, (
                cfg.strategy_id, cfg.strategy_name, cfg.underlying, int(cfg.enabled), cfg.capital,
                cfg.stop_loss_percent, cfg.hard_stop_loss_percent,
                cfg.profit_lock_trigger_percent, cfg.profit_lock_floor_percent, cfg.profit_target_percent,
                cfg.entry_time, cfg.forced_exit_time, int(cfg.hedge_required),
                cfg.nifty_otm_distance, cfg.nifty_near_expiry_distance, cfg.nifty_hedge_distance,
                cfg.sensex_otm_distance, cfg.sensex_near_expiry_distance, cfg.sensex_hedge_distance,
                cfg.strike_selection_mode, cfg.strike_distance_points, int(cfg.allow_atm_short), int(cfg.allow_reentry),
                cfg.max_positions, cfg.version, cfg.created_at, cfg.updated_at, cfg.updated_by
            ))

            # Store version snapshot
            cur.execute("""
            INSERT INTO config_versions (strategy_id, version, config_json, updated_at, updated_by)
            VALUES (?, ?, ?, ?, ?)
            """, (cfg.strategy_id, new_version, json.dumps(cfg.to_dict()), now_str, user))

            conn.commit()
            return new_version

    def get_strategy_config(self, strategy_id: str) -> Optional[StrategyConfig]:
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM strategy_configs WHERE strategy_id = ?", (strategy_id,))
            row = cur.fetchone()
            if not row:
                return None
            return StrategyConfig(
                strategy_id=row["strategy_id"],
                strategy_name=row["strategy_name"],
                underlying=row["underlying"],
                enabled=bool(row["enabled"]),
                capital=row["capital"],
                stop_loss_percent=row["stop_loss_percent"],
                hard_stop_loss_percent=row["hard_stop_loss_percent"],
                profit_lock_trigger_percent=row["profit_lock_trigger_percent"],
                profit_lock_floor_percent=row["profit_lock_floor_percent"],
                profit_target_percent=row["profit_target_percent"],
                entry_time=row["entry_time"],
                forced_exit_time=row["forced_exit_time"],
                hedge_required=bool(row["hedge_required"]),
                nifty_otm_distance=row["nifty_otm_distance"],
                nifty_near_expiry_distance=row["nifty_near_expiry_distance"],
                nifty_hedge_distance=row["nifty_hedge_distance"],
                sensex_otm_distance=row["sensex_otm_distance"],
                sensex_near_expiry_distance=row["sensex_near_expiry_distance"],
                sensex_hedge_distance=row["sensex_hedge_distance"],
                strike_selection_mode=row["strike_selection_mode"],
                strike_distance_points=row["strike_distance_points"],
                allow_atm_short=bool(row["allow_atm_short"]),
                allow_reentry=bool(row["allow_reentry"]),
                max_positions=row["max_positions"],
                version=row["version"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                updated_by=row["updated_by"],
            )

    def list_strategy_configs(self) -> List[StrategyConfig]:
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT strategy_id FROM strategy_configs ORDER BY strategy_name")
            rows = cur.fetchall()
            return [self.get_strategy_config(r["strategy_id"]) for r in rows if r]

    # ── Audit Log Methods ─────────────────────────────────────────────────────

    def log_audit(self, record: AuditRecord):
        now_ts = format_timestamp_day()
        formatted_d = format_date_day(get_current_ist_time())
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
            INSERT INTO audit_logs (
                timestamp, date_formatted, strategy_id, run_id, event, reason, old_state, new_state, user, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                record.timestamp or now_ts,
                record.date_formatted or formatted_d,
                record.strategy_id,
                record.run_id,
                record.event,
                record.reason,
                record.old_state,
                record.new_state,
                record.user,
                json.dumps(record.metadata),
            ))
            conn.commit()

    def get_audit_logs(self, limit: int = 200, strategy_id: Optional[str] = None) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cur = conn.cursor()
            if strategy_id:
                cur.execute("SELECT * FROM audit_logs WHERE strategy_id = ? ORDER BY id DESC LIMIT ?", (strategy_id, limit))
            else:
                cur.execute("SELECT * FROM audit_logs ORDER BY id DESC LIMIT ?", (limit,))
            rows = cur.fetchall()
            results = []
            for r in rows:
                item = dict(r)
                try:
                    item["metadata"] = json.loads(item["metadata"]) if item["metadata"] else {}
                except Exception:
                    pass
                results.append(item)
            return results

    # ── Position & Order Methods ──────────────────────────────────────────────

    def save_position_leg(self, leg: OptionLeg, run_id: str):
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
            INSERT INTO position_legs (
                leg_id, run_id, strategy_id, underlying, expiry, strike, option_type, transaction_type,
                leg_type, quantity, entry_price, entry_time, current_price, stop_loss_price, hard_stop_loss_price,
                stop_loss_percent, hard_stop_loss_percent, status, exit_price, exit_time, exit_reason, pnl, pnl_pct,
                filled_quantity, charges
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(leg_id) DO UPDATE SET
                current_price = excluded.current_price,
                stop_loss_price = excluded.stop_loss_price,
                hard_stop_loss_price = excluded.hard_stop_loss_price,
                status = excluded.status,
                exit_price = excluded.exit_price,
                exit_time = excluded.exit_time,
                exit_reason = excluded.exit_reason,
                pnl = excluded.pnl,
                pnl_pct = excluded.pnl_pct,
                filled_quantity = excluded.filled_quantity,
                charges = excluded.charges
            """, (
                leg.leg_id, run_id, leg.strategy_id, leg.underlying, leg.expiry, leg.strike,
                leg.option_type.value, leg.transaction_type.value, leg.leg_type.value, leg.quantity,
                leg.entry_price, leg.entry_time, leg.current_price, leg.stop_loss_price, leg.hard_stop_loss_price,
                leg.stop_loss_percent, leg.hard_stop_loss_percent, leg.status.value, leg.exit_price,
                leg.exit_time, leg.exit_reason.value if leg.exit_reason else None, leg.pnl, leg.pnl_pct,
                leg.filled_quantity, leg.charges
            ))
            conn.commit()

    def get_open_legs(self, run_id: Optional[str] = None) -> List[OptionLeg]:
        with self.get_connection() as conn:
            cur = conn.cursor()
            if run_id:
                cur.execute("SELECT * FROM position_legs WHERE run_id = ? AND status = 'OPEN'", (run_id,))
            else:
                cur.execute("SELECT * FROM position_legs WHERE status = 'OPEN'")
            rows = cur.fetchall()
            legs = []
            for r in rows:
                legs.append(OptionLeg(
                    leg_id=r["leg_id"],
                    strategy_id=r["strategy_id"],
                    underlying=r["underlying"],
                    expiry=r["expiry"],
                    strike=r["strike"],
                    option_type=OptionType(r["option_type"]),
                    transaction_type=TransactionType(r["transaction_type"]),
                    leg_type=LegType(r["leg_type"]),
                    quantity=r["quantity"],
                    entry_price=r["entry_price"],
                    entry_time=r["entry_time"],
                    current_price=r["current_price"],
                    stop_loss_price=r["stop_loss_price"],
                    hard_stop_loss_price=r["hard_stop_loss_price"],
                    stop_loss_percent=r["stop_loss_percent"],
                    hard_stop_loss_percent=r["hard_stop_loss_percent"],
                    status=LegStatus(r["status"]),
                    exit_price=r["exit_price"],
                    exit_time=r["exit_time"],
                    exit_reason=ExitReason(r["exit_reason"]) if r["exit_reason"] else None,
                    pnl=r["pnl"],
                    pnl_pct=r["pnl_pct"],
                    filled_quantity=r["filled_quantity"],
                    charges=r["charges"],
                ))
            return legs

    def save_order(self, order: Order):
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
            INSERT INTO orders (
                order_id, strategy_id, run_id, leg_id, timestamp, underlying, expiry, strike, option_type,
                transaction_type, quantity, requested_price, executed_price, filled_quantity, remaining_quantity,
                status, reason, source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(order_id) DO UPDATE SET
                executed_price = excluded.executed_price,
                filled_quantity = excluded.filled_quantity,
                remaining_quantity = excluded.remaining_quantity,
                status = excluded.status,
                reason = excluded.reason
            """, (
                order.order_id, order.strategy_id, order.run_id, order.leg_id, order.timestamp,
                order.underlying, order.expiry, order.strike, order.option_type.value, order.transaction_type.value,
                order.quantity, order.requested_price, order.executed_price, order.filled_quantity,
                order.remaining_quantity, order.status.value, order.reason, order.source
            ))
            conn.commit()


# Global DB Manager Instance
db_manager = DatabaseManager()
