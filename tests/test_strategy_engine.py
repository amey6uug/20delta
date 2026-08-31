"""Comprehensive Test Suite for Options Strategy, Risk Engine, and Edge Cases (Phases 34 & 35)."""

from datetime import date, datetime, time
import pytest

from engine.broker_adapter import PaperBrokerAdapter
from engine.calendar import (
    calculate_dte,
    format_date_day,
    format_timestamp_day,
    get_expiry_date,
    is_holiday,
    is_trading_day,
    is_weekend,
    is_within_strategy_window,
    parse_date,
)
from engine.config_service import ConfigService, config_service
from engine.margin_calc import MarginCalculator
from engine.market_data import MarketDataService
from engine.models import (
    AuditRecord,
    BasketMetrics,
    ExitReason,
    LegStatus,
    LegType,
    MarketDataStatus,
    OptionLeg,
    OptionType,
    Order,
    OrderStatus,
    StrategyConfig,
    StrategyState,
    TransactionType,
)
from engine.risk_engine import RiskEngine
from engine.strategy_engine import StrategyExecutionSession
from engine.strike_selector import StrikeSelector


# ── Tests 1 & 2: Strike Selection ─────────────────────────────────────────────

def test_nifty_strike_selection():
    cfg = config_service.get_config("strangle_20d")
    sel = StrikeSelector.select_strikes("NIFTY", 24260.0, "10-09-2026", cfg, custom_expiry="16-09-2026")
    assert sel.is_valid
    assert sel.atm_strike == 24250.0
    assert sel.ce_main_strike == 24450.0
    assert sel.pe_main_strike == 24050.0
    assert sel.ce_hedge_strike == 24750.0
    assert sel.pe_hedge_strike == 23750.0


def test_sensex_strike_selection():
    cfg = config_service.get_config("theta_shifting")
    sel = StrikeSelector.select_strikes("SENSEX", 79840.0, "10-09-2026", cfg, custom_expiry="18-09-2026")
    assert sel.is_valid
    assert sel.atm_strike == 79800.0
    assert sel.ce_main_strike == 80100.0
    assert sel.pe_main_strike == 79500.0


# ── Tests 3 & 4: Expiry Resolution ────────────────────────────────────────────

def test_nifty_and_sensex_expiry():
    t_date = date(2026, 9, 10)  # Thursday
    n_exp = get_expiry_date("NIFTY", t_date)
    s_exp = get_expiry_date("SENSEX", t_date)
    assert n_exp >= t_date
    assert s_exp >= t_date
    assert calculate_dte(t_date, n_exp) >= 0


# ── Test 5: Date/Day Formatting ───────────────────────────────────────────────

def test_date_formatting():
    d = date(2026, 9, 10)  # 10-09-2026 is Thursday
    formatted = format_date_day(d)
    assert formatted == "10-09-2026, Thursday"

    dt = datetime(2026, 9, 10, 9, 45, 0)
    ts_formatted = format_timestamp_day(dt)
    assert "10-09-2026, Thursday" in ts_formatted
    assert "09:45:00 AM" in ts_formatted


# ── Test 6: Holiday and Weekend Detection ─────────────────────────────────────

def test_holiday_and_weekend():
    is_hol, hol_name = is_holiday(date(2026, 1, 26))
    assert is_hol is True
    assert "Republic Day" in hol_name

    sat = date(2026, 9, 12)
    assert is_weekend(sat) is True
    assert is_trading_day(sat) is False

    thu = date(2026, 9, 10)
    assert is_trading_day(thu) is True


# ── Tests 7 & 8: 80% Stop Loss (BUY and SELL) ─────────────────────────────────

def test_buy_leg_80_percent_stop_loss():
    leg = OptionLeg(
        leg_id="TEST_BUY",
        strategy_id="strangle_20d",
        underlying="NIFTY",
        expiry="16-09-2026",
        strike=24700,
        option_type=OptionType.CE,
        transaction_type=TransactionType.BUY,
        leg_type=LegType.HEDGE,
        quantity=65,
        entry_price=100.0,
        entry_time="09:45 AM",
        stop_loss_percent=80.0,
        hard_stop_loss_percent=100.0,
    )
    leg.calculate_stop_loss_prices()
    assert leg.stop_loss_price == 20.0
    assert leg.hard_stop_loss_price == 0.0

    hit, reason, _ = RiskEngine.evaluate_leg_stop_loss(leg, 25.0)
    assert hit is False

    hit, reason, _ = RiskEngine.evaluate_leg_stop_loss(leg, 20.0)
    assert hit is True
    assert reason == ExitReason.NORMAL_STOP_LOSS


def test_sell_leg_80_percent_stop_loss():
    leg = OptionLeg(
        leg_id="TEST_SELL",
        strategy_id="strangle_20d",
        underlying="NIFTY",
        expiry="16-09-2026",
        strike=24400,
        option_type=OptionType.CE,
        transaction_type=TransactionType.SELL,
        leg_type=LegType.MAIN,
        quantity=65,
        entry_price=100.0,
        entry_time="09:45 AM",
        stop_loss_percent=80.0,
        hard_stop_loss_percent=100.0,
    )
    leg.calculate_stop_loss_prices()
    assert leg.stop_loss_price == 180.0
    assert leg.hard_stop_loss_price == 200.0

    hit, reason, _ = RiskEngine.evaluate_leg_stop_loss(leg, 150.0)
    assert hit is False

    hit, reason, _ = RiskEngine.evaluate_leg_stop_loss(leg, 180.0)
    assert hit is True
    assert reason == ExitReason.NORMAL_STOP_LOSS


# ── Test 9: 100% Hard Stop Loss ───────────────────────────────────────────────

def test_sell_leg_100_percent_hard_stop():
    leg = OptionLeg(
        leg_id="TEST_HARD_SL",
        strategy_id="strangle_20d",
        underlying="NIFTY",
        expiry="16-09-2026",
        strike=24400,
        option_type=OptionType.CE,
        transaction_type=TransactionType.SELL,
        leg_type=LegType.MAIN,
        quantity=65,
        entry_price=100.0,
        entry_time="09:45 AM",
        stop_loss_percent=80.0,
        hard_stop_loss_percent=100.0,
    )
    leg.calculate_stop_loss_prices()
    hit, reason, _ = RiskEngine.evaluate_leg_stop_loss(leg, 205.0)
    assert hit is True
    assert reason == ExitReason.HARD_STOP_LOSS


# ── Tests 10 & 11: 1% Profit Lock & Floor Protection ──────────────────────────

def test_profit_lock_activation_and_floor_exit():
    cfg = StrategyConfig(
        strategy_id="test_strat",
        strategy_name="Test Strategy",
        capital=1_000_000.0,
        profit_lock_trigger_percent=1.0,
        profit_lock_floor_percent=1.0,
        profit_target_percent=2.0,
    )

    leg = OptionLeg(
        leg_id="LEG1", strategy_id="test_strat", underlying="NIFTY", expiry="16-09-2026",
        strike=24400, option_type=OptionType.CE, transaction_type=TransactionType.SELL,
        leg_type=LegType.MAIN, quantity=65, entry_price=100.0, entry_time="09:45 AM",
    )

    leg.pnl = 10500.0
    metrics = RiskEngine.calculate_basket_metrics([leg], cfg)
    assert metrics.profit_lock_active is True

    leg.pnl = 15000.0
    metrics = RiskEngine.calculate_basket_metrics([leg], cfg, profit_lock_active=True)
    should_exit, _, _, is_locked = RiskEngine.evaluate_basket_exits(metrics, cfg, current_time_ist=datetime(2026, 9, 10, 11, 0))
    assert should_exit is False
    assert is_locked is True

    leg.pnl = 9800.0
    metrics = RiskEngine.calculate_basket_metrics([leg], cfg, profit_lock_active=True)
    should_exit, exit_reason, msg, _ = RiskEngine.evaluate_basket_exits(metrics, cfg, current_time_ist=datetime(2026, 9, 10, 11, 30))
    assert should_exit is True
    assert exit_reason == ExitReason.PROFIT_LOCK


# ── Tests 12 & 13: 2% Profit Target (Exit ALL legs) ───────────────────────────

def test_profit_target_exit_all_legs():
    cfg = StrategyConfig(
        strategy_id="test_strat",
        strategy_name="Test Strategy",
        capital=1_000_000.0,
        profit_target_percent=2.0,
    )
    leg1 = OptionLeg(
        leg_id="L1", strategy_id="test_strat", underlying="NIFTY", expiry="16-09-2026",
        strike=24400, option_type=OptionType.CE, transaction_type=TransactionType.SELL,
        leg_type=LegType.MAIN, quantity=65, entry_price=100.0, entry_time="09:45 AM", pnl=12000.0,
    )
    leg2 = OptionLeg(
        leg_id="L2", strategy_id="test_strat", underlying="NIFTY", expiry="16-09-2026",
        strike=24000, option_type=OptionType.PE, transaction_type=TransactionType.SELL,
        leg_type=LegType.MAIN, quantity=65, entry_price=100.0, entry_time="09:45 AM", pnl=8500.0,
    )
    metrics = RiskEngine.calculate_basket_metrics([leg1, leg2], cfg)
    assert metrics.net_pnl == 20500.0

    should_exit, exit_reason, msg, _ = RiskEngine.evaluate_basket_exits(metrics, cfg, current_time_ist=datetime(2026, 9, 10, 12, 0))
    assert should_exit is True
    assert exit_reason == ExitReason.PROFIT_TARGET


# ── Test 14: 03:00 PM Forced Exit ─────────────────────────────────────────────

def test_forced_3pm_exit():
    cfg = StrategyConfig(
        strategy_id="test_strat", strategy_name="Test Strategy", capital=1_000_000.0, forced_exit_time="15:00"
    )
    metrics = RiskEngine.calculate_basket_metrics([], cfg)

    t_259 = datetime(2026, 9, 10, 14, 59, 59)
    exit_259, _, _, _ = RiskEngine.evaluate_basket_exits(metrics, cfg, current_time_ist=t_259)
    assert exit_259 is False

    t_300 = datetime(2026, 9, 10, 15, 0, 0)
    exit_300, reason_300, _, _ = RiskEngine.evaluate_basket_exits(metrics, cfg, current_time_ist=t_300)
    assert exit_300 is True
    assert reason_300 == ExitReason.TIME_EXIT


# ── Test 15: Entry Before 09:45 Rejected ──────────────────────────────────────

def test_entry_time_window():
    ok_944, _ = is_within_strategy_window("09:45", "15:00", now=datetime(2026, 9, 10, 9, 44, 59))
    assert ok_944 is False

    ok_945, _ = is_within_strategy_window("09:45", "15:00", now=datetime(2026, 9, 10, 9, 45, 0))
    assert ok_945 is True


# ── Test 16: SENSEX ATM Short Prohibited ──────────────────────────────────────

def test_sensex_atm_short_prohibited():
    is_ok, msg = RiskEngine.validate_sensex_atm_short("SENSEX", TransactionType.SELL, 79800.0, 79800.0)
    assert is_ok is False
    assert "SENSEX ATM SHORTING IS PROHIBITED BY STRATEGY RISK RULES." in msg

    is_ok_otm, _ = RiskEngine.validate_sensex_atm_short("SENSEX", TransactionType.SELL, 80100.0, 79800.0)
    assert is_ok_otm is True


# ── Test 17: Hedge Placement Requirement ──────────────────────────────────────

def test_hedge_placement_requirement():
    cfg = config_service.get_config("strangle_20d")
    broker = PaperBrokerAdapter(initial_capital=cfg.capital)
    session = StrategyExecutionSession(config=cfg, broker_adapter=broker)

    success, _ = session.execute_entry(
        spot_price=24250.0,
        trading_date="10-09-2026",
        entry_time_str="09:45 AM",
        ce_main_premium=48.0,
        pe_main_premium=50.0,
        ce_hedge_premium=12.0,
        pe_hedge_premium=11.5,
        current_datetime=datetime(2026, 9, 10, 9, 45, 0),
    )
    assert success is True
    assert session.state == StrategyState.ACTIVE
    assert len(session.legs) == 4
    hedge_legs = [l for l in session.legs if l.leg_type == LegType.HEDGE]
    assert len(hedge_legs) == 2


# ── Test 18: Partial Fills ───────────────────────────────────────────────────

def test_partial_fill_handling():
    leg = OptionLeg(
        leg_id="PARTIAL_LEG",
        strategy_id="strangle_20d",
        underlying="NIFTY",
        expiry="16-09-2026",
        strike=24400,
        option_type=OptionType.CE,
        transaction_type=TransactionType.SELL,
        leg_type=LegType.MAIN,
        quantity=100,
        filled_quantity=50,
        entry_price=100.0,
        entry_time="09:45 AM",
    )
    leg.update_pnl(80.0)
    assert leg.pnl == 1000.0


# ── Test 19 & 20: Stale Data & Validation ─────────────────────────────────────

def test_market_data_validation():
    srv = MarketDataService()
    freshness_live = srv.evaluate_freshness(datetime.now().isoformat())
    assert freshness_live in (MarketDataStatus.LIVE, MarketDataStatus.DEMO)

    freshness_unavail = srv.evaluate_freshness("")
    assert freshness_unavail == MarketDataStatus.UNAVAILABLE


# ── Test 22 & 23: Capital & Margin Calculations ──────────────────────────────

def test_margin_and_capital_calculation():
    breakdown = MarginCalculator.calculate_margin(
        underlying="NIFTY",
        short_quantity=65,
        short_premium=50.0,
        hedge_quantity=65,
        hedge_premium=12.0,
        hedge_distance_points=300.0,
        strategy_capital=1_000_000.0,
    )
    assert breakdown.naked_short_margin > 0
    assert breakdown.hedge_benefit > 0
    assert breakdown.net_margin_required < breakdown.naked_short_margin
    assert breakdown.available_capital_after_trade > 0
    assert breakdown.is_sufficient_capital is True


# ── Test 24: Configuration Versioning ─────────────────────────────────────────

def test_config_versioning():
    cfg = config_service.get_config("strangle_20d")
    old_ver = cfg.version
    cfg.profit_target_percent = 5.0
    success, msg, new_ver = config_service.update_config(cfg, user="test_suite")
    assert success is True
    assert new_ver == old_ver + 1

    reloaded = config_service.get_config("strangle_20d")
    assert reloaded.profit_target_percent == 5.0
    assert reloaded.version == new_ver


# ── Edge Cases A – N (Phase 35) ───────────────────────────────────────────────

def test_edge_case_a_profit_lock_floor_breached():
    """Edge Case A: Profit reaches 1%, then falls below 1% -> EXIT ALL."""
    cfg = StrategyConfig(strategy_id="strat_a", strategy_name="A", capital=1_000_000.0)
    leg = OptionLeg("L_A", "strat_a", "NIFTY", "16-09-2026", 24400, OptionType.CE, TransactionType.SELL, LegType.MAIN, 65, 100.0, "09:45 AM")
    
    # 1. P&L hits +₹12,000 (Lock activated)
    leg.pnl = 12000.0
    metrics = RiskEngine.calculate_basket_metrics([leg], cfg)
    assert metrics.profit_lock_active is True

    # 2. P&L drops to +₹9,500 (< ₹10,000 floor)
    leg.pnl = 9500.0
    metrics = RiskEngine.calculate_basket_metrics([leg], cfg, profit_lock_active=True)
    should_exit, reason, _, _ = RiskEngine.evaluate_basket_exits(metrics, cfg, current_time_ist=datetime(2026, 9, 10, 11, 0))
    assert should_exit is True
    assert reason == ExitReason.PROFIT_LOCK


def test_edge_case_b_profit_lock_then_reaches_target():
    """Edge Case B: Profit reaches 1%, then reaches 2% -> EXIT ALL."""
    cfg = StrategyConfig(strategy_id="strat_b", strategy_name="B", capital=1_000_000.0)
    leg = OptionLeg("L_B", "strat_b", "NIFTY", "16-09-2026", 24400, OptionType.CE, TransactionType.SELL, LegType.MAIN, 65, 100.0, "09:45 AM")
    
    # 1. Hits 1%
    leg.pnl = 10000.0
    metrics = RiskEngine.calculate_basket_metrics([leg], cfg)
    assert metrics.profit_lock_active is True

    # 2. Continues to 2% (₹20,000)
    leg.pnl = 20000.0
    metrics = RiskEngine.calculate_basket_metrics([leg], cfg, profit_lock_active=True)
    should_exit, reason, _, _ = RiskEngine.evaluate_basket_exits(metrics, cfg, current_time_ist=datetime(2026, 9, 10, 12, 0))
    assert should_exit is True
    assert reason == ExitReason.PROFIT_TARGET


def test_edge_case_c_single_leg_stop_loss():
    """Edge Case C: One leg hits 80% SL -> That leg exits."""
    leg_ce = OptionLeg("CE", "strat_c", "NIFTY", "16-09-2026", 24400, OptionType.CE, TransactionType.SELL, LegType.MAIN, 65, 100.0, "09:45 AM")
    leg_pe = OptionLeg("PE", "strat_c", "NIFTY", "16-09-2026", 24000, OptionType.PE, TransactionType.SELL, LegType.MAIN, 65, 100.0, "09:45 AM")
    leg_ce.calculate_stop_loss_prices()
    leg_pe.calculate_stop_loss_prices()

    # CE moves to 180 (SL Hit), PE stays at 80 (Safe)
    hit_ce, reason_ce, _ = RiskEngine.evaluate_leg_stop_loss(leg_ce, 180.0)
    hit_pe, reason_pe, _ = RiskEngine.evaluate_leg_stop_loss(leg_pe, 80.0)

    assert hit_ce is True
    assert reason_ce == ExitReason.NORMAL_STOP_LOSS
    assert hit_pe is False


def test_edge_case_d_gap_hard_stop_loss():
    """Edge Case D: 80% SL fails and premium jumps to 100% -> Hard exit."""
    leg = OptionLeg("HARD_SL", "strat_d", "NIFTY", "16-09-2026", 24400, OptionType.CE, TransactionType.SELL, LegType.MAIN, 65, 100.0, "09:45 AM")
    leg.calculate_stop_loss_prices()

    # Premium jumps straight to ₹200
    hit, reason, _ = RiskEngine.evaluate_leg_stop_loss(leg, 200.0)
    assert hit is True
    assert reason == ExitReason.HARD_STOP_LOSS


def test_edge_case_e_sensex_atm_short_rejected():
    """Edge Case E: SENSEX ATM SELL requested -> Order rejected."""
    is_ok, reason = RiskEngine.validate_sensex_atm_short("SENSEX", TransactionType.SELL, 80000.0, 80000.0)
    assert is_ok is False
    assert "SENSEX ATM SHORTING IS PROHIBITED BY STRATEGY RISK RULES." in reason


def test_edge_case_f_and_g_entry_timing():
    """Edge Cases F & G: Entry at 09:44 rejected, Entry at 09:45 allowed."""
    ok_944, _ = is_within_strategy_window("09:45", "15:00", now=datetime(2026, 9, 10, 9, 44, 0))
    ok_945, _ = is_within_strategy_window("09:45", "15:00", now=datetime(2026, 9, 10, 9, 45, 0))
    assert ok_944 is False
    assert ok_945 is True


def test_edge_case_h_and_i_forced_exit_timing():
    """Edge Cases H & I: Position at 02:59:59 continues, Position at 03:00 exits all."""
    cfg = StrategyConfig(strategy_id="strat_hi", strategy_name="HI", capital=1_000_000.0)
    metrics = BasketMetrics(capital=1_000_000.0)

    exit_259, _, _, _ = RiskEngine.evaluate_basket_exits(metrics, cfg, current_time_ist=datetime(2026, 9, 10, 14, 59, 59))
    exit_300, reason, _, _ = RiskEngine.evaluate_basket_exits(metrics, cfg, current_time_ist=datetime(2026, 9, 10, 15, 0, 0))

    assert exit_259 is False
    assert exit_300 is True
    assert reason == ExitReason.TIME_EXIT


def test_edge_case_j_market_data_unavailable():
    """Edge Case J: Market data unavailable -> No false live P&L."""
    srv = MarketDataService()
    freshness = srv.evaluate_freshness("")
    assert freshness == MarketDataStatus.UNAVAILABLE


def test_edge_case_k_hedge_failure_protects_naked_short():
    """Edge Case K: Hedge fails -> Do not leave intended naked short exposure."""
    class FailingHedgeBroker(PaperBrokerAdapter):
        def place_order(self, order: Order, fill_ratio: float = 1.0) -> Order:
            if order.transaction_type == TransactionType.BUY:
                order.status = OrderStatus.REJECTED
                return order
            return super().place_order(order, fill_ratio)

    cfg = config_service.get_config("strangle_20d")
    session = StrategyExecutionSession(config=cfg, broker_adapter=FailingHedgeBroker())
    success, msg = session.execute_entry(
        spot_price=24250.0,
        trading_date="10-09-2026",
        entry_time_str="09:45 AM",
        ce_main_premium=48.0,
        pe_main_premium=50.0,
        ce_hedge_premium=12.0,
        pe_hedge_premium=11.5,
        current_datetime=datetime(2026, 9, 10, 9, 45, 0),
    )
    assert success is False
    assert session.state == StrategyState.HEDGE_FAILURE
    assert "Hedge Placement Failed" in msg


def test_edge_case_l_partial_fill_risk_scaling():
    """Edge Case L: Partial fill -> Risk calculated only on filled quantity."""
    leg = OptionLeg("L_PARTIAL", "strat_l", "NIFTY", "16-09-2026", 24400, OptionType.CE, TransactionType.SELL, LegType.MAIN, 100, 100.0, "09:45 AM", filled_quantity=40)
    leg.update_pnl(90.0)  # +10 profit per unit
    assert leg.pnl == 400.0  # 40 * 10 = 400 (not 100 * 10 = 1000)


def test_edge_case_m_and_n_holiday_and_weekend():
    """Edge Cases M & N: Trading holiday & weekend -> No strategy execution."""
    assert is_trading_day(date(2026, 1, 26)) is False  # Republic Day holiday
    assert is_trading_day(date(2026, 9, 12)) is False  # Saturday weekend
