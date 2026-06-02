"""
Offline checks — NO network, NO API keys, NO Tinder. These are the contract that
CI enforces on every push, so either device (or its agent) gets a fast pass/fail
signal that the plumbing still works. They deliberately do NOT call any LLM or Tinder.
"""
import json
import os
from pathlib import Path

import pytest

DATA = Path(__file__).resolve().parent.parent / "data"


def test_sample_data_matches_schema():
    from schema import Profile, Match
    p = Profile(**json.loads((DATA / "sample_profile.json").read_text()))
    m = Match(**json.loads((DATA / "sample_match.json").read_text()))
    assert p.name and p.age > 0
    assert m.match_id


def test_model_output_parses_into_pydantic():
    """The brain asks for JSON; this is the extract+validate path that turns a
    chatty/fenced model reply into a typed object."""
    from coach import _parse
    from schema import ProfileReport
    reply = (
        "Sure! Here you go:\n```json\n"
        '{"photo_score":60,"bio_score":40,"overall_score":50,"summary":"ok",'
        '"bio_variants":[{"text":"x","tone":"playful","rationale":"y","char_count":1}],'
        '"photo_assessments":[{"photo_id":"p1","keep":true,"suggested_slot":1,'
        '"strengths":["clear face"],"issues":[]}],'
        '"recommended_photo_order":["p1"],"prompt_suggestions":["q"],"gaps":["no full-body"]}'
        "\n```\nHope that helps!"
    )
    report = _parse(ProfileReport, reply)
    assert report.overall_score == 50
    assert report.bio_variants[0].tone == "playful"


def test_apply_report_builds_improved_profile_without_touching_photos():
    """apply_report is pure (no LLM): bio + prompts get applied, photos stay untouched."""
    from coach import apply_report
    from schema import Profile, Photo, ProfileReport, BioVariant
    profile = Profile(
        name="Test", age=28, city="Pune", bio="old cliche bio",
        prompts=[{"q": "A perfect Sunday", "a": "idk"}],
        photos=[Photo(id="p1", url="http://x/1.jpg"), Photo(id="p2", url="http://x/2.jpg")],
    )
    report = ProfileReport(
        photo_score=50, bio_score=30, overall_score=40, summary="s",
        bio_variants=[BioVariant(text="new specific bio with a hook", tone="playful",
                                 rationale="r", char_count=28)],
        photo_assessments=[], recommended_photo_order=["p2", "p1"],
        prompt_suggestions=[], gaps=[],
        improved_prompts=[{"q": "A perfect Sunday", "a": "filter coffee then a long trek"}],
    )
    improved = apply_report(profile, report)
    assert improved.bio == "new specific bio with a hook"          # bio applied
    assert improved.prompts[0]["a"] == "filter coffee then a long trek"  # prompt applied
    assert improved.photos == profile.photos                        # photos UNCHANGED
    assert improved.age == 28 and improved.city == "Pune"           # facts preserved


def test_ollama_backend_constructs_offline():
    """ChatOllama construction does not hit the network."""
    os.environ["LLM_BACKEND"] = "ollama"
    os.environ["OLLAMA_MODEL"] = "llama3.1"
    from llm import make_llm
    llm = make_llm()
    assert llm.name.startswith("ollama:")


def test_hf_backend_dependency_importable():
    import importlib
    assert importlib.import_module("langchain_huggingface") is not None


def test_unknown_backend_raises():
    os.environ["LLM_BACKEND"] = "bogus"
    from llm import make_llm
    with pytest.raises(ValueError):
        make_llm()


def test_connector_imports_and_age_helper():
    import connector
    assert connector._age_from_birth_date("1996-07-15T00:00:00.000Z") >= 28


def test_connector_requires_token():
    os.environ.pop("TINDER_X_AUTH_TOKEN", None)
    from connector import TinderConnector
    with pytest.raises(RuntimeError):
        TinderConnector(auth_token=None)


def test_setup_detect_os():
    from setup_env import detect_os
    assert detect_os() in ("windows", "macos", "linux")


def test_setup_error_classifier():
    """The if/else 'knowledge' that turns raw failures into actionable hints."""
    from setup_env import classify
    assert "network" in classify("curl: (28) Failed to connect: timed out").lower()
    assert classify("write error: no space left on device")        # disk
    assert classify("'ollama' is not recognized as a command")     # PATH
    assert classify("Error: access is denied")                     # permission
    assert classify("totally fine, no errors here") == ""          # clean -> no false hint


def _web_client():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root for `import app`
    from fastapi.testclient import TestClient
    import app as webapp
    return TestClient(webapp.app)


def test_web_index_served():
    r = _web_client().get("/")
    assert r.status_code == 200 and "Tinder AI Coach" in r.text


def test_web_health_reports_backend():
    body = _web_client().get("/api/health").json()
    assert "backend" in body and "model" in body


def test_web_analyze_requires_token():
    # no token + no sample -> friendly 400, never touches the LLM
    r = _web_client().post("/api/analyze", json={})
    assert r.status_code == 400


def test_vision_offline(monkeypatch):
    """Verify TinderVision schema updates and offline mock description generation."""
    monkeypatch.setenv("TESTING_OFFLINE", "true")
    from schema import Photo
    from vision import TinderVision

    # 1. Verify schema update
    photo = Photo(id="p_test", url="http://x/test.jpg", description=None)
    assert photo.description is None

    # 2. Verify TinderVision mock behavior
    vision = TinderVision()
    updated = vision.describe_photos([photo])
    assert len(updated) == 1
    assert updated[0].description == "Mock description for photo p_test"

