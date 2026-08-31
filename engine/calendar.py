"""Trading Calendar and Date Formatting Service (Asia/Kolkata).

Provides:
1. Strict date formatting: `DD-MM-YYYY, Day` (e.g., '10-09-2026, Thursday').
2. Strict timestamp formatting: `DD-MM-YYYY, Day HH:MM:SS AM/PM`.
3. NSE and BSE trading holidays (2024–2027).
4. Trading session checks, weekend checks, holiday checks.
5. Dynamic weekly and monthly expiry date resolution and Days to Expiry (DTE).
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import List, Optional, Tuple
import pytz

IST = pytz.timezone("Asia/Kolkata")

# NSE / BSE Trading Holidays (2024 - 2027)
EXCHANGE_HOLIDAYS = {
    # 2024
    date(2024, 1, 22): "Special Holiday (Ram Mandir)",
    date(2024, 1, 26): "Republic Day",
    date(2024, 3, 8): "Mahashivratri",
    date(2024, 3, 25): "Holi",
    date(2024, 3, 29): "Good Friday",
    date(2024, 4, 11): "Id-Ul-Fitr",
    date(2024, 4, 17): "Ram Navami",
    date(2024, 5, 1): "Maharashtra Day",
    date(2024, 5, 20): "General Elections",
    date(2024, 6, 17): "Bakri Id",
    date(2024, 7, 17): "Muharram",
    date(2024, 8, 15): "Independence Day",
    date(2024, 10, 2): "Mahatma Gandhi Jayanti",
    date(2024, 11, 1): "Diwali Laxmi Pujan (Muhurat)",
    date(2024, 11, 15): "Gurunanak Jayanti",
    date(2024, 11, 20): "Maharashtra Assembly Elections",
    date(2024, 12, 25): "Christmas",

    # 2025
    date(2025, 2, 26): "Mahashivratri",
    date(2025, 3, 14): "Holi",
    date(2025, 3, 31): "Id-Ul-Fitr",
    date(2025, 4, 10): "Mahavir Jayanti",
    date(2025, 4, 14): "Dr. Baba Saheb Ambedkar Jayanti",
    date(2025, 4, 18): "Good Friday",
    date(2025, 5, 1): "Maharashtra Day",
    date(2025, 6, 7): "Bakri Id",
    date(2025, 8, 15): "Independence Day",
    date(2025, 8, 27): "Ganesh Chaturthi",
    date(2025, 10, 2): "Mahatma Gandhi Jayanti",
    date(2025, 10, 21): "Diwali Laxmi Pujan",
    date(2025, 10, 22): "Diwali Balipratipada",
    date(2025, 11, 5): "Prakash Gurpurb Sri Guru Nanak Dev",
    date(2025, 12, 25): "Christmas",

    # 2026
    date(2026, 1, 26): "Republic Day",
    date(2026, 2, 16): "Mahashivratri",
    date(2026, 3, 4): "Holi",
    date(2026, 3, 20): "Id-Ul-Fitr",
    date(2026, 4, 3): "Good Friday",
    date(2026, 4, 14): "Dr. Ambedkar Jayanti",
    date(2026, 5, 1): "Maharashtra Day",
    date(2026, 5, 27): "Bakri Id",
    date(2026, 6, 25): "Muharram",
    date(2026, 8, 15): "Independence Day",
    date(2026, 9, 14): "Ganesh Chaturthi",
    date(2026, 10, 2): "Mahatma Gandhi Jayanti",
    date(2026, 10, 20): "Dussehra",
    date(2026, 11, 8): "Diwali Laxmi Pujan",
    date(2026, 11, 24): "Guru Nanak Jayanti",
    date(2026, 12, 25): "Christmas",

    # 2027
    date(2027, 1, 26): "Republic Day",
    date(2027, 3, 23): "Holi",
    date(2027, 3, 26): "Good Friday",
    date(2027, 4, 14): "Dr. Ambedkar Jayanti",
    date(2027, 5, 1): "Maharashtra Day",
    date(2027, 8, 15): "Independence Day",
    date(2027, 10, 2): "Mahatma Gandhi Jayanti",
    date(2027, 12, 25): "Christmas",
}


def get_current_ist_time() -> datetime:
    """Return current datetime in Asia/Kolkata timezone."""
    return datetime.now(IST)


def parse_date(d: date | datetime | str) -> date:
    """Parse various date inputs to standard date object."""
    if isinstance(d, datetime):
        return d.date()
    if isinstance(d, date):
        return d
    if isinstance(d, str):
        # Try multiple formats
        for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y", "%d-%b-%Y", "%Y/%m/%d"):
            try:
                return datetime.strptime(d.strip().split(",")[0].strip(), fmt).date()
            except ValueError:
                continue
    raise ValueError(f"Could not parse date: {d}")


def format_date_day(d: date | datetime | str) -> str:
    """
    Format date strictly as 'DD-MM-YYYY, Day'.
    Example: 10-09-2026 -> '10-09-2026, Thursday'.
    """
    dt = parse_date(d)
    day_name = dt.strftime("%A")
    return f"{dt.strftime('%d-%m-%Y')}, {day_name}"


def format_timestamp_day(dt: datetime | str | None = None) -> str:
    """
    Format timestamp strictly as 'DD-MM-YYYY, Day HH:MM:SS AM/PM'.
    Example: 10-09-2026 09:45:00 -> '10-09-2026, Thursday 09:45:00 AM'.
    """
    if dt is None:
        val = get_current_ist_time()
    elif isinstance(dt, str):
        try:
            val = datetime.fromisoformat(dt)
        except Exception:
            return dt
    else:
        val = dt

    if val.tzinfo is None:
        val = IST.localize(val)
    else:
        val = val.astimezone(IST)

    day_name = val.strftime("%A")
    date_str = val.strftime("%d-%m-%Y")
    time_str = val.strftime("%I:%M:%S %p")
    return f"{date_str}, {day_name} {time_str}"


def is_weekend(d: date | datetime | str) -> bool:
    """Check if date falls on Saturday (5) or Sunday (6)."""
    dt = parse_date(d)
    return dt.weekday() in (5, 6)


def is_holiday(d: date | datetime | str) -> Tuple[bool, str]:
    """Check if date is an exchange holiday."""
    dt = parse_date(d)
    if is_weekend(dt):
        return True, "Weekend (" + dt.strftime("%A") + ")"
    if dt in EXCHANGE_HOLIDAYS:
        return True, EXCHANGE_HOLIDAYS[dt]
    return False, ""


def is_trading_day(d: date | datetime | str) -> bool:
    """Check if date is an active market trading day."""
    holiday, _ = is_holiday(d)
    return not holiday


def get_next_trading_day(d: date | datetime | str) -> date:
    """Get next active trading day."""
    curr = parse_date(d) + timedelta(days=1)
    while not is_trading_day(curr):
        curr += timedelta(days=1)
    return curr


def get_previous_trading_day(d: date | datetime | str) -> date:
    """Get previous active trading day."""
    curr = parse_date(d) - timedelta(days=1)
    while not is_trading_day(curr):
        curr -= timedelta(days=1)
    return curr


def get_expiry_date(underlying: str, trading_date: date | datetime | str) -> date:
    """
    Dynamically determine the upcoming expiry date for an underlying from trading_date.
    
    Current Contract Specs:
    - NIFTY weekly expiry is typically Tuesday (or Thursday for monthly, data-driven).
    - SENSEX weekly expiry is Tuesday (BSE revised specifications) or Thursday.
    - If scheduled expiry is an exchange holiday, moves backward to previous trading day.
    """
    t_date = parse_date(trading_date)
    underlying = underlying.upper().strip()

    # Target weekday: NIFTY = Tuesday (1), SENSEX = Tuesday (1) or Thursday (3)
    # Defaulting to Tuesday (weekday 1) for both as per active 2025/2026 specs,
    # or finding the nearest future contract day.
    target_weekday = 1  # Tuesday

    days_ahead = target_weekday - t_date.weekday()
    if days_ahead < 0:  # Target day already passed this week
        days_ahead += 7

    candidate_expiry = t_date + timedelta(days=days_ahead)

    # If candidate expiry falls on an exchange holiday, adjust backward to prior trading day
    while not is_trading_day(candidate_expiry):
        candidate_expiry -= timedelta(days=1)

    # If adjusted expiry is in the past relative to trading date, find next week's
    if candidate_expiry < t_date:
        next_week = t_date + timedelta(days=days_ahead + 7)
        while not is_trading_day(next_week):
            next_week -= timedelta(days=1)
        candidate_expiry = next_week

    return candidate_expiry


def calculate_dte(trading_date: date | datetime | str, expiry_date: date | datetime | str) -> int:
    """Calculate Days to Expiry (DTE) between trading date and expiry date."""
    t_date = parse_date(trading_date)
    e_date = parse_date(expiry_date)
    return max(0, (e_date - t_date).days)


def is_within_market_hours(now: Optional[datetime] = None) -> Tuple[bool, str]:
    """Check if current time is within Indian market trading hours (09:15 to 15:30 IST)."""
    curr = now or get_current_ist_time()
    if not is_trading_day(curr.date()):
        return False, "Market Closed: Non-trading day or holiday"

    curr_time = curr.time()
    market_open = time(9, 15)
    market_close = time(15, 30)

    if curr_time < market_open:
        return False, f"Pre-market: Opens at 09:15 AM (Current: {curr_time.strftime('%I:%M %p')})"
    if curr_time > market_close:
        return False, f"Post-market: Closed at 03:30 PM (Current: {curr_time.strftime('%I:%M %p')})"

    return True, "Market Open"


def is_within_strategy_window(
    entry_time_str: str = "09:45",
    forced_exit_time_str: str = "15:00",
    now: Optional[datetime] = None,
) -> Tuple[bool, str]:
    """
    Check if current time is within strategy entry and active window.
    Strictly prohibits entry before entry_time_str (09:45 AM).
    Enforces forced exit at forced_exit_time_str (03:00 PM).
    """
    curr = now or get_current_ist_time()
    if not is_trading_day(curr.date()):
        return False, "Strategy Inactive: Non-trading day"

    curr_time = curr.time()

    eh, em = map(int, entry_time_str.split(":"))
    entry_t = time(eh, em)

    xh, xm = map(int, forced_exit_time_str.split(":"))
    exit_t = time(xh, xm)

    if curr_time < entry_t:
        return False, f"Waiting for Entry Window: 09:45 AM (Current: {curr_time.strftime('%I:%M:%S %p')})"

    if curr_time >= exit_t:
        return False, f"Forced Exit Window: Active after 03:00 PM (Current: {curr_time.strftime('%I:%M:%S %p')})"

    return True, "Strategy Active Window"
