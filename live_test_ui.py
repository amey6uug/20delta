"""Live Market Test — Interactive Paper Trading Mode.

Uses the EXACT SAME strategy and risk engine as Backtest.
Simulates order routing and paper execution with real/live data or market quotes.
"""

from __future__ import annotations

from datetime import datetime
import pandas as pd
import streamlit as st

from engine.broker_adapter import PaperBrokerAdapter
from engine.calendar import format_date_day, format_timestamp_day, get_current_ist_time
from engine.config_service import config_service
from engine.market_data import market_data_service
from engine.models import ExitReason, MarketDataStatus, OptionType, StrategyState, TransactionType
from engine.strategy_engine import StrategyExecutionSession
from engine.strike_selector import StrikeSelector
from theme import (
    BLUE, GREEN, RED, GOLD, PURPLE, MUTED,
    color_for, fmt_inr, page_header, render_risk_banner, render_table,
)


def render_live_test_page():
    page_header(
        "Live Market Test (Paper Trading)",
        subtitle="Zero-risk execution using the unified production strategy engine and live market quotes",
        badge="paper",
    )

    now_ist = get_current_ist_time()
    st.markdown(
        f'<div style="text-align:center; color:#8b949e; margin-bottom:12px;">'
        f'Session Date: <b>{format_date_day(now_ist)}</b> &nbsp;|&nbsp; Local Market Time: <b>{format_timestamp_day(now_ist)}</b>'
        f'</div>',
        unsafe_allow_html=True,
    )

    cfg = config_service.get_config("strangle_20d")
    if not cfg:
        st.error("Strategy configuration not found.")
        return

    # Check live market data connectivity
    n_spot, n_chg, n_pct, n_status = market_data_service.get_index_spot_price("NIFTY")
    s_spot, s_chg, s_pct, s_status = market_data_service.get_index_spot_price("SENSEX")

    if n_status == MarketDataStatus.UNAVAILABLE or s_status == MarketDataStatus.UNAVAILABLE:
        st.warning("⚠️ Live market data connection unavailable. Live paper test is paused.")
        return

    # ── Session State Management ───────────────────────────────────────────────
    if "paper_session" not in st.session_state:
        paper_broker = PaperBrokerAdapter(initial_capital=cfg.capital)
        st.session_state["paper_session"] = StrategyExecutionSession(
            config=cfg,
            broker_adapter=paper_broker,
        )

    session: StrategyExecutionSession = st.session_state["paper_session"]

    result = st.session_state.pop("entry_result", None)
    if result:
        kind, text = result
        (st.success if kind == "success" else st.error)(
            ("✅ " if kind == "success" else "❌ ") + text
        )

    # ── Control Bar ────────────────────────────────────────────────────────────
    st.markdown("##### 🎮 Paper Trading Session Controls")
    with st.container(border=True):
        col_s1, col_s2, col_s3, col_s4 = st.columns([2, 1.5, 1.5, 1.5])
        with col_s1:
            st.write(f"**Strategy:** {cfg.strategy_name} ({cfg.underlying})")
            st.write(f"**State:** `{session.state.value}`")
        with col_s2:
            st.write(f"**Capital:** {fmt_inr(cfg.capital)}")
            st.write(f"**Net P&L:** {fmt_inr(session.metrics.net_pnl)} ({session.metrics.net_pnl_pct:+.2f}%)")
        with col_s3:
            enter_btn = st.button("▶️ Execute 09:45 Entry", type="primary", use_container_width=True, disabled=(session.state != StrategyState.IDLE))
        with col_s4:
            reset_btn = st.button("🔄 Reset Paper Session", use_container_width=True)

    if reset_btn:
        st.session_state["paper_session"] = StrategyExecutionSession(
            config=cfg,
            broker_adapter=PaperBrokerAdapter(initial_capital=cfg.capital),
        )
        st.rerun()

    if enter_btn:
        trading_d = now_ist.strftime("%d-%m-%Y")

        # Premiums must come from the market. There is no safe placeholder for an
        # option price, so entry is refused outright when quotes are unavailable.
        if n_status != MarketDataStatus.LIVE or n_spot <= 0:
            success, msg = False, (
                f"No live {cfg.underlying} spot price - cannot select strikes. "
                f"{market_data_service.get_last_error()}"
            )
        else:
            sel = StrikeSelector.select_strikes(cfg.underlying, n_spot, trading_d, cfg)
            if not sel.is_valid:
                success, msg = False, sel.rejection_reason
            else:
                wanted = [
                    ("ce_main_premium", sel.ce_main_strike, "CE"),
                    ("pe_main_premium", sel.pe_main_strike, "PE"),
                    ("ce_hedge_premium", sel.ce_hedge_strike, "CE"),
                    ("pe_hedge_premium", sel.pe_hedge_strike, "PE"),
                ]
                premiums, missing = {}, []
                for name, strike, opt in wanted:
                    if strike is None:            # hedges are optional in config
                        premiums[name] = 0.0
                        continue
                    ltp, q_status = market_data_service.get_option_ltp(
                        cfg.underlying, sel.expiry, strike, opt
                    )
                    if q_status != MarketDataStatus.LIVE:
                        missing.append(f"{strike:,.0f}{opt}")
                    premiums[name] = ltp

                if missing:
                    success, msg = False, (
                        "No live quotes for " + ", ".join(missing) + ". "
                        + (market_data_service.get_last_error() or "Broker not connected.")
                    )
                else:
                    success, msg = session.execute_entry(
                        spot_price=n_spot,
                        trading_date=trading_d,
                        entry_time_str="09:45:00 AM",
                        num_lots=1,
                        current_datetime=now_ist,
                        **premiums,
                    )
        # st.rerun() discards anything rendered in this run, so the banner has to
        # survive in session_state and be drawn on the next pass instead.
        st.session_state["entry_result"] = ("success" if success else "error", msg)
        st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Risk Simulator / Tick Injector ─────────────────────────────────────────
    st.markdown("##### ⚡ Interactive Price & Risk Scenario Simulator")
    with st.container(border=True):
        st.caption("Simulate price movements to test per-leg 80% SL, 100% Hard Stop, 1% Profit Lock, 2% Target, and 3 PM Exit in real time:")
        t1, t2, t3, t4, t5 = st.columns(5)
        with t1:
            if st.button("📈 +₹10k (Lock Active)", use_container_width=True, disabled=session.state == StrategyState.IDLE):
                prices = {leg.leg_id: leg.entry_price * 0.40 for leg in session.legs}
                session.process_tick(prices, current_datetime=now_ist)
                st.rerun()
        with t2:
            if st.button("🚀 +₹20k (Target Hit)", use_container_width=True, disabled=session.state == StrategyState.IDLE):
                prices = {leg.leg_id: 0.1 for leg in session.legs}
                session.process_tick(prices, current_datetime=now_ist)
                st.rerun()
        with t3:
            if st.button("💥 CE 80% Stop Loss", use_container_width=True, disabled=session.state == StrategyState.IDLE):
                prices = {}
                for leg in session.legs:
                    if leg.option_type == OptionType.CE and leg.transaction_type == TransactionType.SELL:
                        prices[leg.leg_id] = leg.stop_loss_price + 1.0
                    else:
                        prices[leg.leg_id] = leg.entry_price
                session.process_tick(prices, current_datetime=now_ist)
                st.rerun()
        with t4:
            if st.button("⚡ CE 100% Hard Stop", use_container_width=True, disabled=session.state == StrategyState.IDLE):
                prices = {}
                for leg in session.legs:
                    if leg.option_type == OptionType.CE and leg.transaction_type == TransactionType.SELL:
                        prices[leg.leg_id] = leg.hard_stop_loss_price + 5.0
                    else:
                        prices[leg.leg_id] = leg.entry_price
                session.process_tick(prices, current_datetime=now_ist)
                st.rerun()
        with t5:
            if st.button("⏰ 03:00 PM Forced Exit", use_container_width=True, disabled=session.state == StrategyState.IDLE):
                sim_exit_time = now_ist.replace(hour=15, minute=0, second=5)
                prices = {leg.leg_id: leg.current_price for leg in session.legs}
                session.process_tick(prices, current_datetime=sim_exit_time)
                st.rerun()

    # ── Live Paper Positions Table ─────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("##### 📋 Open Paper Positions")
    if session.legs:
        leg_rows = []
        for leg in session.legs:
            leg_rows.append({
                "Leg ID": leg.leg_id,
                "Underlying": leg.underlying,
                "Expiry": leg.expiry,
                "Strike": leg.strike,
                "Type": leg.option_type.value,
                "Side": leg.transaction_type.value,
                "Role": leg.leg_type.value,
                "Qty": leg.quantity,
                "Entry Premium": f"₹{leg.entry_price:.2f}",
                "Current LTP": f"₹{leg.current_price:.2f}",
                "SL (80%)": f"₹{leg.stop_loss_price:.2f}",
                "Hard SL (100%)": f"₹{leg.hard_stop_loss_price:.2f}",
                "P&L (₹)": f"₹{leg.pnl:+,.2f}",
                "P&L (%)": f"{leg.pnl_pct:+.1f}%",
                "Status": leg.status.value,
            })
        render_table(pd.DataFrame(leg_rows))
    else:
        st.info("No active paper positions. Click 'Execute 09:45 Entry' above to initiate trade.")

    # ── Basket & Risk Cards ────────────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    b1, b2, b3, b4 = st.columns(4)
    b1.metric("Paper Capital", fmt_inr(session.config.capital))
    b2.metric("Basket Net P&L", fmt_inr(session.metrics.net_pnl), f"{session.metrics.net_pnl_pct:+.2f}%")
    b3.metric("Profit Lock Status", "ACTIVE" if session.metrics.profit_lock_active else "INACTIVE", "Trigger: ₹10,000")
    b4.metric("Profit Target Status", "₹20,000", f"Distance: {fmt_inr(session.metrics.distance_to_target)}")
