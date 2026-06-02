"""
Tinder AI Coach — local web dashboard.

Run:  python app.py     (then open http://127.0.0.1:8000)

Why local-first: the Tinder X-Auth-Token is full account access. This app binds to
127.0.0.1 only, uses the token in-memory for one request, and NEVER stores or logs it.
The HF API key stays in .env (server-side). Reviewers just: clone -> put HF key in .env ->
`python app.py` -> open the page -> paste their token (or click "Try with sample data").

Photo/vision analysis is intentionally OFF here (it needs local Ollama). The dashboard runs
on the HF text brain configured in .env, which is all a reviewer needs.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

load_dotenv()

from coach import DatingCoach          # noqa: E402
from connector import TinderConnector  # noqa: E402
from schema import Profile             # noqa: E402

app = FastAPI(title="Tinder AI Coach")
WEB = ROOT / "web"

_coach: DatingCoach | None = None


def get_coach() -> DatingCoach:
    """Build the brain once, lazily (so the server starts even if the key is missing;
    a misconfigured backend then surfaces as a friendly error on /api/analyze)."""
    global _coach
    if _coach is None:
        _coach = DatingCoach()
    return _coach


class AnalyzeRequest(BaseModel):
    token: str | None = None
    use_sample: bool = False
    use_vision: bool = False


class UpdateBioRequest(BaseModel):
    token: str
    bio: str


class ConfigRequest(BaseModel):
    hf_token: str


def _update_env(updates: dict[str, str]) -> None:
    """Update/insert keys in .env without disturbing the rest. Local file, user's own machine."""
    env_path = ROOT / ".env"
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    seen: set[str] = set()
    out: list[str] = []
    for ln in lines:
        m = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*=", ln)
        if m and m.group(1) in updates:
            out.append(f"{m.group(1)}={updates[m.group(1)]}")
            seen.add(m.group(1))
        else:
            out.append(ln)
    for k, v in updates.items():
        if k not in seen:
            out.append(f"{k}={v}")
    env_path.write_text("\n".join(out) + "\n", encoding="utf-8")


def _vision_ready() -> bool:
    try:
        import requests
        r = requests.get("http://127.0.0.1:11434/api/tags", timeout=1.5)
        if r.status_code != 200:
            return False
        vm = os.getenv("VISION_MODEL", "moondream").split(":")[0]
        return any(vm in m.get("name", "") for m in r.json().get("models", []))
    except Exception:
        return False


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return (WEB / "index.html").read_text(encoding="utf-8")


@app.get("/api/setup")
def setup(model: str | None = None) -> StreamingResponse:
    """Stream the one-click local-AI setup (Ollama + vision model) as newline-delimited JSON."""
    from setup_env import setup_steps
    return StreamingResponse(setup_steps(model), media_type="application/x-ndjson")


@app.get("/api/health")
def health() -> dict:
    backend = os.getenv("LLM_BACKEND", "ollama").lower()
    model = os.getenv("HF_MODEL") if backend == "hf" else os.getenv("OLLAMA_MODEL", "llama3.1")
    key_present = bool(os.getenv("HUGGINGFACEHUB_API_TOKEN")) if backend == "hf" else True
    return {"backend": backend, "model": model, "key_present": key_present,
            "vision_ready": _vision_ready(), "vision_model": os.getenv("VISION_MODEL", "moondream")}


@app.post("/api/config")
def config(req: ConfigRequest) -> dict:
    """Save the HF API key into .env (once), switch the text brain to HF, and reload."""
    global _coach
    token = (req.hf_token or "").strip()
    if not token.startswith("hf_"):
        raise HTTPException(status_code=400, detail="That doesn't look like a Hugging Face token (it should start with “hf_”).")
    updates = {"HUGGINGFACEHUB_API_TOKEN": token, "LLM_BACKEND": "hf"}
    if not os.getenv("HF_MODEL"):
        updates["HF_MODEL"] = "Qwen/Qwen2.5-72B-Instruct"   # a strong free default
    _update_env(updates)
    load_dotenv(override=True)   # refresh process env from the new .env
    _coach = None                # rebuild the brain with the new key/backend on next call
    return health()


@app.post("/api/analyze")
def analyze(req: AnalyzeRequest) -> dict:
    try:
        if req.use_sample:
            profile = Profile.model_validate_json((ROOT / "data" / "sample_profile.json").read_text(encoding="utf-8"))
        else:
            token = (req.token or "").strip()
            if not token:
                raise HTTPException(status_code=400, detail="Paste your Tinder X-Auth-Token first (or click “Try with sample data”).")
            profile = TinderConnector(auth_token=token).get_my_profile()

        # Optional: local vision (Ollama VLM) describes each photo so the text brain can
        # judge them. Best-effort — if Ollama/model/CDN isn't available, we skip silently.
        if req.use_vision and profile.photos:
            try:
                from vision import TinderVision
                profile.photos = TinderVision().describe_photos(profile.photos)
            except Exception:
                pass

        result = get_coach().improve_profile(profile)
        return {
            "profile": json.loads(profile.model_dump_json()),
            "report": json.loads(result.report.model_dump_json()),
            "improved": json.loads(result.improved_profile.model_dump_json()),
        }
    except HTTPException:
        raise
    except Exception as e:  # token bad/expired, backend misconfigured, model error, etc.
        raise HTTPException(status_code=400, detail=f"{type(e).__name__}: {e}")


@app.post("/api/update-bio")
def update_bio(req: UpdateBioRequest) -> dict:
    try:
        token = req.token.strip()
        if not token:
            raise HTTPException(status_code=400, detail="Missing Tinder token.")
        bio = req.bio.strip()
        if not bio:
            raise HTTPException(status_code=400, detail="Bio content cannot be empty.")
        
        conn = TinderConnector(auth_token=token)
        res = conn.update_my_bio(bio, confirm=True)
        return {"ok": True, "detail": "Profile bio updated live on Tinder!", "response": res}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Update failed: {e}")


if __name__ == "__main__":
    import uvicorn

    print("\n  Tinder AI Coach dashboard  ->  http://127.0.0.1:8000\n")
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")
