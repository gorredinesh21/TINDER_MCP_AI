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
        self._token = token
        self._client = TinderClient(token)          # raises LoginException if token is bad/expired
        self._self = self._client.get_self_user()
        self._self_id = self._self.id

    # ---------- read (automated) ----------

    def get_my_profile(self) -> Profile:
        u = self._self
        country = getattr(getattr(u, "position_info", None), "country", "") or ""
        
        # 1. Start with robust defaults from legacy profile payload
        photos_list = _photos(getattr(u, "photos", ()))
        interests_list = []
        descriptors_list = []
        prompts_list = []
        email_val = getattr(u, "email", None)
        intent_val = "unsure"
        
        # 2. Try fetching rich v2 profile data (interests, descriptors, prompts)
        try:
            import requests as req
            headers = {
                "X-Auth-Token": self._client._http._headers.get("X-Auth-Token", ""),
                "User-Agent": "Tinder/14.21.0 (iPhone; iOS 16.6.1; Scale/3.00)",
                "Content-Type": "application/json",
            }
            res = req.get("https://api.gotinder.com/v2/profile?include=account,user", headers=headers).json()
            if "data" in res and "user" in res["data"]:
                user_data = res["data"]["user"]
                
                # Fetch selected interests
                for item in user_data.get("user_interests", {}).get("selected_interests", []):
                    interests_list.append(item.get("name", ""))
                
                # Fetch prompts
                for p in user_data.get("user_prompts", {}).get("prompts", []):
                    prompts_list.append({
                        "q": p.get("question_text", ""),
                        "a": p.get("answer_text", ""),
                        "id": p.get("id", ""),
                        "question_id": p.get("question_id", "")
                    })
                
                # Fetch descriptors (zodiac, smoker, drinking, height, languages, etc.)
                for d in user_data.get("selected_descriptors", []):
                    name = d.get("name", d.get("id", ""))
                    # Clean up common raw IDs to human-readable names
                    if not name or name == "de_37":
                        name = "Languages"
                    elif name == "de_38":
                        name = "Relationship Type"
                    
                    choices = [c.get("name", "") for c in d.get("choice_selections", [])]
                    if choices:
                        descriptors_list.append({"name": name, "value": ", ".join(choices)})
                
                # Determine intent / looking for
                for d in user_data.get("selected_descriptors", []):
                    if d.get("id") == "de_29":  # "Looking for"
                        choices = [c.get("name", "") for c in d.get("choice_selections", [])]
                        if choices:
                            goal = choices[0].lower()
                            if "long" in goal:
                                intent_val = "serious"
                            elif "short" in goal:
                                intent_val = "casual"
        except Exception:
            pass  # Fallback to defaults to remain extremely robust if Tinder changes format
            
        return Profile(
            name=u.name,
            age=_age_from_birth_date(getattr(u, "birth_date", None)),
            city=country,
            bio=getattr(u, "bio", "") or "",
            job=_job_str(u),
            prompts=prompts_list,
            photos=photos_list,
            intent=intent_val,
            verified=_is_verified(u),
            interests=interests_list,
            descriptors=descriptors_list,
            email=email_val,
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

    def update_my_bio(self, new_bio: str, confirm: bool = False) -> dict:
        """Push a new bio to YOUR OWN profile. MANUAL-CONFIRM only — pass confirm=True.

        This edits your own profile (not messaging anyone), but it's still a write, so it
        refuses unless you explicitly confirm. The AI never calls this on its own; you call it
        after reviewing the improved bio. Uses a mobile User-Agent (same trick that made the
        v2/profile READ work on the work laptop).
        """
        if not confirm:
            raise RuntimeError(
                "update_my_bio refused: pass confirm=True to actually change your live bio."
            )
        import requests as _req
        headers = {
            "X-Auth-Token": self._token,
            "User-Agent": "Tinder/14.21.0 (iPhone; iOS 16.6.1; Scale/3.00)",
            "Content-Type": "application/json",
        }
        res = _req.post(
            "https://api.gotinder.com/profile",
            headers=headers,
            json={"bio": new_bio},
        )
        res.raise_for_status()
        return res.json()

    def update_my_prompt(self, prompt_id: str, question_id: str, new_answer: str, confirm: bool = False) -> dict:
        """Push an updated prompt answer to YOUR OWN profile. MANUAL-CONFIRM only.

        Uses the same mobile User-Agent to POST to v2/profile.
        """
        if not confirm:
            raise RuntimeError(
                "update_my_prompt refused: pass confirm=True to actually change your live prompt."
            )
        import requests as _req
        headers = {
            "X-Auth-Token": self._token,
            "User-Agent": "Tinder/14.21.0 (iPhone; iOS 16.6.1; Scale/3.00)",
            "Content-Type": "application/json",
        }
        payload = {
            "user_prompts": {
                "prompts": [
                    {
                        "id": prompt_id,
                        "question_id": question_id,
                        "answer_text": new_answer
                    }
                ]
            }
        }
        res = _req.post(
            "https://api.gotinder.com/v2/profile",
            headers=headers,
            json=payload,
        )
        res.raise_for_status()
        return res.json()

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
