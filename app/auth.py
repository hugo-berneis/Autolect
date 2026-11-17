"""Authentication: one password (from .env) -> signed session cookie.

A single dependency, `get_current_user`, protects every router and the
WebSocket. Login is rate-limited per IP.
"""
from __future__ import annotations

import hashlib
import hmac
import time
from collections import defaultdict, deque

from fastapi import Cookie, HTTPException

from .config import settings
from .models import DEFAULT_USER

COOKIE_NAME = "autolect_session"


def _signature(user: str) -> str:
    return hmac.new(
        settings.session_secret.encode(), user.encode(), hashlib.sha256
    ).hexdigest()


def make_session() -> str:
    return f"{DEFAULT_USER}.{_signature(DEFAULT_USER)}"


def verify_token(token: str | None) -> str | None:
    if not token or "." not in token:
        return None
    user, _, sig = token.rpartition(".")
    if user and hmac.compare_digest(sig, _signature(user)):
        return user
    return None


def check_password(password: str) -> bool:
    return hmac.compare_digest(password, settings.app_password)


def get_current_user(
    session: str | None = Cookie(default=None, alias=COOKIE_NAME),
) -> str:
    user = verify_token(session)
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


# --- login rate limiting (failed attempts per IP, sliding 60s window) ---
_failures: dict[str, deque[float]] = defaultdict(deque)


def too_many_failures(ip: str) -> bool:
    now = time.time()
    dq = _failures[ip]
    while dq and now - dq[0] > 60:
        dq.popleft()
    return len(dq) >= settings.login_rate_limit_per_min


def record_failure(ip: str) -> None:
    _failures[ip].append(time.time())


def clear_failures(ip: str) -> None:
    _failures.pop(ip, None)
