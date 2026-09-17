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

load_dotenv(ROOT / ".env")

from coach import DatingCoach          # noqa: E402
from connector import TinderConnector  # noqa: E402
from schema import Profile             # noqa: E402

app = FastAPI(title="Tinder AI Coach")
WEB = ROOT / "web"

_coach: DatingCoach | None = None


def get_coach() -> DatingCoach:
    """Build the brain once, lazily, and rebuild dynamically if backend preference changes."""
    global _coach
    backend = os.getenv("LLM_BACKEND", "vertex").lower()
    if _coach is not None:
        active_llm_name = _coach.llm.name.lower()
        if not active_llm_name.startswith(backend):
            print(f"[coach] LLM backend changed from {active_llm_name} to {backend}. Rebuilding DatingCoach.")
            _coach = None

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
    hf_token: str | None = None
    gemini_token: str | None = None
    brain_backend: str | None = None
    vision_backend: str | None = None


class UpdatePromptRequest(BaseModel):
    token: str
    question_text: str
    answer_text: str


class GenerateProfileRequest(BaseModel):
    description: str


class AvailablePromptsRequest(BaseModel):
    token: str


class CreatePromptRequest(BaseModel):
    token: str
    question_id: str
    answer_text: str


class SuggestPromptsRequest(BaseModel):
    token: str
    n: int = 3


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
    backend = os.getenv("LLM_BACKEND", "vertex").lower()
    model = os.getenv("HF_MODEL") if backend == "hf" else (os.getenv("GEMINI_MODEL", "gemini-2.5-flash") if backend == "gemini" else os.getenv("OLLAMA_MODEL", "llama3.1"))
    
    if backend == "hf":
        key_present = bool(os.getenv("HUGGINGFACEHUB_API_TOKEN"))
    elif backend == "gemini":
        key_present = bool(os.getenv("GEMINI_API_KEY"))
    else:
        key_present = True
        
    vision_backend = os.getenv("VISION_BACKEND", "gemini" if os.getenv("GEMINI_API_KEY") else "ollama").lower()
        
    return {
        "backend": backend,
        "model": model,
        "key_present": key_present,
        "gemini_present": bool(os.getenv("GEMINI_API_KEY")),
        "vision_ready": _vision_ready(),
        "vision_model": os.getenv("VISION_MODEL", "moondream"),
        "vision_backend": vision_backend
    }


@app.post("/api/config")
def config(req: ConfigRequest) -> dict:
    """Save the HF API key, Gemini key, and/or backend selections into .env, and reload."""
    global _coach
    updates = {}
    
    if req.hf_token is not None:
        token = req.hf_token.strip()
        if token and not token.startswith("hf_"):
            raise HTTPException(status_code=400, detail="That doesn't look like a Hugging Face token (it should start with “hf_”).")
        if token:
            updates["HUGGINGFACEHUB_API_TOKEN"] = token
            if req.brain_backend is None:
                updates["LLM_BACKEND"] = os.getenv("LLM_BACKEND", "vertex")
            if not os.getenv("HF_MODEL"):
                updates["HF_MODEL"] = "Qwen/Qwen2.5-72B-Instruct"

    if req.gemini_token is not None:
        token = req.gemini_token.strip()
        if token and not token.startswith("AIzaSy"):
            raise HTTPException(status_code=400, detail="That doesn't look like a Google Gemini API key.")
        if token:
            updates["GEMINI_API_KEY"] = token
            if req.brain_backend is None:
                updates["LLM_BACKEND"] = "gemini"

    if req.brain_backend is not None:
        backend = req.brain_backend.strip().lower()
        if backend in ["hf", "gemini", "ollama"]:
            updates["LLM_BACKEND"] = backend

    if req.vision_backend is not None:
        v_backend = req.vision_backend.strip().lower()
        if v_backend in ["gemini", "ollama"]:
            updates["VISION_BACKEND"] = v_backend
            
    if updates:
        _update_env(updates)
        for k, v in updates.items():
            os.environ[k] = v
        load_dotenv(ROOT / ".env", override=True)
        _coach = None
        
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


@app.post("/api/generate-profile")
def generate_profile(req: GenerateProfileRequest) -> dict:
    try:
        desc = req.description.strip()
        if not desc:
            raise HTTPException(status_code=400, detail="Description text cannot be empty.")
            
        result = get_coach().generate_profile_from_description(desc)
        return {
            "profile": json.loads(result.improved_profile.model_dump_json()),
            "report": json.loads(result.report.model_dump_json()),
            "improved": json.loads(result.improved_profile.model_dump_json()),
        }
    except HTTPException:
        raise
    except Exception as e:
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


@app.post("/api/available-prompts")
def available_prompts(req: AvailablePromptsRequest) -> dict:
    """Fetch Tinder's selectable prompt-question catalog (reverse-engineered; verify live)."""
    try:
        conn = TinderConnector(auth_token=req.token.strip())
        raw = conn.fetch_available_prompts()
        return {"catalog": conn.parse_available_prompts(raw),
                "endpoint_status": {u: r.get("status", r.get("error")) for u, r in raw.items()}}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"{type(e).__name__}: {e}")


@app.post("/api/suggest-prompts")
def suggest_prompts_ep(req: SuggestPromptsRequest) -> dict:
    """AI picks prompt questions from the live catalog + drafts answers from the user's data.
    Returns suggestions (human reviews/edits), the full catalog, and current prompts. No auto-write."""
    try:
        conn = TinderConnector(auth_token=req.token.strip())
        catalog = conn.parse_available_prompts(conn.fetch_available_prompts())
        profile = conn.get_my_profile()
        sset = get_coach().suggest_prompts(profile, catalog, n=req.n)
        return {
            "suggestions": json.loads(sset.model_dump_json())["suggestions"],
            "notes": sset.notes,
            "catalog": catalog,
            "current_prompts": profile.prompts,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"{type(e).__name__}: {e}")


@app.post("/api/create-prompt")
def create_prompt_ep(req: CreatePromptRequest) -> dict:
    """Create a NEW prompt answer on the user's own profile (keeps existing prompts)."""
    try:
        conn = TinderConnector(auth_token=req.token.strip())
        res = conn.create_prompt(req.question_id.strip(), req.answer_text.strip(), confirm=True)
        return {"ok": True, "detail": "Prompt created on your Tinder profile!", "response": res}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"create failed: {e}")


@app.post("/api/update-prompt")
def update_prompt(req: UpdatePromptRequest) -> dict:
    try:
        token = req.token.strip()
        if not token:
            raise HTTPException(status_code=400, detail="Missing Tinder token.")
        question_text = req.question_text.strip()
        if not question_text:
            raise HTTPException(status_code=400, detail="Question text cannot be empty.")
        answer_text = req.answer_text.strip()
        if not answer_text:
            raise HTTPException(status_code=400, detail="Answer text cannot be empty.")
        
        conn = TinderConnector(auth_token=token)
        profile = conn.get_my_profile()
        
        if not profile.prompts:
            raise HTTPException(
                status_code=400,
                detail="You don't have any prompts active on your Tinder profile. Please add a prompt on the Tinder mobile app first, then you can update it here!"
            )
        
        def _normalize(s: str) -> str:
            import html
            s = html.unescape(s)
            return "".join(c.lower() for c in s if c.isalnum())

        prompt_id = None
        question_id = None
        norm_target = _normalize(question_text)
        
        # 1. Strict normalized match
        for p in profile.prompts:
            if _normalize(p.get("q", "")) == norm_target:
                prompt_id = p.get("id")
                question_id = p.get("question_id")
                break
                
        # 2. Substring matching (e.g. "together we could" vs "together, we could...")
        if not prompt_id:
            for p in profile.prompts:
                pq = _normalize(p.get("q", ""))
                if pq and norm_target and (pq in norm_target or norm_target in pq):
                    prompt_id = p.get("id")
                    question_id = p.get("question_id")
                    break
                    
        # 3. Key words intersection
        if not prompt_id:
            def _get_words(s: str) -> set[str]:
                return set(re.findall(r"\w+", s.lower()))
            target_words = _get_words(question_text)
            best_overlap = 0
            for p in profile.prompts:
                pq_words = _get_words(p.get("q", ""))
                overlap = len(target_words.intersection(pq_words))
                if overlap > best_overlap and overlap >= 2:
                    best_overlap = overlap
                    prompt_id = p.get("id")
                    question_id = p.get("question_id")
                    
        # 4. Fallback to first prompt if there is only 1 prompt active
        if not prompt_id:
            if len(profile.prompts) == 1:
                prompt_id = profile.prompts[0].get("id")
                question_id = profile.prompts[0].get("question_id")
                
        if not prompt_id:
            raise HTTPException(
                status_code=404, 
                detail="Matching prompt question not found on your profile. Please ensure the prompt exists on Tinder."
            )
            
        res = conn.update_my_prompt(prompt_id, question_id, answer_text, confirm=True)
        return {"ok": True, "detail": "Profile prompt updated live on Tinder!", "response": res}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Update failed: {e}")


if __name__ == "__main__":
    import uvicorn

    print("\n  Tinder AI Coach dashboard  ->  http://127.0.0.1:8000\n")
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")
