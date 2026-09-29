"""
Offline checks — NO network, NO API keys, NO Tinder. These are the contract CI
enforces on every push: schema plumbing, JSON extraction, error mapping, session
store, and demo-mode API behavior. Nothing here calls Gemini or Tinder.
"""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

DATA = Path(__file__).resolve().parent.parent / "data"


def test_sample_data_matches_schema():
    from server.schemas import Profile, Match
    p = Profile(**json.loads((DATA / "sample_profile.json").read_text()))
    matches = [Match(**m) for m in json.loads((DATA / "sample_matches.json").read_text())]
    assert p.name and p.age > 0
    assert len(matches) == 3 and all(m.match_id for m in matches)


def test_model_output_parses_into_pydantic():
    """Chatty/fenced model replies must still become typed objects."""
    from server.coach import _parse
    from server.schemas import ProfileReport
    reply = (
        "Sure! Here you go:\n```json\n"
        '{"photo_score":60,"bio_score":40,"overall_score":50,"summary":"ok",'
        '"bio_variants":[{"text":"x","tone":"warm","rationale":"r","char_count":1}],'
        '"photo_assessments":[],"recommended_photo_order":[],"prompt_suggestions":[],"gaps":[]}'
        "\n```"
    )
    rep = _parse(ProfileReport, reply)
    assert rep.overall_score == 50


def test_apply_report_deterministic():
    from server.coach import apply_report
    from server.schemas import BioVariant, Profile, ProfileReport
    profile = Profile(name="A", age=25, city="X", bio="old")
    report = ProfileReport(photo_score=1, bio_score=1, overall_score=1, summary="s",
                           bio_variants=[BioVariant(text="new", tone="t", rationale="r", char_count=3)],
                           photo_assessments=[], recommended_photo_order=[], prompt_suggestions=[], gaps=[])
    assert apply_report(profile, report).bio == "new"


def test_token_format_check():
    from server.errors import looks_like_token
    assert looks_like_token("bff5d171-23a4-4c8e-9f2a-6d1b0c7e4a58")
    assert not looks_like_token("hello")
    assert not looks_like_token("")


def test_friendly_error_mapping():
    from server.errors import from_exception
    e = from_exception(Exception("401 Unauthorized"), token=None, where="t")
    assert e.detail["code"] == "expired_token"
    e2 = from_exception(Exception("connection timed out"), token=None, where="t")
    assert e2.detail["code"] == "tinder_unreachable"
    assert "AxiosError" not in e2.detail["message"]


def test_scrub_never_leaks_token():
    from server.errors import scrub
    tok = "bff5d171-23a4-4c8e-9f2a-6d1b0c7e4a58"
    out = scrub(f"failed with {tok} for user", tok)
    assert tok not in out


def test_session_store_lifecycle():
    from server.session import SessionStore
    s = SessionStore()
    sid = s.create(token="x" * 36, name="Tester")
    assert s.get(sid).name == "Tester"
    s.drop(sid)
    assert s.get(sid) is None
    demo = s.create(token=None, name="Demo")
    assert s.get(demo).mode == "demo"
    assert s.get(demo).fingerprint == ""


def _client():
    import app as appmod
    return TestClient(appmod.app)


def test_health_and_demo_flow():
    client = _client()
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["product"] == "Wingman AI"

    # demo session: profile, matches, assistant-less reads
    r = client.post("/api/demo")
    assert r.status_code == 200
    r = client.get("/api/profile")
    assert r.status_code == 200 and r.json()["name"]
    r = client.get("/api/matches")
    assert r.status_code == 200 and len(r.json()["matches"]) == 3
    r = client.get("/api/session")
    assert r.json()["mode"] == "demo"

    # write actions must refuse in demo
    r = client.post("/api/actions/bio", json={"bio": "hi", "confirm": True})
    assert r.status_code == 400 and r.json()["error"]["code"] == "demo_action"
    r = client.post("/api/actions/send", json={"match_id": "x", "text": "hi", "confirm": True})
    assert r.status_code == 400

    # unknown route shape -> friendly error envelope
    r = client.get("/api/matches/sample-match-2")
    assert r.status_code == 200


def test_connect_rejects_malformed_token():
    client = _client()
    r = client.post("/api/connect", json={"token": "not-a-token"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "token_format"


def test_no_session_is_friendly():
    client = _client()
    r = client.get("/api/profile")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "no_session"
    assert "paste" in r.json()["error"]["message"].lower()


def test_swipes_not_routed():
    """Swipes stay unexposed: no API route may reach like/pass (by design)."""
    import server.routes as routes
    paths = {r.path for r in routes.router.routes}
    assert not any("swipe" in p or "like" in p or "pass" in p for p in paths)
