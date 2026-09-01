"""Read-only Angel One connectivity check.

Verifies the whole live-data chain without placing a single order:
session -> profile -> margins -> positions -> index spot -> option LTP.

Run from the project root:
    python scripts/angel_check.py
"""

import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

from engine import angel_broker as ab
from engine.config_service import config_service
from engine.calendar import get_current_ist_time
from engine.market_data import market_data_service
from engine.models import MarketDataStatus
from engine.strike_selector import StrikeSelector


def line(label, value):
    print(f"  {label:<26} {value}")


def main():
    print("=" * 72)
    print(f"  ANGEL ONE CONNECTIVITY CHECK   {get_current_ist_time():%d-%b-%Y %H:%M:%S IST}")
    print("=" * 72)

    # 0. credentials
    if not ab.credentials_present():
        import os
        missing = [k for k in ("ANGEL_API_KEY", "ANGEL_CLIENT_CODE",
                               "ANGEL_PIN", "ANGEL_TOTP_SECRET")
                   if not os.getenv(k, "").strip()]
        print("\n  MISSING CREDENTIALS in .env:")
        for k in missing:
            print(f"    - {k}")
        print("\n  Fill those in and re-run. Nothing else can be tested without them.")
        return 1

    line("credentials", "present")
    line("live order gate", "UNLOCKED (!)" if ab.live_trading_enabled() else "LOCKED (safe)")

    adapter = ab.AngelOneBrokerAdapter()

    # 1. session
    print("\n  -- session --")
    try:
        adapter.connect()
        line("generateSession", "OK")
    except Exception as e:
        line("generateSession", f"FAILED: {e}")
        return 1

    # 2. profile
    print("\n  -- account --")
    for label, fn in (("profile", adapter.get_account), ("margins", adapter.get_margins)):
        try:
            d = fn()
            for k, v in d.items():
                line(f"{label}.{k}", v)
        except Exception as e:
            line(label, f"FAILED: {e}")

    try:
        pos = adapter.get_positions()
        line("open positions", len(pos))
    except Exception as e:
        line("open positions", f"FAILED: {e}")

    # 3. index spot through the service (proves the whole resolution chain)
    print("\n  -- live index spot --")
    spots = {}
    for u in ("NIFTY", "SENSEX"):
        spot, chg, pct, status = market_data_service.get_index_spot_price(u)
        spots[u] = spot
        line(u, f"{spot:,.2f}  {chg:+.2f} ({pct:+.2f}%)   [{status.value}]")
    if market_data_service.get_last_error():
        line("last fallback reason", market_data_service.get_last_error())

    # 4. option quotes for the strikes the strategy would actually short
    print("\n  -- live option quotes --")
    cfg = config_service.get_config("strangle_20d")
    spot = spots.get(cfg.underlying, 0.0)
    if spot <= 0:
        line("skipped", "no spot price, cannot select strikes")
        return 1

    sel = StrikeSelector.select_strikes(
        cfg.underlying, spot, get_current_ist_time().strftime("%d-%m-%Y"), cfg
    )
    line("expiry / DTE", f"{sel.expiry}  DTE={sel.dte}")

    legs = [("CE main", sel.ce_main_strike, "CE"), ("PE main", sel.pe_main_strike, "PE"),
            ("CE hedge", sel.ce_hedge_strike, "CE"), ("PE hedge", sel.pe_hedge_strike, "PE")]
    quoted = 0
    for label, strike, opt in legs:
        if strike is None:
            line(label, "not configured")
            continue
        ltp, status = market_data_service.get_option_ltp(cfg.underlying, sel.expiry, strike, opt)
        if status == MarketDataStatus.LIVE:
            quoted += 1
            line(label, f"{strike:,.0f}{opt}  LTP {ltp:,.2f}")
        else:
            line(label, f"{strike:,.0f}{opt}  UNAVAILABLE - {market_data_service.get_last_error()}")

    print("\n" + "=" * 72)
    print(f"  {quoted}/4 legs quoted. Live paper entry needs all four.")
    print("=" * 72)
    return 0 if quoted == 4 else 1


if __name__ == "__main__":
    sys.exit(main())
