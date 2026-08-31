"""Strategy Configuration Service.

Handles:
- CRUD operations for Strategy Configurations
- Comprehensive parameter validation
- Seed default strategy configurations (Phase 1 default values)
- Version incrementing and audit tracking
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from engine.db import db_manager
from engine.models import AuditRecord, StrategyConfig

DEFAULT_STRATEGIES = [
    StrategyConfig(
        strategy_id="strangle_20d",
        strategy_name="20Δ Short Strangle",
        underlying="NIFTY",
        enabled=True,
        capital=1_000_000.0,
        stop_loss_percent=80.0,
        hard_stop_loss_percent=100.0,
        profit_lock_trigger_percent=1.0,
        profit_lock_floor_percent=1.0,
        profit_target_percent=2.0,
        entry_time="09:45",
        forced_exit_time="15:00",
        hedge_required=True,
        nifty_otm_distance=200,
        nifty_near_expiry_distance=100,
        nifty_hedge_distance=300,
        sensex_otm_distance=300,
        sensex_near_expiry_distance=100,
        sensex_hedge_distance=500,
        allow_atm_short=False,
        allow_reentry=False,
        max_positions=4,
        version=1,
    ),
    StrategyConfig(
        strategy_id="theta_shifting",
        strategy_name="Theta Shifting Straddle",
        underlying="SENSEX",
        enabled=True,
        capital=1_000_000.0,
        stop_loss_percent=80.0,
        hard_stop_loss_percent=100.0,
        profit_lock_trigger_percent=1.0,
        profit_lock_floor_percent=1.0,
        profit_target_percent=2.0,
        entry_time="09:45",
        forced_exit_time="15:00",
        hedge_required=True,
        nifty_otm_distance=200,
        nifty_near_expiry_distance=100,
        nifty_hedge_distance=300,
        sensex_otm_distance=300,
        sensex_near_expiry_distance=100,
        sensex_hedge_distance=500,
        allow_atm_short=False,  # Hard risk safety rule
        allow_reentry=False,
        max_positions=4,
        version=1,
    ),
]


class ConfigService:
    def __init__(self):
        self._ensure_defaults()

    def _ensure_defaults(self):
        """Seed default strategies if database is empty."""
        for strat in DEFAULT_STRATEGIES:
            existing = db_manager.get_strategy_config(strat.strategy_id)
            if not existing:
                db_manager.save_strategy_config(strat, user="system_init")

    def validate_config(self, cfg: StrategyConfig) -> Tuple[bool, List[str]]:
        """
        Validate all strategy configuration parameters.
        Returns (is_valid, list_of_error_messages).
        """
        errors = []

        if not cfg.strategy_name.strip():
            errors.append("Strategy Name cannot be empty.")

        if cfg.capital <= 0:
            errors.append("Strategy Capital must be greater than 0.")

        # Stop loss validation
        if cfg.stop_loss_percent <= 0:
            errors.append("Stop Loss % must be greater than 0%.")

        if cfg.hard_stop_loss_percent < cfg.stop_loss_percent:
            errors.append("Hard Stop Loss % must be greater than or equal to Stop Loss % (e.g. 100% >= 80%).")

        # Profit lock & target validation
        if cfg.profit_lock_trigger_percent <= 0:
            errors.append("Profit Lock Trigger % must be greater than 0%.")

        if cfg.profit_lock_floor_percent > cfg.profit_lock_trigger_percent:
            errors.append("Profit Lock Floor % cannot exceed Profit Lock Trigger %.")

        if cfg.profit_target_percent <= cfg.profit_lock_trigger_percent:
            errors.append("Profit Target % must be strictly greater than Profit Lock Trigger % (e.g. 2% > 1%).")

        # Timing validation
        try:
            eh, em = map(int, cfg.entry_time.split(":"))
            xh, xm = map(int, cfg.forced_exit_time.split(":"))
            entry_minutes = eh * 60 + em
            exit_minutes = xh * 60 + xm

            if entry_minutes < 9 * 60 + 15 or entry_minutes > 15 * 60 + 30:
                errors.append("Entry Time must be within market hours (09:15 to 15:30).")

            if exit_minutes < 9 * 60 + 15 or exit_minutes > 15 * 60 + 30:
                errors.append("Forced Exit Time must be within market hours (09:15 to 15:30).")

            if entry_minutes >= exit_minutes:
                errors.append("Entry Time must be strictly earlier than Forced Exit Time.")
        except Exception:
            errors.append("Invalid time format. Use HH:MM in 24-hour format (e.g. '09:45' and '15:00').")

        # Distance validation
        if cfg.nifty_otm_distance <= 0 or cfg.sensex_otm_distance <= 0:
            errors.append("OTM distances must be positive integers.")

        if cfg.hedge_required and (cfg.nifty_hedge_distance <= 0 or cfg.sensex_hedge_distance <= 0):
            errors.append("Hedge distances must be positive when hedge is required.")

        return len(errors) == 0, errors

    def get_config(self, strategy_id: str) -> Optional[StrategyConfig]:
        return db_manager.get_strategy_config(strategy_id)

    def list_configs(self) -> List[StrategyConfig]:
        return db_manager.list_strategy_configs()

    def update_config(self, cfg: StrategyConfig, user: str = "admin") -> Tuple[bool, str, int]:
        is_valid, errors = self.validate_config(cfg)
        if not is_valid:
            return False, "; ".join(errors), 0

        old_cfg = db_manager.get_strategy_config(cfg.strategy_id)
        new_ver = db_manager.save_strategy_config(cfg, user=user)

        # Log audit event
        db_manager.log_audit(
            AuditRecord(
                strategy_id=cfg.strategy_id,
                event="STRATEGY_CONFIG_UPDATED",
                reason=f"Version updated from {old_cfg.version if old_cfg else 0} to {new_ver}",
                old_state=f"v{old_cfg.version}" if old_cfg else "None",
                new_state=f"v{new_ver}",
                user=user,
                metadata=cfg.to_dict(),
            )
        )
        return True, f"Strategy updated successfully to version {new_ver}", new_ver

    def reset_to_defaults(self, strategy_id: str, user: str = "admin") -> Tuple[bool, str]:
        for strat in DEFAULT_STRATEGIES:
            if strat.strategy_id == strategy_id:
                new_ver = db_manager.save_strategy_config(strat, user=user)
                db_manager.log_audit(
                    AuditRecord(
                        strategy_id=strategy_id,
                        event="STRATEGY_CONFIG_RESET",
                        reason=f"Reset to default configuration (v{new_ver})",
                        old_state="Custom",
                        new_state=f"v{new_ver}",
                        user=user,
                    )
                )
                return True, f"Reset to default parameters (v{new_ver})."
        return False, "Strategy ID not found in default list."


config_service = ConfigService()
