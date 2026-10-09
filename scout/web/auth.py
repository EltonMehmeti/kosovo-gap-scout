"""Single-user login. The founder types DASHBOARD_TOKEN once, and an HttpOnly cookie then carries
an HMAC of it. The cookie never holds the token itself, and changing the token logs every browser
out."""

from __future__ import annotations

import hashlib
import hmac

from fastapi import Request

COOKIE = "scout_auth"
OPEN_PATHS = frozenset({"/login", "/logout", "/healthz"})
STATIC_PREFIX = "/static/"  # CSS, JS, fonts and icons: the login page needs them before login
MAX_AGE = 60 * 60 * 24 * 30  # 30 days
MIN_TOKEN_LENGTH = 16


def usable_token(settings) -> str | None:
    """The configured DASHBOARD_TOKEN, or None when it is unset or too short to trust."""
    token = settings.dashboard_token
    return token if token and len(token) >= MIN_TOKEN_LENGTH else None


def cookie_value(token: str) -> str:
    return hmac.new(token.encode(), b"scout-dashboard-v1", hashlib.sha256).hexdigest()


def token_matches(given: str, token: str) -> bool:
    return hmac.compare_digest(given.encode(), token.encode())


def is_logged_in(request: Request, token: str) -> bool:
    got = request.cookies.get(COOKIE, "")
    return hmac.compare_digest(got.encode(), cookie_value(token).encode())


def is_https(request: Request) -> bool:
    """Render terminates TLS and forwards plain HTTP with X-Forwarded-Proto: https."""
    return request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
