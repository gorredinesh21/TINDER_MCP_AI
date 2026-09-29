"""Wingman AI — sessions.

The Tinder token is FULL ACCOUNT ACCESS, so it lives in server memory only:

  * never written to disk, never logged, never returned to the client
  * keyed by an opaque random session id stored in an HttpOnly cookie
  * idle TTL (default 2h); a Disconnect button drops it immediately
  * the client only ever sees a masked fingerprint (first 4 chars) so the user can
    tell which token is connected without exposing it

This module deliberately has no persistence: restart = everyone disconnected = safe.
"""
from __future__ import annotations

import hashlib
import secrets
import threading
import time
from dataclasses import dataclass, field

from .config import config


@dataclass
class Session:
    token: str | None          # None => sample-data demo session
    mode: str                  # "live" | "demo"
    created_at: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    name: str = "Guest"

    def touch(self) -> None:
        self.last_seen = time.time()

    @property
    def fingerprint(self) -> str:
        if not self.token:
            return ""
        return self.token[:4] + "…" + hashlib.sha256(self.token.encode()).hexdigest()[:6]


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        self._lock = threading.Lock()

    def create(self, token: str | None, name: str) -> str:
        sid = secrets.token_urlsafe(24)
        with self._lock:
            self._gc()
            self._sessions[sid] = Session(token=token, mode="live" if token else "demo", name=name)
        return sid

    def get(self, sid: str | None) -> Session | None:
        if not sid:
            return None
        with self._lock:
            s = self._sessions.get(sid)
            if not s:
                return None
            if time.time() - s.last_seen > config.session_ttl_seconds:
                del self._sessions[sid]
                return None
            s.touch()
            return s

    def drop(self, sid: str | None) -> None:
        if sid:
            with self._lock:
                self._sessions.pop(sid, None)

    def _gc(self) -> None:
        now = time.time()
        stale = [k for k, s in self._sessions.items() if now - s.last_seen > config.session_ttl_seconds]
        for k in stale:
            del self._sessions[k]


store = SessionStore()
