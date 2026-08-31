"""Alert routing tests — no network, requests is stubbed out."""

import pytest

from engine import alerts

TG = {"TELEGRAM_BOT_TOKEN": "tok", "TELEGRAM_CHAT_ID": "42"}
WA = {"TWILIO_ACCOUNT_SID": "AC1", "TWILIO_AUTH_TOKEN": "sec", "WHATSAPP_TO": "+919876543210"}
ALL_KEYS = list(TG) + list(WA) + ["TWILIO_WHATSAPP_FROM"]


@pytest.fixture
def env(monkeypatch):
    """Start from a clean slate so a developer's real .env can't leak in."""
    for key in ALL_KEYS:
        monkeypatch.delenv(key, raising=False)
    return monkeypatch


@pytest.fixture
def posts(monkeypatch):
    calls = []

    class Resp:
        def raise_for_status(self):
            pass

    def fake_post(url, **kw):
        calls.append((url, kw))
        return Resp()

    monkeypatch.setattr(alerts.requests, "post", fake_post)
    return calls


def test_no_credentials_is_a_noop(env, posts):
    assert alerts.configured_channels() == []
    assert alerts.send_sync("hello") == ([], [])
    alerts.send("hello")
    assert posts == []


def test_both_channels_send(env, posts):
    for k, v in {**TG, **WA}.items():
        env.setenv(k, v)
    delivered, errors = alerts.send_sync("hello")
    assert delivered == ["telegram", "whatsapp"] and errors == []
    assert "api.telegram.org/bottok/sendMessage" in posts[0][0]
    assert posts[0][1]["json"] == {"chat_id": "42", "text": "hello"}
    assert posts[1][0].endswith("/Accounts/AC1/Messages.json")
    # bare numbers get the whatsapp: scheme Twilio requires
    assert posts[1][1]["data"]["To"] == "whatsapp:+919876543210"
    assert posts[1][1]["data"]["Body"] == "hello"


def test_one_channel_failing_does_not_block_the_other(env, posts, monkeypatch):
    for k, v in {**TG, **WA}.items():
        env.setenv(k, v)

    def boom(text):
        raise RuntimeError("telegram down")

    monkeypatch.setattr(alerts, "CHANNELS", (boom, alerts._whatsapp))
    delivered, errors = alerts.send_sync("hello")
    assert delivered == ["whatsapp"]
    assert "telegram down" in errors[0]


def test_only_interesting_states_alert(env, posts):
    for k, v in TG.items():
        env.setenv(k, v)

    alerts.alert_state("S", "RUN1", "IDLE", "WAITING_FOR_ENTRY", "noise", 0.0)
    assert posts == []                                    # plumbing stays quiet
    alerts.alert_state("S", "RUN1", "ACTIVE", "ACTIVE", "same", 0.0)
    assert posts == []                                    # no self-transition spam

    alerts.alert_state("S", "RUN1", "ENTERING", "ACTIVE", "legs entered", 12345.0)
    body = _wait_for_one(posts)["json"]["text"]
    assert "🟢 S — ACTIVE" in body and "legs entered" in body and "₹12,345" in body


def _wait_for_one(posts, timeout=3.0):
    """send() dispatches on a daemon thread — give it a moment to land."""
    import time
    deadline = time.time() + timeout
    while time.time() < deadline:
        if posts:
            return posts[0][1]
        time.sleep(0.01)
    raise AssertionError("no alert was sent")
