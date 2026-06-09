"""Telegram ειδοποιήσεις για auto punch bot."""

from __future__ import annotations

import os
import time

import requests

_last_error_key = ""
_last_error_at = 0.0


def _env(name: str) -> str:
    return os.environ.get(name, "").strip()


def _host() -> str:
    return _env("ERGANI_AUTO_PUNCH_HOSTNAME") or "auto-punch"


def telegram_configured() -> bool:
    return bool(_env("ERGANI_AUTO_PUNCH_TELEGRAM_BOT_TOKEN") and _env("ERGANI_AUTO_PUNCH_TELEGRAM_CHAT_ID"))


def _send(text: str) -> bool:
    token = _env("ERGANI_AUTO_PUNCH_TELEGRAM_BOT_TOKEN")
    chat_id = _env("ERGANI_AUTO_PUNCH_TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False
    try:
        res = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=15,
        )
        res.raise_for_status()
        return True
    except requests.RequestException:
        return False


def send_auto_punch_info(message: str) -> None:
    _send(f"✅ Ergani auto punch ({_host()})\n{message}")


def send_auto_punch_error(message: str, *, key: str) -> None:
    global _last_error_key, _last_error_at
    now = time.time()
    throttle = 1800
    try:
        throttle = max(300, int(_env("ERGANI_AUTO_PUNCH_ALERT_THROTTLE_SEC") or "1800"))
    except ValueError:
        pass
    if key == _last_error_key and now - _last_error_at < throttle:
        return
    if _send(f"❌ Σφάλμα — Ergani auto punch ({_host()})\n{message}"):
        _last_error_key = key
        _last_error_at = now
