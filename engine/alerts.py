"""Trade alerts over Telegram and WhatsApp.

Both channels are opt-in through .env. With no credentials set every call is a
no-op, so backtests and the test suite stay silent. Delivery runs on a daemon
thread and never raises — a messaging outage must never stall or abort a live
trading session.

Telegram : bot token from @BotFather + your chat id from @userinfobot.
WhatsApp : Twilio (its sandbox works without Meta business verification).
"""

from __future__ import annotations

import os
import threading
from typing import List, Optional, Tuple

import requests
from dotenv import load_dotenv

from engine.calendar import format_timestamp_day

load_dotenv()

TIMEOUT = 8

# State transitions worth a phone buzz — the rest is internal plumbing.
ALERT_STATES = {
    "ACTIVE": "🟢",
    "PROFIT_LOCK_ACTIVE": "🔒",
    "STOP_LOSS_TRIGGERED": "🛑",
    "HARD_STOP_TRIGGERED": "⛔",
    "HEDGE_FAILURE": "🚨",
    "TARGET_REACHED": "🎯",
    "FORCED_EXIT": "⏰",
    "COMPLETED": "🏁",
    "ERROR": "❌",
}


def _telegram(text: str) -> Optional[str]:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not (token and chat_id):
        return None
    resp = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    return "telegram"


def _whatsapp(text: str) -> Optional[str]:
    sid = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
    token = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
    to = os.getenv("WHATSAPP_TO", "").strip()
    if not (sid and token and to):
        return None
    if not to.startswith("whatsapp:"):
        to = f"whatsapp:{to}"
    frm = os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886").strip()
    if not frm.startswith("whatsapp:"):
        frm = f"whatsapp:{frm}"
    resp = requests.post(
        f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
        auth=(sid, token),
        data={"From": frm, "To": to, "Body": text},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    return "whatsapp"


CHANNELS = (_telegram, _whatsapp)


def configured_channels() -> List[str]:
    """Names of the channels that have complete credentials."""
    names = []
    if os.getenv("TELEGRAM_BOT_TOKEN", "").strip() and os.getenv("TELEGRAM_CHAT_ID", "").strip():
        names.append("telegram")
    if (
        os.getenv("TWILIO_ACCOUNT_SID", "").strip()
        and os.getenv("TWILIO_AUTH_TOKEN", "").strip()
        and os.getenv("WHATSAPP_TO", "").strip()
    ):
        names.append("whatsapp")
    return names


def send_sync(text: str) -> Tuple[List[str], List[str]]:
    """Send on every configured channel. Returns (delivered, errors)."""
    delivered: List[str] = []
    errors: List[str] = []
    for channel in CHANNELS:
        try:
            name = channel(text)
            if name:
                delivered.append(name)
        except Exception as e:  # network/auth failure must not propagate
            errors.append(f"{channel.__name__.lstrip('_')}: {e}")
    return delivered, errors


def send(text: str) -> None:
    """Fire-and-forget send — returns immediately, never raises."""
    if not configured_channels():
        return
    threading.Thread(target=send_sync, args=(text,), daemon=True).start()


def alert_state(
    strategy_name: str,
    run_id: str,
    old_state: str,
    new_state: str,
    reason: str,
    net_pnl: float = 0.0,
) -> None:
    """Push a state-transition alert if this state is one worth waking up for."""
    icon = ALERT_STATES.get(new_state)
    if not icon or new_state == old_state:
        return
    send(
        f"{icon} {strategy_name} — {new_state}\n"
        f"{reason}\n"
        f"P&L: ₹{net_pnl:,.0f}\n"
        f"{format_timestamp_day()}  |  {run_id}"
    )
