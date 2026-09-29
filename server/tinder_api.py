"""Wingman AI — the ONLY module that talks to Tinder.

Design rules:
  * every write action (bio, prompts, message) requires confirm=True — the AI layer
    can never trigger a write on its own; only an explicit user action in the UI can
  * swiping is implemented but NOT routed: it stays disabled until live-verified
    (see docs/research-findings.md). Research-first, no blind automation.
  * the token is passed in per call and never stored on this object beyond the call
"""
from __future__ import annotations

import logging
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

import requests

from .schemas import ChatTurn, Match, Photo, Profile

# vendored `tinder` library (Apache-2.0, rednit-team/tinder.py)
sys.path.insert(0, str(Path(__file__).resolve().parent / "vendor"))
from tinder import TinderClient          # noqa: E402

log = logging.getLogger("wingman.tinder")

BASE = "https://api.gotinder.com"
MOBILE_UA = "Tinder/14.21.0 (iPhone; iOS 16.6.1; Scale/3.00)"

# one Tinder call at a time per process — politeness by construction
_call_lock = threading.Lock()


def _age(birth_date: str | None) -> int:
    if not birth_date:
        return 0
    try:
        d = datetime.strptime(birth_date[:10], "%Y-%m-%d")
        today = datetime.now(timezone.utc)
        return today.year - d.year - ((today.month, today.day) < (d.month, d.day))
    except Exception:
        return 0


def _photos(lib_photos) -> list[Photo]:
    return [Photo(id=getattr(p, "id", "") or str(i), url=getattr(p, "url", None))
            for i, p in enumerate(lib_photos or ())]


def _headers(token: str) -> dict:
    return {
        "X-Auth-Token": token,
        "User-Agent": MOBILE_UA,
        "platform": "ios",
        "Content-Type": "application/json",
    }


class TinderAPI:
    """Reads + gated writes against the authenticated user's own account."""

    def __init__(self, token: str):
        self._token = token
        self._self_id: str | None = None

    @property
    def self_id(self) -> str:
        """The authenticated user's own Tinder id (cached; one extra call per session)."""
        if self._self_id is None:
            with _call_lock:
                res = requests.get(f"{BASE}/profile", headers=_headers(self._token), timeout=20)
            if res.status_code == 401:
                raise PermissionError("401 unauthorized")
            res.raise_for_status()
            self._self_id = res.json().get("_id", "")
        return self._self_id

    # ---------------- reads ----------------

    def verify(self) -> Profile:
        """Cheap connectivity check: fetch the profile or raise."""
        return self.get_profile()

    def get_profile(self) -> Profile:
        with _call_lock:
            res = requests.get(
                f"{BASE}/v2/profile?include=account,user",
                headers=_headers(self._token), timeout=20)
        if res.status_code == 401:
            raise PermissionError("401 unauthorized")
        res.raise_for_status()
        user = res.json().get("data", {}).get("user", {})
        return self._profile_from_v2(user)

    def _profile_from_v2(self, user: dict) -> Profile:
        interests = [i.get("name", "") for i in user.get("user_interests", {}).get("selected_interests", [])]
        prompts = [{
            "q": p.get("question_text", ""),
            "a": p.get("answer_text", ""),
            "id": p.get("id", ""),
            "question_id": p.get("question_id", ""),
        } for p in user.get("user_prompts", {}).get("prompts", [])]

        descriptors: list[dict[str, str]] = []
        intent = "unsure"
        for d in user.get("selected_descriptors", []):
            name = d.get("name") or d.get("id", "")
            if d.get("id") == "de_37":
                name = "Languages"
            choices = [c.get("name", "") for c in d.get("choice_selections", [])]
            if choices:
                descriptors.append({"name": name, "value": ", ".join(choices)})
            if d.get("id") == "de_29" and choices:            # "Looking for"
                goal = choices[0].lower()
                if "long" in goal:
                    intent = "serious"
                elif "short" in goal:
                    intent = "casual"

        photos = [Photo(id=str(p.get("id", i)), url=p.get("url"))
                  for i, p in enumerate(user.get("photos", []))]
        return Profile(
            name=user.get("name", ""),
            age=_age(user.get("birth_date")),
            city=(user.get("position_info") or {}).get("country", "") or "—",
            bio=user.get("bio") or "",
            job=None,
            prompts=prompts,
            photos=photos,
            intent=intent,
            verified=bool(user.get("is_verified", False)),
            interests=[i for i in interests if i],
            descriptors=descriptors,
            email=user.get("email"),
        )

    def list_matches(self, limit: int = 30) -> list[Match]:
        """Recent matches with their latest messages (one paginated call set)."""
        client = TinderClient(self._token)
        with _call_lock:
            matches = client.load_all_matches()
        out: list[Match] = []
        for m in matches[:limit]:
            out.append(self._to_match(m))
        return out

    def get_match(self, match_id: str) -> Match:
        client = TinderClient(self._token)
        with _call_lock:
            m = client.get_match(match_id)
        return self._to_match(m, full_history=True)

    def _to_match(self, m, full_history: bool = False) -> Match:
        u = m.matched_user
        conversation: list[ChatTurn] = []
        try:
            me = self.self_id
            history = m.message_history
            msgs = history.load_all_messages() if full_history else history.get_messages()
            for msg in reversed(msgs):        # chronological
                conversation.append(ChatTurn(
                    sender="me" if msg.author_id == me else "them",
                    text=msg.content,
                    ts=getattr(msg, "sent_date", None),
                ))
        except Exception:
            log.debug("message history unavailable for match %s", m.id, exc_info=True)
        return Match(
            match_id=m.id,
            name=getattr(u, "name", None),
            age=_age(getattr(u, "birth_date", None)),
            bio=getattr(u, "bio", "") or "",
            photos=_photos(getattr(u, "photos", ())),
            verified=any("verif" in b.badge_type.lower() for b in getattr(u, "badges", ()) or ()),
            conversation=conversation,
        )

    # ---------------- writes (explicit user confirmation only) ----------------

    def update_bio(self, new_bio: str, confirm: bool = False) -> dict:
        if not confirm:
            raise PermissionError("confirm required")
        with _call_lock:
            res = requests.post(f"{BASE}/profile", headers=_headers(self._token),
                                json={"bio": new_bio}, timeout=20)
        if res.status_code == 401:
            raise PermissionError("401 unauthorized")
        res.raise_for_status()
        return res.json()

    def set_prompts(self, prompts: list[dict], confirm: bool = False) -> dict:
        """Write the full prompt set: [{question_id|id, answer_text}]."""
        if not confirm:
            raise PermissionError("confirm required")
        clean = [{"id": (p.get("id") or p.get("question_id")), "answer_text": p.get("answer_text", p.get("a", ""))}
                 for p in prompts if (p.get("id") or p.get("question_id"))]
        with _call_lock:
            res = requests.post(f"{BASE}/v2/profile/user?locale=en",
                                headers=_headers(self._token),
                                json={"selected_prompts": clean}, timeout=20)
        if res.status_code == 401:
            raise PermissionError("401 unauthorized")
        res.raise_for_status()
        return res.json()

    def send_message(self, match_id: str, text: str, confirm: bool = False) -> dict:
        """Send a message the user has explicitly reviewed and approved in the UI."""
        if not confirm:
            raise PermissionError("confirm required")
        with _call_lock:
            res = requests.post(f"{BASE}/user/matches/{match_id}",
                                headers=_headers(self._token),
                                json={"message": text}, timeout=20)
        if res.status_code == 401:
            raise PermissionError("401 unauthorized")
        res.raise_for_status()
        return res.json()

    # ---------------- swipes: implemented, deliberately NOT routed ----------------
    # Live-verified? No — blocked by the account-verification gate during research
    # (docs/research-findings.md §Swipes). These methods exist so verification can be
    # finished without touching the rest of the app, but no API route calls them yet.

    def _swipe(self, direction: str, user_id: str, confirm: bool) -> dict:
        if not confirm:
            raise PermissionError("confirm required")
        with _call_lock:
            res = requests.post(f"{BASE}/{direction}/{user_id}",
                                headers=_headers(self._token), timeout=20)
        if res.status_code == 401:
            raise PermissionError("401 unauthorized")
        res.raise_for_status()
        return res.json()

    def like(self, user_id: str, confirm: bool = False) -> dict:
        return self._swipe("like", user_id, confirm)

    def pass_on(self, user_id: str, confirm: bool = False) -> dict:
        return self._swipe("pass", user_id, confirm)
