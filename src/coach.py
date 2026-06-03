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
from schema import (Profile, Match, ProfileReport, DraftSet, ImprovementResult,
                    PromptSuggestionSet)

KB_PATH = Path(__file__).resolve().parent.parent / "knowledge" / "dating_profile_kb.md"

T = TypeVar("T", bound=BaseModel)

PROFILE_TASK = """You are a high-effort dating-profile coach for the Indian market. Using ONLY the \
knowledge pack above as your rubric, evaluate and AGGRESSIVELY improve the user's OWN profile.

EFFORT BAR (critical): Returning the input nearly unchanged is a FAILURE. Make real, specific changes.
NEVER fabricate facts — but reframe, sharpen, and combine the TRUE data into much stronger output.
The knowledge pack's examples are ILLUSTRATIVE ONLY — do NOT copy any example line verbatim; generate
fresh text built from THIS user's own data.

You are given rich data: bio, prompts, job, interests, and descriptors (zodiac, languages, workout,
pet, drinking/smoking, "looking for", love style, education, etc.). USE IT.

- bio_variants: write 2-3 DISTINCT rewrites of different tones, each 120-300 chars. Each MUST weave in
  >=2 specific TRUE details from interests/descriptors/job/prompts, use show-don't-tell (no bare
  adjectives or cliches), and end with ONE easy hook. If the current bio is already decent, still make
  it materially better or offer a strong alternative — do not echo it back.
- improved_prompts: REWRITE the answer to EVERY existing prompt (keep the SAME questions). One-word or
  generic answers (e.g. "Badminton", "Food and sports") are unacceptable and MUST become specific,
  vivid, reply-inviting lines using his real details. Assign roles across prompts (one funny, one
  thoughtful, one cute). Keep his real content; upgrade the delivery. Empty list ONLY if he has no prompts.
- photo_assessments + recommended_photo_order: assess every photo (keep/drop, slot, strengths, issues) using the `Photo.description` field (which contains rich visual VLM analysis of background, outfit, smile, grooming, framing, and selfies) or photo metadata. Evaluate quality, background clutter, wardrobe, facial expression/grooming, pose open-ness, and selfies. Give a best-first order by id. If no real images or descriptions are provided, reason from metadata and say so.
- prompt_suggestions: extra prompt ideas he could add. gaps: concrete missing pieces (e.g. "no full-body
  shot", "no job listed", intent vs 'Looking for' mismatch).
- Score photos and bio with the rubric's formulas (0-100); set overall to your weighted judgement; be
  honest (don't inflate). Flag cliches, negativity, and anything that hurts in the India safety-first market."""

PROMPT_SUGGEST_TASK = """You are a high-effort dating-profile coach for the Indian market. Using the \
knowledge pack's PROMPTS rubric (§3), pick the best prompt QUESTIONS for this user from the provided
catalog and write a great answer for each.

- Choose questions whose `question_id` EXISTS in the catalog below — never invent an id.
- Prefer questions that let the user show a SPECIFIC true detail from their data (interests, descriptors,
  job, existing prompts). Avoid questions that would force a generic answer.
- Each answer: specific, vivid, reply-inviting (NO one-word/generic answers), built ONLY from true data —
  never fabricate. Assign role variety across the set (one funny, one thoughtful, one cute/warm).
- No clichés, no negativity, nothing sexual. Don't copy knowledge-pack examples verbatim.
- Return exactly the requested number of suggestions, each with question_id, question_text, answer, rationale."""

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


def apply_report(profile: Profile, report: ProfileReport, bio_choice: int = 0) -> Profile:
    """Pure, deterministic: produce an improved Profile by applying the report.

    - bio  -> the chosen bio_variant (default = the first / top one)
    - prompts -> report.improved_prompts, if any
    - photos and every factual field (interests, descriptors, job, email, city, age...) are
      left UNCHANGED. Photos are intentionally out of scope for now.
    No LLM call here — just assembly, so it's testable offline and predictable.
    """
    updates: dict = {}
    if report.bio_variants:
        idx = bio_choice if 0 <= bio_choice < len(report.bio_variants) else 0
        updates["bio"] = report.bio_variants[idx].text
    if report.improved_prompts:
        updates["prompts"] = report.improved_prompts
    return profile.model_copy(update=updates)


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

    def improve_profile(self, profile: Profile, bio_choice: int = 0) -> ImprovementResult:
        """Profile JSON in -> {analysis report, improved profile JSON} out.

        One LLM call (the standardize step) produces the report; the improved profile is then
        assembled deterministically via apply_report(). `improved_profile` is the same Profile
        shape with the new bio + rewritten prompts applied; photos are left untouched.
        """
        report = self.standardize_profile(profile)
        improved = apply_report(profile, report, bio_choice=bio_choice)
        return ImprovementResult(report=report, improved_profile=improved)

    def suggest_prompts(self, profile: Profile, catalog: list[dict], n: int = 3) -> PromptSuggestionSet:
        """AI picks the best prompt QUESTIONS from the live catalog and drafts answers from the
        user's real data. `catalog` = [{question_id, question_text}, ...] (from the connector).
        Human reviews/edits, then create_prompt() writes the chosen ones. The AI never auto-writes.
        """
        if not catalog:
            return PromptSuggestionSet(suggestions=[], notes="No prompt catalog available to choose from.")

        # Exclude questions the user already uses, so we suggest fresh ones.
        used = {p.get("id") or p.get("question_id") for p in profile.prompts}
        pool = [c for c in catalog if c.get("question_id") not in used] or catalog

        system = self._system(PROMPT_SUGGEST_TASK, PromptSuggestionSet)
        user = (
            "USER PROFILE (use ONLY these true facts):\n" + profile.model_dump_json(indent=2)
            + "\n\nAVAILABLE PROMPT CATALOG (pick question_id ONLY from this list):\n"
            + json.dumps(pool, ensure_ascii=False)
            + f"\n\nReturn exactly {n} suggestions."
        )
        result = _parse(PromptSuggestionSet, self.llm.generate(system, user))

        # Validate against the catalog: drop hallucinated ids, fix question_text from the source of truth.
        by_id = {c["question_id"]: c["question_text"] for c in catalog}
        valid = []
        for s in result.suggestions:
            if s.question_id in by_id:
                s.question_text = by_id[s.question_id]
                valid.append(s)
        result.suggestions = valid[:n]
        return result

    def draft_replies(self, match: Match, my_profile: Profile) -> DraftSet:
        system = self._system(REPLY_TASK, DraftSet)
        user = (
            "MY profile (the sender):\n\n" + my_profile.model_dump_json(indent=2)
            + "\n\nThe MATCH and our conversation so far:\n\n" + match.model_dump_json(indent=2)
        )
        return _parse(DraftSet, self.llm.generate(system, user))

    def generate_profile_from_description(self, description: str) -> ImprovementResult:
        """User description text -> new optimized ProfileReport and Profile."""
        task = """You are a high-effort dating-profile coach for the Indian market.
Given a raw self-description by the user explaining their personality, daily life, work, hobbies, habits, and preferences:
Generate a highly optimized, brand new Tinder profile report that aligns with their facts.
You must return a JSON response matching the `ProfileReport` Pydantic model:
- overall_score: 100
- bio_score: 100
- photo_score: 100
- summary: A summary explaining the strategy of the generated profile.
- bio_variants: 3 creative, high-impact bio options of different tones (sincere, playful, witty) matching their description. Each 120-300 chars, showing instead of telling, and ending with a single hook.
- improved_prompts: 3 prompt suggestions with questions and answers based on their hobbies/facts (e.g. [{"q": "Together, we could...", "a": "blind taste-test the best street momos in Indiranagar"}]).
- photo_assessments: Empty list.
- recommended_photo_order: Empty list.
- prompt_suggestions: 3 prompt ideas they can add.
- gaps: Any gaps in their self-description (e.g. if they did not mention smoking/drinking habits, height, relationship type, or workout).
"""
        system = self._system(task, ProfileReport)
        user = f"User self-description:\n\n{description}"
        report = _parse(ProfileReport, self.llm.generate(system, user))
        
        # Create a mock Profile object with the first bio and generated prompts
        first_bio = report.bio_variants[0].text if report.bio_variants else ""
        mock_profile = Profile(
            name="New Profile",
            age=24,
            city="India",
            bio=first_bio,
            prompts=report.improved_prompts,
            photos=[],
            intent="unsure"
        )
        return ImprovementResult(report=report, improved_profile=mock_profile)
