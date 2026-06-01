"""
Tinder connector: turns the live Tinder account into the clean Profile/Match
objects the AI brain consumes (schema.py). This is the ONLY part that touches
Tinder; swap it without changing the brain.

Backed by the vendored `rednit-team/tinder.py` library (src/vendor/tinder,
Apache-2.0) — vendored because its PyPI `setup.py` ships no importable package.

Auth = X-Auth-Token from your logged-in browser (see README "token guide").
Run it on your OWN machine / home network — cloud IPs get accounts blocked.

SENDING: the AI never sends. `send_message()` exists only for YOU to call by
hand after reviewing a draft. Reading (profile/matches/messages) is automated;
sending is not.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# vendored library is importable as top-level `tinder`
sys.path.insert(0, str(Path(__file__).resolve().parent / "vendor"))
from tinder import TinderClient  # noqa: E402

from schema import Profile, Match, Photo, ChatTurn  # noqa: E402


def _age_from_birth_date(birth_date: str | None) -> int:
    if not birth_date:
        return 0
    try:
        d = datetime.strptime(birth_date[:10], "%Y-%m-%d")
        today = datetime.now(timezone.utc)
        return today.year - d.year - ((today.month, today.day) < (d.month, d.day))
    except Exception:
        return 0


def _photos(lib_photos) -> list[Photo]:
    out: list[Photo] = []
    for p in lib_photos or ():
        out.append(Photo(id=getattr(p, "id", ""), url=getattr(p, "url", None)))
    return out


def _is_verified(lib_user) -> bool:
    return any("verif" in b.badge_type.lower() for b in getattr(lib_user, "badges", ()) or ())


def _job_str(lib_user) -> str | None:
    job = getattr(lib_user, "job", None)
    if not job:
        return None
    title = getattr(job, "title", None)
    company = getattr(job, "company", None)
    if title and company:
        return f"{title} at {company}"
    return title or company


class TinderConnector:
    def __init__(self, auth_token: str | None = None):
        token = auth_token or os.environ.get("TINDER_X_AUTH_TOKEN")
        if not token:
            raise RuntimeError(
                "No Tinder token. Set TINDER_X_AUTH_TOKEN in .env (see README token guide)."
            )
        self._client = TinderClient(token)          # raises LoginException if token is bad/expired
        self._self = self._client.get_self_user()
        self._self_id = self._self.id

    # ---------- read (automated) ----------

    def get_my_profile(self) -> Profile:
        u = self._self
        country = getattr(getattr(u, "position_info", None), "country", "") or ""
        return Profile(
            name=u.name,
            age=_age_from_birth_date(getattr(u, "birth_date", None)),
            city=country,                       # self profile exposes country, not city
            bio=getattr(u, "bio", "") or "",
            job=_job_str(u),
            prompts=[],                         # not exposed for the self user by the library
            photos=_photos(getattr(u, "photos", ())),
            intent="unsure",                    # Tinder doesn't expose this
            verified=_is_verified(u),
        )

    def list_matches(self, limit: int | None = 20, with_messages: bool = True,
                     enrich: bool = False) -> list[Match]:
        matches = self._client.load_all_matches()
        if limit:
            matches = matches[:limit]
        return [self._to_match(m, with_messages=with_messages, enrich=enrich) for m in matches]

    def get_match(self, match_id: str, with_messages: bool = True, enrich: bool = True) -> Match:
        return self._to_match(
            self._client.get_match(match_id), with_messages=with_messages, enrich=enrich
        )

    # ---------- send (manual only — you call this, never the AI) ----------

    def send_message(self, match_id: str, text: str) -> None:
        """Send a message you have personally reviewed. The AI never calls this."""
        self._client.get_match(match_id).send_message(text)

    # ---------- mapping ----------

    def _to_match(self, m, with_messages: bool, enrich: bool) -> Match:
        u = m.matched_user
        interests: list[str] = []
        if enrich:
            try:  # full profile is a separate request; best-effort
                interests = [i.name for i in getattr(u.get_user_profile(), "interests", ())]
            except Exception:
                pass

        conversation: list[ChatTurn] = []
        if with_messages:
            try:
                msgs = m.message_history.get_messages()  # recent -> past
                for msg in reversed(msgs):               # flip to chronological
                    conversation.append(ChatTurn(
                        sender="me" if msg.author_id == self._self_id else "them",
                        text=msg.content,
                        ts=getattr(msg, "sent_date", None),
                    ))
            except Exception:
                pass

        return Match(
            match_id=m.id,
            name=getattr(u, "name", None),
            age=_age_from_birth_date(getattr(u, "birth_date", None)),
            bio=getattr(u, "bio", "") or "",
            interests=interests,
            photos=_photos(getattr(u, "photos", ())),
            verified=_is_verified(u),
            conversation=conversation,
        )
