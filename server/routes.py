"""Wingman AI — every API route, with session handling and friendly errors."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from . import gemini
from .config import config
from .errors import AppError, from_exception, looks_like_token, no_session
from .schemas import Match, Profile
from .session import Session, store
from .tinder_api import TinderAPI
from .coach import coach

log = logging.getLogger("wingman.api")
router = APIRouter(prefix="/api")

DATA = Path(__file__).resolve().parent.parent / "data"


# ---------- request models ----------

class ConnectBody(BaseModel):
    token: str


class AnalyzeBody(BaseModel):
    photo_vision: bool = True


class ConversationBody(BaseModel):
    match_id: str
    tone: str = "balanced"       # casual | funny | flirty | confident | balanced


class AssistantBody(BaseModel):
    question: str
    include_matches: bool = True


class DescriptionBody(BaseModel):
    description: str


class BioBody(BaseModel):
    bio: str
    confirm: bool = False


class PromptBody(BaseModel):
    prompts: list[dict]
    confirm: bool = False


class SendMessageBody(BaseModel):
    match_id: str
    text: str
    confirm: bool = False


# ---------- session plumbing ----------

def _session(request: Request) -> Session:
    sid = request.cookies.get(config.session_cookie)
    s = store.get(sid)
    if not s:
        raise no_session()
    return s


def _api(s: Session) -> TinderAPI:
    if s.mode != "live" or not s.token:
        raise AppError("live_required", "This feature needs a live Tinder connection — the demo uses sample data.", 400)
    if not config.live_allowed:
        raise AppError("cloud_live_blocked",
                       "This is the public demo instance, so live Tinder connections are disabled here. "
                       "Run Wingman AI on your own machine to connect your real account.", 403)
    return TinderAPI(s.token)


def _profile(s: Session) -> Profile:
    if s.mode == "live":
        return _api(s).get_profile()
    return Profile.model_validate_json((DATA / "sample_profile.json").read_text(encoding="utf-8"))


def _matches(s: Session, limit: int = 30) -> list[Match]:
    if s.mode == "live":
        return _api(s).list_matches(limit)
    raw = json.loads((DATA / "sample_matches.json").read_text(encoding="utf-8"))
    return [Match.model_validate(m) for m in raw]


# ---------- system ----------

@router.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "product": config.product_name,
        "version": config.version,
        "ai_backend": gemini.backend_name(),
        "mode": "cloud-demo" if config.is_cloud else "local",
        "live_allowed": config.live_allowed,
    }


# ---------- connection ----------

@router.post("/connect")
def connect(body: ConnectBody, request: Request) -> JSONResponse:
    token = (body.token or "").strip()
    if not looks_like_token(token):
        raise AppError("token_format",
                       "That doesn't look like a Tinder token — it's a 36-character code like "
                       "`a1b2c3d4-e5f6-...`. Open the step-by-step guide to copy it correctly.", 400)
    if not config.live_allowed:
        raise AppError("cloud_live_blocked",
                       "This is the public demo instance, so live Tinder connections are disabled here. "
                       "Run Wingman AI on your own machine (localhost) to connect your real account.", 403)
    try:
        api = TinderAPI(token)
        profile = api.verify()
    except AppError:
        raise
    except Exception as e:
        raise from_exception(e, token=token, where="connect")

    sid = store.create(token=token, name=profile.name)
    resp = JSONResponse({
        "connected": True,
        "mode": "live",
        "profile": {"name": profile.name, "age": profile.age, "bio_len": len(profile.bio),
                    "photos": len(profile.photos), "verified": profile.verified},
    })
    resp.set_cookie(config.session_cookie, sid, httponly=True, samesite="lax",
                    max_age=config.session_ttl_seconds)
    return resp


@router.post("/demo")
def start_demo(request: Request) -> JSONResponse:
    sample = Profile.model_validate_json((DATA / "sample_profile.json").read_text(encoding="utf-8"))
    sid = store.create(token=None, name=sample.name)
    resp = JSONResponse({"connected": True, "mode": "demo", "profile": {"name": sample.name}})
    resp.set_cookie(config.session_cookie, sid, httponly=True, samesite="lax",
                    max_age=config.session_ttl_seconds)
    return resp


@router.post("/disconnect")
def disconnect(request: Request) -> JSONResponse:
    store.drop(request.cookies.get(config.session_cookie))
    resp = JSONResponse({"connected": False})
    resp.delete_cookie(config.session_cookie)
    return resp


@router.get("/session")
def session_state(request: Request) -> dict:
    s = store.get(request.cookies.get(config.session_cookie))
    if not s:
        return {"connected": False, "mode": None}
    return {
        "connected": True,
        "mode": s.mode,
        "name": s.name,
        "token_fingerprint": s.fingerprint,
        "connected_at": s.created_at,
        "expires_after_idle_min": config.session_ttl_seconds // 60,
    }


# ---------- reads ----------

@router.get("/profile")
def get_profile(request: Request) -> dict:
    s = _session(request)
    try:
        return json.loads(_profile(s).model_dump_json())
    except AppError:
        raise
    except Exception as e:
        raise from_exception(e, token=s.token, where="profile")


@router.get("/matches")
def get_matches(request: Request) -> dict:
    s = _session(request)
    try:
        matches = _matches(s)
        return {"matches": _serialize_matches(matches)}
    except AppError:
        raise
    except Exception as e:
        raise from_exception(e, token=s.token, where="matches")


def _serialize_matches(matches: list[Match]) -> list[dict]:
    out = []
    for m in matches:
        d = m.model_dump(exclude={"conversation"})
        convo = m.conversation
        d["message_count"] = len(convo)
        d["last_message"] = convo[-1].model_dump() if convo else None
        d["waiting_on_me"] = bool(convo and convo[-1].sender == "them")
        out.append(d)
    return out


@router.get("/matches/{match_id}")
def get_match(match_id: str, request: Request) -> dict:
    s = _session(request)
    try:
        if s.mode == "live":
            m = _api(s).get_match(match_id)
        else:
            raw = json.loads((DATA / "sample_matches.json").read_text(encoding="utf-8"))
            m = next((Match.model_validate(x) for x in raw if x["match_id"] == match_id), None)
            if not m:
                raise AppError("not_found", "That conversation isn't in the demo data.", 404)
        return json.loads(m.model_dump_json())
    except AppError:
        raise
    except Exception as e:
        raise from_exception(e, token=s.token, where="match")


# ---------- AI ----------

@router.post("/ai/analyze-profile")
def ai_analyze_profile(body: AnalyzeBody, request: Request) -> dict:
    s = _session(request)
    try:
        profile = _profile(s)
        result = coach.analyze_profile(profile, with_photo_vision=body.photo_vision and s.mode == "live")
        return json.loads(result.model_dump_json())
    except AppError:
        raise
    except ValueError as e:
        raise AppError("ai_bad_output", "The AI returned something we couldn't use — please try again.", 502)
    except Exception as e:
        raise from_exception(e, token=s.token, where="analyze-profile")


@router.post("/ai/conversation")
def ai_conversation(body: ConversationBody, request: Request) -> dict:
    s = _session(request)
    try:
        matches = _matches(s)
        m = next((x for x in matches if x.match_id == body.match_id), None)
        if not m and s.mode == "live":
            m = _api(s).get_match(body.match_id)
        if not m:
            raise AppError("not_found", "We couldn't find that conversation. Refresh your matches and try again.", 404)
        my_profile = _profile(s)
        report = coach.analyze_conversation(m, my_profile, tone=body.tone)
        return json.loads(report.model_dump_json())
    except AppError:
        raise
    except ValueError:
        raise AppError("ai_bad_output", "The AI returned something we couldn't use — please try again.", 502)
    except Exception as e:
        raise from_exception(e, token=s.token, where="conversation")


@router.post("/ai/assistant")
def ai_assistant(body: AssistantBody, request: Request) -> dict:
    s = _session(request)
    try:
        profile = _profile(s)
        matches = _matches(s, limit=8) if body.include_matches else None
        answer = coach.assistant(body.question, profile, matches)
        return json.loads(answer.model_dump_json())
    except AppError:
        raise
    except ValueError:
        raise AppError("ai_bad_output", "The AI returned something we couldn't use — please try again.", 502)
    except Exception as e:
        raise from_exception(e, token=s.token, where="assistant")


@router.post("/ai/profile-from-description")
def ai_from_description(body: DescriptionBody) -> dict:
    desc = (body.description or "").strip()
    if len(desc) < 40:
        raise AppError("token_format",
                       "Tell us a bit more about yourself (at least a couple of lines) so the AI has something to work with.", 400)
    try:
        result = coach.profile_from_description(desc)
        return json.loads(result.model_dump_json())
    except ValueError:
        raise AppError("ai_bad_output", "The AI returned something we couldn't use — please try again.", 502)
    except Exception as e:
        raise from_exception(e, token=None, where="profile-from-description")


# ---------- actions (always user-confirmed) ----------

@router.post("/actions/bio")
def action_bio(body: BioBody, request: Request) -> dict:
    s = _session(request)
    bio = (body.bio or "").strip()
    if not bio:
        raise AppError("token_format", "The bio can't be empty.", 400)
    if not body.confirm:
        raise AppError("confirm_required",
                       "For safety this action only runs when you press the confirmation button in the app.", 400)
    if s.mode != "live":
        raise AppError("demo_action",
                       "This is the demo with sample data, so live changes are disabled. Connect your own account to edit your real bio.", 400)
    try:
        api = _api(s)
        api.update_bio(bio, confirm=True)
        return {"ok": True, "message": "Your Tinder bio has been updated. Open Tinder to see it live."}
    except AppError:
        raise
    except Exception as e:
        raise from_exception(e, token=s.token, where="update-bio")


@router.post("/actions/prompts")
def action_prompts(body: PromptBody, request: Request) -> dict:
    s = _session(request)
    if not body.confirm:
        raise AppError("confirm_required",
                       "For safety this action only runs when you press the confirmation button in the app.", 400)
    if s.mode != "live":
        raise AppError("demo_action",
                       "This is the demo with sample data, so live changes are disabled. Connect your own account to edit your real prompts.", 400)
    try:
        api = _api(s)
        api.set_prompts(body.prompts, confirm=True)
        return {"ok": True, "message": "Your profile prompts have been updated on Tinder."}
    except AppError:
        raise
    except Exception as e:
        raise from_exception(e, token=s.token, where="update-prompts")


@router.post("/actions/send")
def action_send(body: SendMessageBody, request: Request) -> dict:
    s = _session(request)
    text = (body.text or "").strip()
    if not text:
        raise AppError("token_format", "Message can't be empty.", 400)
    if not body.confirm:
        raise AppError("confirm_required",
                       "Wingman never sends on its own — review the draft and press Send to confirm.", 400)
    if s.mode != "live":
        raise AppError("demo_action",
                       "This is the demo with sample data, so sending is disabled. Connect your own account to message a real match.", 400)
    try:
        api = _api(s)
        api.send_message(body.match_id, text, confirm=True)
        return {"ok": True, "message": "Message sent. You can see it in your Tinder app."}
    except AppError:
        raise
    except Exception as e:
        raise from_exception(e, token=s.token, where="send-message")


# ---------- diagnostics (Connection Health) ----------

@router.get("/diagnostics")
def diagnostics(request: Request) -> dict:
    """Which capabilities are available RIGHT NOW on the connected account?"""
    s = _session(request)
    checks: list[dict] = []
    if s.mode != "live":
        return {"mode": "demo", "checks": [
            {"name": "Demo data", "ok": True, "note": "All demo features work without a Tinder connection."}]}
    api = _api(s)
    token = s.token

    def run(name: str, fn) -> None:
        try:
            fn()
            checks.append({"name": name, "ok": True, "note": "working"})
        except AppError as e:
            checks.append({"name": name, "ok": False, "note": e.detail["message"] if isinstance(e.detail, dict) else str(e.detail)})
        except Exception as e:
            friendly = from_exception(e, token=token, where=f"diag:{name}")
            checks.append({"name": name, "ok": False, "note": friendly.detail["message"] if isinstance(friendly.detail, dict) else "unavailable"})

    run("Read your profile", api.get_profile)
    run("Read your matches", lambda: api.list_matches(limit=5))
    run("AI service (Gemini on GCP)", lambda: gemini.generate(
        "Reply with the single word: ok", "ping", model=None) and None)
    locked = any((not c["ok"]) and c["name"] == "Read your matches" for c in checks)
    return {"mode": "live", "checks": checks,
            "note": ("Your account is in a Tinder verification/review state — profile tools work, "
                     "match tools will unlock after the review. This is observed live."
                     if locked else "All systems normal.")}
