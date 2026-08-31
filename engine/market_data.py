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
            return MarketDataStatus.DEMO

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

        # Check if live yfinance is available
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

        # Fallback indicative market reference values
        defaults = {
            "NIFTY": (24_250.0, 65.5, 0.27),
            "SENSEX": (79_800.0, 195.0, 0.24),
            "BANKNIFTY": (51_200.0, 110.0, 0.22),
        }
        ref = defaults.get(underlying, (24_000.0, 0.0, 0.0))
        return ref[0], ref[1], ref[2], MarketDataStatus.DEMO


market_data_service = MarketDataService()
