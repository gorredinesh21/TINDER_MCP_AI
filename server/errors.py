"""Wingman AI — friendly errors.

Ordinary users never see `AxiosError: 401 Unauthorized`. Every failure the product can
hit is mapped to a stable machine code + a plain-language message the UI can render.
Technical details go to the server console only (token-scrubbed), never to the client.
"""
from __future__ import annotations

import logging
import re

from fastapi import HTTPException

log = logging.getLogger("wingman")


class AppError(HTTPException):
    """An error with a friendly, user-facing message."""

    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(status_code=status, detail={"code": code, "message": message})


def scrub(text: str, token: str | None) -> str:
    """Remove any accidental token leak from logs/errors before printing or returning."""
    if not token:
        return text
    return text.replace(token, "<redacted-token>")


# how each raw failure is explained to a normal user
_FRIENDLY = {
    "invalid_token": "That Tinder token wasn't accepted. Please copy it again from tinder.com — the guide shows exactly where it lives.",
    "expired_token": "Your Tinder connection has expired. Tokens stop working after a while (or when you log out) — just paste a fresh one.",
    "token_format": "That doesn't look like a Tinder token. It's 36 characters, like `bff5d171-....-...-...`. The guide shows how to copy the whole value.",
    "no_session": "You're not connected yet. Paste your Tinder token on the Connect screen, or try the demo.",
    "not_connected": "You're not connected yet. Paste your Tinder token on the Connect screen, or try the demo.",
    "cloud_live_blocked": "This is the public demo instance, so live Tinder connections are disabled here. Run Wingman AI on your own machine to connect your account (it takes 2 minutes and keeps your token under your control).",
    "tinder_unreachable": "Tinder isn't responding right now. Check your internet connection and try again in a moment.",
    "rate_limited": "Tinder is asking us to slow down. Wait a minute before trying again.",
    "account_locked": "Tinder has your account in a verification/review state, so this data isn't available right now. Complete any verification Tinder asks for (usually in the mobile app), then reconnect.",
    "not_found": "We couldn't find that on Tinder anymore — refresh and try again.",
    "ai_unavailable": "The AI service is busy for a moment. Please try again.",
    "ai_bad_output": "The AI returned something we couldn't use. Please try again.",
    "live_required": "This feature needs a live Tinder connection (the demo uses sample data).",
    "confirm_required": "For safety, this action only runs when you explicitly confirm it in the app.",
    "demo_action": "This is the demo with sample data, so this action is disabled here. Connect your own account to use it.",
}


def invalid_token() -> AppError:
    return AppError("invalid_token", _FRIENDLY["invalid_token"], 401)


def expired_token() -> AppError:
    return AppError("expired_token", _FRIENDLY["expired_token"], 401)


def no_session() -> AppError:
    return AppError("no_session", _FRIENDLY["no_session"], 401)


def from_exception(exc: Exception, token: str | None = None, where: str = "") -> AppError:
    """Map any low-level failure to a friendly AppError; log the technical cause scrubbed."""
    name = type(exc).__name__
    msg = str(exc)
    safe = scrub(f"{where}: {name}: {msg}", token)
    log.warning("[error] %s", safe[:400])

    text = f"{name} {msg}".lower()
    if "401" in text or "unauthorized" in text:
        return expired_token()
    if "403" in text or "forbidden" in text:
        return AppError("account_locked", _FRIENDLY["account_locked"], 403)
    if "404" in text or "notfound" in text:
        return AppError("not_found", _FRIENDLY["not_found"], 404)
    if "429" in text or "rate" in text or "too many" in text:
        return AppError("rate_limited", _FRIENDLY["rate_limited"], 429)
    if any(k in text for k in ("connection", "timeout", "dns", "network", "ssl", "refused")):
        return AppError("tinder_unreachable", _FRIENDLY["tinder_unreachable"], 502)
    if "selfie" in text or "verification" in text or "review" in text:
        return AppError("account_locked", _FRIENDLY["account_locked"], 403)
    return AppError("tinder_unreachable", _FRIENDLY["tinder_unreachable"], 502)


def looks_like_token(value: str) -> bool:
    """Tinder X-Auth-Token is a 36-char UUID. Loose sanity check only."""
    v = value.strip()
    return bool(re.fullmatch(r"[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", v))
