"""
The AI brain — now on Hugging Face / local models via LangChain (no Anthropic).

Reads a clean Profile/Match (schema.py), applies the India knowledge pack
(knowledge/dating_profile_kb.md), and returns structured Pydantic objects.

Why prompt+parse instead of native tool-calling: open models on HF/Ollama vary in
function-calling support, so we ask for raw JSON matching a schema and parse it
ourselves. That works on any instruct model.

HUMAN-IN-THE-LOOP: draft_replies() only DRAFTS. It never sends. (KB §5)

Note on photos: open text models aren't multimodal, so this version reasons from
each photo's declared_type + caption. For true image analysis, point a multimodal
model at it (Ollama: `llava`; HF: a vision model) — left as a later step.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Type, TypeVar

from pydantic import BaseModel, ValidationError

from llm import LLM, make_llm
from schema import Profile, Match, ProfileReport, DraftSet

KB_PATH = Path(__file__).resolve().parent.parent / "knowledge" / "dating_profile_kb.md"

T = TypeVar("T", bound=BaseModel)

PROFILE_TASK = """You are a dating-profile coach for the Indian market. Using ONLY the \
knowledge pack above as your rubric, evaluate and standardize the user's OWN profile.

- Score photos and bio with the rubric's formulas (0-100 each); set overall to your weighted judgement.
- Rewrite the bio into 2-3 variants of different tones. NEVER invent facts — only restate true \
details from the profile. Keep each 100-300 characters.
- Assess every photo (keep/drop, suggested slot, strengths, issues) and give a best-first order by id.
- Suggest prompt answers and list concrete gaps (e.g. "no full-body shot").
- Be specific and honest; flag cliches and anything that hurts in the India safety-first market."""

REPLY_TASK = """You are a dating-message assistant for the Indian market. Using ONLY the \
knowledge pack above as your rubric, DRAFT replies for the user to review and send.

- You are NOT sending anything. Produce 2-3 draft options of different tones (playful / sincere / \
curious) for the human to choose, edit, and send themselves.
- Personalize to THIS match: reference a specific detail from their bio / interests / chat.
- Openers: 5-15 words, end with something answerable; use the match's name if known.
- NEVER write sexual content, generic flattery, pickup-line cliches, or pressuring text.
- Respect pace: if the match is quiet or set a boundary, say so in `notes` and keep drafts \
low-pressure (or recommend not messaging)."""


def _extract_json(text: str) -> str:
    """Pull the first top-level JSON object out of a model's (possibly chatty) reply."""
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        return fenced.group(1)
    m = re.search(r"\{.*\}", text, re.DOTALL)  # greedy: first { to last }
    if not m:
        raise ValueError(f"No JSON object in model output:\n{text[:800]}")
    return m.group(0)


def _parse(model_cls: Type[T], text: str) -> T:
    raw = _extract_json(text)
    try:
        return model_cls.model_validate_json(raw)
    except ValidationError as e:
        raise ValueError(f"Model output didn't match {model_cls.__name__}:\n{raw[:800]}\n\n{e}") from e


class DatingCoach:
    def __init__(self, llm: LLM | None = None):
        self.llm = llm or make_llm()
        self._kb = KB_PATH.read_text(encoding="utf-8")
        print(f"[coach] backend = {self.llm.name}")

    def _system(self, task: str, model_cls: Type[BaseModel]) -> str:
        schema = json.dumps(model_cls.model_json_schema())
        return (
            "## KNOWLEDGE PACK (your rubric)\n\n" + self._kb + "\n\n"
            + task + "\n\n"
            + "Return ONLY a single JSON object (no markdown, no commentary) that conforms "
            + "exactly to this JSON Schema:\n" + schema
        )

    def standardize_profile(self, profile: Profile) -> ProfileReport:
        system = self._system(PROFILE_TASK, ProfileReport)
        user = "Here is the user's profile as JSON:\n\n" + profile.model_dump_json(indent=2)
        return _parse(ProfileReport, self.llm.generate(system, user))

    def draft_replies(self, match: Match, my_profile: Profile) -> DraftSet:
        system = self._system(REPLY_TASK, DraftSet)
        user = (
            "MY profile (the sender):\n\n" + my_profile.model_dump_json(indent=2)
            + "\n\nThe MATCH and our conversation so far:\n\n" + match.model_dump_json(indent=2)
        )
        return _parse(DraftSet, self.llm.generate(system, user))
