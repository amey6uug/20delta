"""Market Data Validation and Quote Provider Service.

Handles:
- Quote validation (symbol, expiry, strike, option type, LTP, bid, ask).
- Freshness tracking and status tagging (LIVE, STALE, UNAVAILABLE, DEMO).
- Live and historical option price resolution.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import pandas as pd

from engine.calendar import format_timestamp_day, get_current_ist_time
from engine.models import MarketDataStatus, MarketQuote, OptionType


class MarketDataService:
    def __init__(self, stale_threshold_seconds: int = 60):
        self.stale_threshold_seconds = stale_threshold_seconds
        self._cached_quotes: Dict[str, MarketQuote] = {}
        self._last_error: str = ""
        self._angel = None

    def validate_quote(self, quote: MarketQuote) -> Tuple[bool, str]:
        """Validate option quote structure and positive price."""
        if quote.ltp <= 0 and quote.bid <= 0 and quote.ask <= 0:
            return False, "Quote has non-positive prices (LTP <= 0)."
        if not quote.symbol or not quote.underlying:
            return False, "Missing symbol or underlying."
        return True, ""

    def evaluate_freshness(self, timestamp_str: str) -> MarketDataStatus:
        """Determine if a quote timestamp is LIVE, STALE, or UNAVAILABLE."""
        if not timestamp_str:
            return MarketDataStatus.UNAVAILABLE

        try:
            # Try ISO format
            q_time = datetime.fromisoformat(timestamp_str)
        except Exception:
            # An unreadable timestamp means unknown freshness, not demo data.
            return MarketDataStatus.UNAVAILABLE

        now = get_current_ist_time()
        if q_time.tzinfo is None:
            from engine.calendar import IST
            q_time = IST.localize(q_time)

        diff = (now - q_time).total_seconds()
        if diff <= self.stale_threshold_seconds:
            return MarketDataStatus.LIVE
        elif diff <= 3600:
            return MarketDataStatus.STALE
        return MarketDataStatus.UNAVAILABLE

    def get_index_spot_price(self, underlying: str) -> Tuple[float, float, float, MarketDataStatus]:
        """
        Get current spot price, change, change % and status for NIFTY or SENSEX.
        Returns (current_price, change, change_pct, status).
        """
        underlying = underlying.upper().strip()

        # 1. Angel One - the configured execution broker, so its quotes are the
        #    ones the strategy would actually trade against.
        try:
            from engine import angel_broker as ab
            if ab.credentials_present():
                ltp, chg, pct = self._angel_adapter().get_index_spot(underlying)
                if ltp > 0:
                    return ltp, chg, pct, MarketDataStatus.LIVE
        except Exception as e:
            self._last_error = f"Angel spot failed for {underlying}: {e}"

        # 2. Live broker quote (Flattrade NorenAPI) - only source that is truly real-time.
        try:
            import flattrade_fetch as ft
            if ft.credentials_present():
                ltp, chg, pct = ft.get_index_spot(underlying)
                if ltp > 0:
                    return ltp, chg, pct, MarketDataStatus.LIVE
        except Exception as e:
            self._last_error = f"Flattrade spot failed for {underlying}: {e}"

        # 3. Check if live yfinance is available
        try:
            import yfinance as yf
            ticker_map = {"NIFTY": "^NSEI", "SENSEX": "^BSESN", "BANKNIFTY": "^NSEBANK"}
            symbol = ticker_map.get(underlying)
            if symbol:
                t = yf.Ticker(symbol)
                hist = t.history(period="2d")
                if not hist.empty:
                    curr = float(hist["Close"].iloc[-1])
                    prev = float(hist["Close"].iloc[-2]) if len(hist) > 1 else curr
                    chg = curr - prev
                    pct = (chg / prev * 100.0) if prev else 0.0
                    return round(curr, 2), round(chg, 2), round(pct, 2), MarketDataStatus.LIVE
        except Exception:
            pass

        # 4. No live source reachable. Report that honestly rather than inventing
        #    a plausible-looking price the UI would render as if it were real.
        if not self._last_error:
            self._last_error = f"No live market data source available for {underlying}"
        return 0.0, 0.0, 0.0, MarketDataStatus.UNAVAILABLE

    def get_option_quote(self, tsym: str, exch: str = "NFO") -> Tuple[Optional[MarketQuote], MarketDataStatus]:
        """
        Live option quote by trading symbol. Returns (quote, status).
        Returns (None, UNAVAILABLE) when the broker is not configured or the
        contract cannot be resolved - callers must handle that, since there is
        no meaningful synthetic price for a specific option contract.
        """
        try:
            import flattrade_fetch as ft
            if not ft.credentials_present():
                self._last_error = "Flattrade credentials not configured (.env)"
                return None, MarketDataStatus.UNAVAILABLE
            q = ft.get_option_quote(tsym, exch=exch)
        except Exception as e:
            self._last_error = f"Option quote failed for {tsym}: {e}"
            return None, MarketDataStatus.UNAVAILABLE

        if q["ltp"] <= 0:
            return None, MarketDataStatus.UNAVAILABLE

        # flattrade_fetch already knows how to parse NFO/BFO symbols - reuse it
        parsed = ft._parse_symbol(q["tsym"]) or ft._parse_symbol(tsym)
        underlying, expiry, strike, opt = parsed if parsed else (tsym, "", 0, "CE")

        quote = MarketQuote(
            symbol=q["tsym"],
            underlying=underlying,
            expiry=expiry,
            strike=float(strike),
            option_type=OptionType.CE if opt == "CE" else OptionType.PE,
            ltp=q["ltp"],
            bid=q["bid"],
            ask=q["ask"],
            volume=int(q["volume"]),
            timestamp=get_current_ist_time().isoformat(),
            status=MarketDataStatus.LIVE,
        )
        self._cached_quotes[q["tsym"]] = quote
        return quote, MarketDataStatus.LIVE


    def get_option_ltp(
        self, underlying: str, expiry: str, strike: float, option_type: str
    ) -> Tuple[float, MarketDataStatus]:
        """
        Live LTP for one option contract, addressed by its components rather than
        a broker-specific trading symbol.

        `expiry` accepts an ISO date (2026-09-01) or Angel's own 01SEP2026 form.
        Returns (0.0, UNAVAILABLE) when no broker is configured - there is no
        sensible synthetic price for a specific contract, so callers must refuse
        to trade rather than guess.
        """
        try:
            from engine import angel_broker as ab
        except Exception as e:
            self._last_error = f"Angel adapter unavailable: {e}"
            return 0.0, MarketDataStatus.UNAVAILABLE

        if not ab.credentials_present():
            self._last_error = "Angel One credentials not configured (.env)"
            return 0.0, MarketDataStatus.UNAVAILABLE

        # Normalise ISO dates to Angel's DDMMMYYYY.
        exp = str(expiry).strip()
        if "-" in exp:
            try:
                exp = datetime.strptime(exp[:10], "%Y-%m-%d").strftime("%d%b%Y").upper()
            except ValueError:
                self._last_error = f"Unparseable expiry: {expiry}"
                return 0.0, MarketDataStatus.UNAVAILABLE

        try:
            adapter = self._angel_adapter()
            ltp = adapter.get_ltp(underlying, exp, float(strike), option_type)
        except Exception as e:
            self._last_error = f"Angel LTP failed for {underlying} {exp} {strike}{option_type}: {e}"
            return 0.0, MarketDataStatus.UNAVAILABLE

        if ltp <= 0:
            self._last_error = f"No quote for {underlying} {exp} {strike}{option_type}"
            return 0.0, MarketDataStatus.UNAVAILABLE
        return ltp, MarketDataStatus.LIVE

    def _angel_adapter(self):
        """One Angel session per process - logging in per quote would burn TOTP codes."""
        if getattr(self, "_angel", None) is None:
            from engine.angel_broker import AngelOneBrokerAdapter
            self._angel = AngelOneBrokerAdapter()
        return self._angel

    def get_last_error(self) -> str:
        """Reason the most recent live fetch fell back, for display in the UI."""
        return getattr(self, "_last_error", "")


market_data_service = MarketDataService()
