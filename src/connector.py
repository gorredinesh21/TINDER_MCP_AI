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

    # ---------- prompts: create + update (reverse-engineered — VERIFY LIVE via probe_prompts.py) ----------

    def _api_headers(self) -> dict:
        return {
            "X-Auth-Token": self._token,
            "User-Agent": "Tinder/14.21.0 (iPhone; iOS 16.6.1; Scale/3.00)",
            "platform": "ios",
            "Content-Type": "application/json",
        }

    def _raw_user_prompts(self) -> list[dict]:
        """Your current prompts straight from the live profile (id, question_id, answer_text)."""
        import requests as _req
        r = _req.get("https://api.gotinder.com/v2/profile?include=user",
                     headers=self._api_headers(), timeout=15)
        r.raise_for_status()
        user = r.json().get("data", {}).get("user", {})
        out: list[dict] = []
        for p in user.get("user_prompts", {}).get("prompts", []):
            out.append({k: p.get(k) for k in ("id", "question_id", "question_text", "answer_text")
                        if p.get(k) is not None})
        return out

    def fetch_available_prompts(self) -> dict:
        """Discover Tinder's catalog of selectable prompt QUESTIONS.

        The catalog endpoint is undocumented, so we probe several known candidates and return each
        one's status + payload. Run src/probe_prompts.py live to see which works; then
        parse_available_prompts() pulls the question list out of the winner.
        """
        import requests as _req
        candidates = [
            # Tinder's static published config bundle — most likely home of the prompt catalog.
            "https://data.gotinder.com/v3/publish/app/json",
            "https://api.gotinder.com/v2/profile?include=available_prompts",
            "https://api.gotinder.com/v2/profile?locale=en&include=available_descriptors",
            "https://api.gotinder.com/v2/profile/prompts",
            "https://api.gotinder.com/v2/prompts",
            "https://api.gotinder.com/v2/dynamic-ui/configuration?include=prompts",
        ]
        results: dict = {}
        for url in candidates:
            try:
                r = _req.get(url, headers=self._api_headers(), timeout=15)
                ct = r.headers.get("content-type", "")
                results[url] = {"status": r.status_code,
                                "body": r.json() if ct.startswith("application/json") else r.text[:400]}
            except Exception as e:
                results[url] = {"error": str(e)}
        return results

    @staticmethod
    def parse_available_prompts(raw: dict) -> list[dict]:
        """Best-effort: pull [{question_id, question_text}] out of whatever a candidate returned.
        Walks the JSON looking for objects that carry a question id + text but no answer."""
        found: list[dict] = []

        def walk(obj):
            if isinstance(obj, dict):
                qid = obj.get("question_id") or obj.get("id")
                qtext = obj.get("question_text") or obj.get("text") or obj.get("prompt") or obj.get("name")
                if qid and qtext and "answer_text" not in obj:
                    found.append({"question_id": qid, "question_text": qtext})
                for v in obj.values():
                    walk(v)
            elif isinstance(obj, list):
                for v in obj:
                    walk(v)

        for entry in raw.values():
            if isinstance(entry, dict) and entry.get("status") == 200:
                walk(entry.get("body"))
        seen, uniq = set(), []
        for f in found:
            if f["question_id"] not in seen:
                seen.add(f["question_id"]); uniq.append(f)
        return uniq

    def set_prompts(self, prompts: list[dict], confirm: bool = False) -> dict:
        """Write the FULL prompt list to your own profile (Tinder replaces the whole set, so we
        always send every prompt — never just one — to avoid wiping the others).
        Each item: {"question_id":.., "answer_text":.., optional "id" for an existing one}."""
        if not confirm:
            raise RuntimeError("set_prompts refused: pass confirm=True to change your live prompts.")
        import requests as _req
        clean = [{k: p[k] for k in ("id", "question_id", "answer_text") if p.get(k)} for p in prompts]
        r = _req.post("https://api.gotinder.com/v2/profile",
                      headers=self._api_headers(), json={"user_prompts": {"prompts": clean}}, timeout=15)
        r.raise_for_status()
        return r.json()

    def create_prompt(self, question_id: str, answer_text: str, confirm: bool = False) -> dict:
        """Add a NEW prompt answer while keeping existing ones (fetch current → append → write all)."""
        if not confirm:
            raise RuntimeError("create_prompt refused: pass confirm=True to change your live profile.")
        current: list[dict] = []
        try:
            current = self._raw_user_prompts()
        except Exception:
            pass
        # The live read shows prompts use `id` (e.g. "pro_4"), NOT `question_id`. So the question
        # identifier passed in is written as `id`.
        merged = current + [{"id": question_id, "answer_text": answer_text}]
        return self.set_prompts(merged, confirm=True)

    def update_my_prompt(self, prompt_id: str, question_id: str, new_answer: str, confirm: bool = False) -> dict:
        """Update an EXISTING prompt's answer (re-sends the full set so others aren't wiped)."""
        if not confirm:
            raise RuntimeError("update_my_prompt refused: pass confirm=True to change your live prompt.")
        current = self._raw_user_prompts()
        for p in current:
            if (prompt_id and p.get("id") == prompt_id) or (question_id and p.get("question_id") == question_id):
                p["answer_text"] = new_answer
                break
        else:
            current.append({"question_id": question_id, "answer_text": new_answer})
        return self.set_prompts(current, confirm=True)

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
