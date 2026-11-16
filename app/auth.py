"""Authentication boundary.

Single user for now. Phase (e) will enforce the .env password via a session
cookie here (and rate-limit login), without changing call sites: every router
depends on `get_current_user`, so adding real auth is localized to this module.
"""
from __future__ import annotations

from .models import DEFAULT_USER


def get_current_user() -> str:
    # Phase (e): validate the session cookie set by password login and return
    # the authenticated user id. Until then, single-user default.
    return DEFAULT_USER
