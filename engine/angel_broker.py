"""Angel One (SmartAPI) broker adapter for live execution.

Architecture note: this sits behind the same BrokerAdapter interface as
PaperBrokerAdapter, so the strategy engine does not know which broker it is
talking to.

SAFETY: live order transmission is OFF unless ANGEL_LIVE_TRADING=true is set
in the environment. Without it every place_order() is rejected before any
network call is made. This mirrors the "Live Execution Gate: LOCKED" rule the
deployment dashboard already advertises - flipping it is a deliberate act.

Required .env:
    ANGEL_API_KEY, ANGEL_CLIENT_CODE, ANGEL_PIN, ANGEL_TOTP_SECRET
Optional:
    ANGEL_LIVE_TRADING=true     enable real order placement
    ANGEL_PRODUCT_TYPE          INTRADAY (default) or CARRYFORWARD
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from engine.broker_adapter import BrokerAdapter
from engine.models import Order, OrderStatus

log = logging.getLogger(__name__)

SCRIP_MASTER_URL = (
    "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
)
# ~20MB; refetched only when older than a day. Kept out of the repo.
SCRIP_CACHE = Path(".cache/angel_scrip_master.json")
SCRIP_MAX_AGE_SECONDS = 24 * 3600

# NIFTY/BANKNIFTY options list on NFO, SENSEX/BANKEX on BFO.
EXCHANGE_FOR = {
    "NIFTY": "NFO", "BANKNIFTY": "NFO", "FINNIFTY": "NFO",
    "SENSEX": "BFO", "BANKEX": "BFO",
}


def credentials_present() -> bool:
    """True when enough .env vars exist to attempt an Angel One login."""
    return all(os.getenv(k, "").strip() for k in (
        "ANGEL_API_KEY", "ANGEL_CLIENT_CODE", "ANGEL_PIN", "ANGEL_TOTP_SECRET",
    ))


def live_trading_enabled() -> bool:
    """Real orders are transmitted only when this is explicitly turned on."""
    return os.getenv("ANGEL_LIVE_TRADING", "").strip().lower() in ("1", "true", "yes")


# -- Scrip master (contract -> token resolution) -------------------------------

_SCRIP_CACHE_MEM: Optional[List[Dict[str, Any]]] = None


def load_scrip_master(force: bool = False) -> List[Dict[str, Any]]:
    """Fetch and cache Angel's instrument dump. Needed to map a contract to its token."""
    global _SCRIP_CACHE_MEM
    if _SCRIP_CACHE_MEM is not None and not force:
        return _SCRIP_CACHE_MEM

    fresh = (
        SCRIP_CACHE.exists()
        and (time.time() - SCRIP_CACHE.stat().st_mtime) < SCRIP_MAX_AGE_SECONDS
    )
    if fresh and not force:
        _SCRIP_CACHE_MEM = json.loads(SCRIP_CACHE.read_text(encoding="utf-8"))
        return _SCRIP_CACHE_MEM

    log.info("Downloading Angel One scrip master (~20MB)...")
    resp = requests.get(SCRIP_MASTER_URL, timeout=120)
    resp.raise_for_status()
    data = resp.json()

    SCRIP_CACHE.parent.mkdir(parents=True, exist_ok=True)
    SCRIP_CACHE.write_text(json.dumps(data), encoding="utf-8")
    _SCRIP_CACHE_MEM = data
    return data


def resolve_option_token(
    underlying: str, expiry: str, strike: float, option_type: str
) -> Optional[Dict[str, Any]]:
    """
    Find the Angel instrument for one option contract.

    `expiry` must match Angel's format, e.g. "04SEP2025".
    Returns the raw scrip dict (token, symbol, lotsize, ...) or None.
    """
    underlying = underlying.upper().strip()
    option_type = option_type.upper().strip()
    exch = EXCHANGE_FOR.get(underlying, "NFO")

    # ponytail: Angel publishes OPTIDX strikes in paise (x100). Both readings are
    # accepted so a format change on their side degrades to a miss, not a wrong fill.
    wanted = {round(strike * 100, 2), round(float(strike), 2)}

    for s in load_scrip_master():
        if s.get("exch_seg") != exch or s.get("instrumenttype") != "OPTIDX":
            continue
        if s.get("name", "").upper() != underlying:
            continue
        if s.get("expiry", "").upper() != expiry.upper():
            continue
        try:
            if round(float(s.get("strike", -1)), 2) not in wanted:
                continue
        except (TypeError, ValueError):
            continue
        if not s.get("symbol", "").upper().endswith(option_type):
            continue
        return s
    return None


# -- Adapter -------------------------------------------------------------------

class AngelOneBrokerAdapter(BrokerAdapter):
    """Live Angel One execution. Orders are gated behind ANGEL_LIVE_TRADING."""

    def __init__(self, initial_capital: float = 1_000_000.0):
        self.capital = initial_capital
        self.is_connected = False
        self._smart = None
        self._feed_token = None
        self._refresh_token = None
        self.orders: Dict[str, Order] = {}

    # -- connection ------------------------------------------------------------

    def connect(self) -> bool:
        if not credentials_present():
            raise ValueError(
                "Missing .env vars: ANGEL_API_KEY, ANGEL_CLIENT_CODE, "
                "ANGEL_PIN, ANGEL_TOTP_SECRET"
            )
        try:
            from SmartApi import SmartConnect
        except ImportError as e:
            raise RuntimeError("Run: pip install smartapi-python") from e
        import pyotp

        api_key = os.getenv("ANGEL_API_KEY", "").strip()
        client = os.getenv("ANGEL_CLIENT_CODE", "").strip()
        pin = os.getenv("ANGEL_PIN", "").strip()
        totp = pyotp.TOTP(os.getenv("ANGEL_TOTP_SECRET", "").strip()).now()

        self._smart = SmartConnect(api_key=api_key)
        data = self._smart.generateSession(client, pin, totp)

        if not data.get("status"):
            raise ValueError(f"Angel One login failed: {data.get('message', data)}")

        self._refresh_token = data["data"]["refreshToken"]
        self._feed_token = self._smart.getfeedToken()
        self.is_connected = True
        log.info("Angel One session established for %s", client)
        return True

    def disconnect(self) -> bool:
        try:
            if self._smart:
                self._smart.terminateSession(os.getenv("ANGEL_CLIENT_CODE", "").strip())
        except Exception as e:
            log.warning("Angel logout failed: %s", e)
        self.is_connected = False
        return True

    def _require_session(self):
        if not self.is_connected:
            self.connect()

    # -- account ---------------------------------------------------------------

    def get_account(self) -> Dict[str, Any]:
        self._require_session()
        prof = self._smart.getProfile(self._refresh_token)
        d = prof.get("data", {}) if isinstance(prof, dict) else {}
        return {
            "broker": "Angel One (SmartAPI)",
            "account_id": d.get("clientcode", os.getenv("ANGEL_CLIENT_CODE", "")),
            "name": d.get("name", ""),
            "status": "LIVE" if live_trading_enabled() else "CONNECTED_ORDERS_LOCKED",
            "exchanges": d.get("exchanges", []),
        }

    def get_margins(self) -> Dict[str, float]:
        self._require_session()
        rms = self._smart.rmsLimit()
        d = rms.get("data", {}) if isinstance(rms, dict) else {}

        def _f(key: str) -> float:
            try:
                return float(d.get(key) or 0.0)
            except (TypeError, ValueError):
                return 0.0

        available = _f("availablecash")
        used = _f("utiliseddebits")
        return {
            "total_capital": available + used,
            "available_margin": available,
            "used_margin": used,
            "net": _f("net"),
        }

    def get_positions(self) -> List[Dict[str, Any]]:
        self._require_session()
        pos = self._smart.position()
        return (pos.get("data") or []) if isinstance(pos, dict) else []

    # -- quotes ----------------------------------------------------------------

    def get_ltp(self, underlying: str, expiry: str, strike: float, option_type: str) -> float:
        """Live LTP for one option contract. 0.0 when it cannot be resolved."""
        self._require_session()
        scrip = resolve_option_token(underlying, expiry, strike, option_type)
        if not scrip:
            return 0.0
        r = self._smart.ltpData(scrip["exch_seg"], scrip["symbol"], scrip["token"])
        try:
            return float(r["data"]["ltp"])
        except (KeyError, TypeError, ValueError):
            return 0.0

    # -- orders ----------------------------------------------------------------

    def place_order(self, order: Order) -> Order:
        """Transmit a real order. Refuses unless ANGEL_LIVE_TRADING is enabled."""
        if not live_trading_enabled():
            order.status = OrderStatus.REJECTED
            order.reason = (
                "LIVE EXECUTION GATE LOCKED - set ANGEL_LIVE_TRADING=true to transmit "
                "real orders. No request was sent to the broker."
            )
            self.orders[order.order_id] = order
            log.warning("Blocked live order %s: gate locked", order.order_id)
            return order

        self._require_session()

        opt = getattr(order.option_type, "value", str(order.option_type))
        scrip = resolve_option_token(order.underlying, order.expiry, order.strike, opt)
        if not scrip:
            order.status = OrderStatus.REJECTED
            order.reason = (
                f"Contract not found in Angel scrip master: "
                f"{order.underlying} {order.expiry} {order.strike} {opt}"
            )
            self.orders[order.order_id] = order
            return order

        txn = getattr(order.transaction_type, "value", str(order.transaction_type))
        params = {
            "variety": "NORMAL",
            "tradingsymbol": scrip["symbol"],
            "symboltoken": str(scrip["token"]),
            "transactiontype": txn,
            "exchange": scrip["exch_seg"],
            "ordertype": "LIMIT" if order.requested_price > 0 else "MARKET",
            "producttype": os.getenv("ANGEL_PRODUCT_TYPE", "INTRADAY").strip() or "INTRADAY",
            "duration": "DAY",
            "price": str(order.requested_price or 0),
            "squareoff": "0",
            "stoploss": "0",
            "quantity": str(order.quantity),
        }

        log.info("Angel order -> %s", params)
        try:
            resp = self._smart.placeOrder(params)
        except Exception as e:
            order.status = OrderStatus.FAILED
            order.reason = f"Angel placeOrder failed: {e}"
            self.orders[order.order_id] = order
            return order

        # placeOrder returns the broker order id (string) on success.
        broker_order_id = resp.get("data", {}).get("orderid") if isinstance(resp, dict) else resp
        if not broker_order_id:
            order.status = OrderStatus.REJECTED
            order.reason = f"Angel rejected order: {resp}"
        else:
            order.broker_order_id = str(broker_order_id)
            order.status = OrderStatus.SUBMITTED
            order.reason = ""

        self.orders[order.order_id] = order
        return order

    def cancel_order(self, order_id: str) -> bool:
        self._require_session()
        local = self.orders.get(order_id)
        broker_id = getattr(local, "broker_order_id", None) or order_id
        try:
            resp = self._smart.cancelOrder(broker_id, "NORMAL")
        except Exception as e:
            log.error("Angel cancel failed for %s: %s", broker_id, e)
            return False
        ok = bool(resp.get("status")) if isinstance(resp, dict) else False
        if ok and local:
            local.status = OrderStatus.CANCELLED
        return ok

    def get_order_status(self, order_id: str) -> OrderStatus:
        self._require_session()
        local = self.orders.get(order_id)
        broker_id = getattr(local, "broker_order_id", None) or order_id
        try:
            book = self._smart.orderBook()
        except Exception as e:
            log.error("Angel orderBook failed: %s", e)
            return OrderStatus.FAILED

        rows = (book.get("data") or []) if isinstance(book, dict) else []
        for row in rows:
            if str(row.get("orderid")) != str(broker_id):
                continue
            return {
                "complete":        OrderStatus.FILLED,
                "rejected":        OrderStatus.REJECTED,
                "cancelled":       OrderStatus.CANCELLED,
                "open":            OrderStatus.SUBMITTED,
                "trigger pending": OrderStatus.PENDING,
            }.get(str(row.get("status", "")).lower(), OrderStatus.SUBMITTED)

        return OrderStatus.FAILED
