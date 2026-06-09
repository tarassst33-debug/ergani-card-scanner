"""Security helpers for the Ergani UI (local / private deployment)."""

from __future__ import annotations

import os
import secrets
import time
from collections import defaultdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from flask import Flask, Request

_LOGIN_ATTEMPTS: dict[str, list[float]] = defaultdict(list)
_LOGIN_WINDOW_SEC = 300
_LOGIN_MAX_ATTEMPTS = 8


def require_ui_secret() -> str:
    secret = os.environ.get("ERGANI_UI_SECRET", "").strip()
    if len(secret) < 32:
        raise RuntimeError(
            "Ορίσε ERGANI_UI_SECRET (τουλάχιστον 32 χαρακτήρες, σταθερό) "
            "για κρυπτογράφηση και ασφαλή sessions. "
            'Παράδειγμα: openssl rand -hex 32'
        )
    return secret


def require_bootstrap_admin_password() -> tuple[str, str]:
    username = os.environ.get("ERGANI_UI_ADMIN_USER", "").strip()
    password = os.environ.get("ERGANI_UI_ADMIN_PASSWORD", "").strip()
    if not username:
        raise RuntimeError(
            "Άδεια Firestore: όρισε ERGANI_UI_ADMIN_USER και ERGANI_UI_ADMIN_PASSWORD "
            "(τουλάχιστον 12 χαρακτήρες) για τον πρώτο admin."
        )
    if len(password) < 12:
        raise RuntimeError(
            "Ο ERGANI_UI_ADMIN_PASSWORD πρέπει να έχει τουλάχιστον 12 χαρακτήρες."
        )
    return username, password


def username_allowed(username: str) -> bool:
    allowed = os.environ.get("ERGANI_UI_ALLOWED_USERS", "").strip()
    if not allowed:
        return True
    names = {n.strip().casefold() for n in allowed.split(",") if n.strip()}
    return username.strip().casefold() in names


def manual_connect_enabled() -> bool:
    return os.environ.get("ERGANI_UI_ALLOW_MANUAL_CONNECT", "").strip() in {
        "1",
        "true",
        "yes",
    }


def kiosk_web_gate_credentials() -> tuple[str, str]:
    return (
        os.environ.get("ERGANI_KIOSK_WEB_USER", "").strip(),
        os.environ.get("ERGANI_KIOSK_WEB_PASSWORD", "").strip(),
    )


def kiosk_web_gate_enabled() -> bool:
    user, password = kiosk_web_gate_credentials()
    return bool(user and password)


def verify_kiosk_web_login(username: str, password: str) -> bool:
    expected_user, expected_pass = kiosk_web_gate_credentials()
    if not expected_user or not expected_pass:
        return True
    return secrets.compare_digest(
        username.strip().casefold(), expected_user.casefold()
    ) and secrets.compare_digest(password, expected_pass)


def check_login_rate_limit(client_ip: str) -> str | None:
    now = time.monotonic()
    key = client_ip or "unknown"
    attempts = _LOGIN_ATTEMPTS[key]
    attempts[:] = [t for t in attempts if now - t < _LOGIN_WINDOW_SEC]
    if len(attempts) >= _LOGIN_MAX_ATTEMPTS:
        return "Πολλές προσπάθειες σύνδεσης. Δοκίμασε ξανά σε λίγα λεπτά."
    attempts.append(now)
    return None


def configure_app(app: Flask) -> None:
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("ERGANI_UI_HTTPS", "").strip()
        in {"1", "true", "yes"},
        PERMANENT_SESSION_LIFETIME=28800,
    )

    @app.after_request
    def _security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Cache-Control"] = "no-store"
        return response


def client_ip(request: Request) -> str:
    forwarded = (request.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
    return forwarded or (request.remote_addr or "")
