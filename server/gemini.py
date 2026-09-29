"""Wingman AI — the AI layer. Google Cloud Gemini only (no Ollama, no local models).

Primary path:  Vertex AI (api endpoint per region, auth via the GCP metadata server on
               Cloud Run or `gcloud auth print-access-token` on a laptop). Works with
               zero API keys on the deployed instance and on any machine with gcloud.
Fallback path: GEMINI_API_KEY (Google AI Studio key) for environments without gcloud.

Both paths go through one class so the model can be changed by editing one env var
(GEMINI_MODEL) — nothing else in the app knows how the text was produced.

  generate(system, user) -> str            text reasoning (analysis, drafts, chat)
  describe_image(url, prompt) -> str       photo vision (profile photo feedback)
"""
from __future__ import annotations

import base64
import logging
import subprocess
import time
from typing import Any

import requests

from .config import config

log = logging.getLogger("wingman.ai")


class GeminiError(RuntimeError):
    pass


class _VertexAuth:
    """Access token from the GCP metadata server (Cloud Run/GCE) or the gcloud CLI."""

    def __init__(self) -> None:
        self._token: str | None = None
        self._expiry: float = 0

    def token(self) -> str:
        now = time.time()
        if self._token and now < self._expiry:
            return self._token
        # 1) metadata server (running inside GCP)
        try:
            r = requests.get(
                "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token",
                headers={"Metadata-Flavor": "Google"}, timeout=3)
            if r.status_code == 200:
                self._token = r.json()["access_token"]
                self._expiry = now + 45 * 60
                return self._token
        except requests.RequestException:
            pass
        # 2) local development via gcloud
        try:
            out = subprocess.run(["gcloud", "auth", "print-access-token"],
                                 capture_output=True, text=True, timeout=30)
            if out.returncode == 0 and out.stdout.strip():
                self._token = out.stdout.strip()
                self._expiry = now + 45 * 60
                return self._token
            raise GeminiError(
                "gcloud is not logged in. Run `gcloud auth application-default login` "
                "(or set GEMINI_API_KEY as a fallback).")
        except FileNotFoundError as e:
            raise GeminiError("gcloud CLI not found. Install it or set GEMINI_API_KEY.") from e


_auth = _VertexAuth()


def _endpoint_for(model: str) -> tuple[str, dict[str, str]]:
    """Return (url, headers) for the configured auth path."""
    if config.gemini_api_key:
        url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
               f"{model}:generateContent")
        return url, {"Content-Type": "application/json", "x-goog-api-key": config.gemini_api_key}
    url = (f"https://{config.gcp_region}-aiplatform.googleapis.com/v1/projects/"
           f"{config.gcp_project}/locations/{config.gcp_region}/publishers/google/"
           f"models/{model}:generateContent")
    return url, {"Content-Type": "application/json", "Authorization": f"Bearer {_auth.token()}"}


def _post(payload: dict[str, Any], model: str | None = None) -> str:
    model = model or config.gemini_model
    url, headers = _endpoint_for(model)
    last_status = None
    for attempt in range(3):
        res = requests.post(url, json=payload, headers=headers, timeout=90)
        last_status = res.status_code
        if res.status_code == 429:                       # back off and retry politely
            time.sleep(8 * (attempt + 1))
            continue
        if res.status_code >= 500:                       # transient model-service error
            time.sleep(3 * (attempt + 1))
            continue
        break
    if res.status_code != 200:
        raise GeminiError(f"Gemini API returned {last_status}: {res.text[:200]}")
    data = res.json()
    try:
        text = "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"])
    except (KeyError, IndexError) as e:
        raise GeminiError(f"Gemini returned no usable candidate: {str(data)[:200]}") from e
    if not text.strip():
        raise GeminiError("Gemini returned an empty response.")
    return text


def generate(system: str, user: str, model: str | None = None) -> str:
    """One system+user turn -> plain text. Used by every text feature."""
    payload: dict[str, Any] = {
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {
            "temperature": config.llm_temperature,
            "maxOutputTokens": config.llm_max_tokens,
            # 2.5 Flash is a thinking model: without a budget, thinking tokens
            # eat maxOutputTokens and the JSON gets truncated mid-stream.
            "thinkingConfig": {"thinkingBudget": config.thinking_budget},
        },
    }
    if system:
        payload["system_instruction"] = {"parts": [{"text": system}]}
    return _post(payload, model)


def describe_image(image_url: str, prompt: str) -> str:
    """Photo vision: fetch the image server-side, send inline to Gemini, return prose."""
    r = requests.get(image_url, timeout=20)
    r.raise_for_status()
    b64 = base64.b64encode(r.content).decode()
    mime = r.headers.get("Content-Type", "image/jpeg").split(";")[0]
    payload = {
        "contents": [{
            "role": "user",
            "parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": mime, "data": b64}},   # Vertex snake_case
            ],
        }],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 400},
    }
    try:
        return _post(payload)
    except GeminiError:
        # v1beta (API-key path) uses camelCase — retry once with that spelling
        payload["contents"][0]["parts"][1] = {
            "text": None,  # placeholder replaced below
        }
        payload["contents"][0]["parts"][1] = {"inlineData": {"mimeType": mime, "data": b64}}
        return _post(payload)


def backend_name() -> str:
    if config.gemini_api_key:
        return f"gemini-api-key:{config.gemini_model}"
    return f"vertex:{config.gemini_model}"
