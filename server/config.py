"""Wingman AI — configuration.

Everything comes from environment variables (12-factor). The product runs in two modes:

  ENV=local  (default) — binds 127.0.0.1, live Tinder connections allowed.
  ENV=cloud            — binds 0.0.0.0/PORT (Cloud Run), LIVE Tinder calls are refused;
                         the deployed instance is a demo (sample-data) only. Datacenter
                         IPs get real accounts flagged, so live mode is localhost-only
                         by design.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class Config:
    def __init__(self) -> None:
        self.env = os.getenv("ENV", "local").lower()
        self.is_cloud = self.env == "cloud"

        # --- AI (Google Cloud Gemini via Vertex AI; API key is a documented fallback) ---
        self.gcp_project = os.getenv("GCP_PROJECT", "personal-project-dg21")
        self.gcp_region = os.getenv("GCP_REGION", "us-central1")
        self.gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        self.gemini_api_key = os.getenv("GEMINI_API_KEY", "")  # optional: AI Studio key fallback
        self.llm_temperature = float(os.getenv("LLM_TEMPERATURE", "0.4"))
        self.llm_max_tokens = int(os.getenv("LLM_MAX_TOKENS", "8192"))
        # Gemini 2.5 thinking budget: 0 disables thinking (fast + enough for
        # structured JSON tasks); raise for harder reasoning if needed.
        self.thinking_budget = int(os.getenv("GEMINI_THINKING_BUDGET", "0"))

        # --- Sessions ---
        self.session_ttl_seconds = int(os.getenv("SESSION_TTL_SECONDS", str(2 * 60 * 60)))
        self.session_cookie = "wingman_sid"

        # --- Branding ---
        self.product_name = "Wingman AI"
        self.version = "2.0.0"

    @property
    def live_allowed(self) -> bool:
        return not self.is_cloud


config = Config()
