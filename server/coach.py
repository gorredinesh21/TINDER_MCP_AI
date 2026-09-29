"""Wingman AI — the AI brain (Google Cloud Gemini only).

All prompts return strict JSON validated against Pydantic models, so a bad model
response is caught here and never reaches the UI half-formed.

Safety is structural: this module has NO import of the Tinder layer and no way to
send anything. It only ever produces drafts, analyses, and suggestions; every write
to Tinder goes through an explicit user-confirmed action route.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Type, TypeVar

from pydantic import BaseModel, ValidationError

from . import gemini
from .schemas import (AssistantAnswer, ConversationReport, ImprovementResult, Match,
                      Profile, ProfileReport, PromptSuggestionSet)

log = logging.getLogger("wingman.coach")

KB_PATH = Path(__file__).resolve().parent.parent / "knowledge" / "dating_profile_kb.md"
PHOTO_PROMPT = (
    "You are a dating-profile photo reviewer. Describe this photo in 2-3 sentences for "
    "a coach who cannot see it: framing (close-up / half / full body), setting and "
    "background clutter, outfit impression, facial expression and apparent mood, "
    "grooming, whether it looks like a selfie or taken by someone else, and overall "
    "quality for a dating profile. Be specific and honest, never crude."
)

T = TypeVar("T", bound=BaseModel)

PROFILE_TASK = """You are a high-effort dating-profile coach for the Indian market. Using ONLY the \
knowledge pack above as your rubric, evaluate and AGGRESSIVELY improve the user's OWN profile.

EFFORT BAR: returning the input nearly unchanged is a FAILURE. Make real, specific changes.
NEVER fabricate facts — but reframe, sharpen, and combine the TRUE data into much stronger output.
The knowledge pack's examples are ILLUSTRATIVE ONLY — never copy an example line verbatim.

You are given rich data: bio, prompts, job, interests, and descriptors (zodiac, languages, workout, \
pet, drinking/smoking, "looking for", education, etc.). USE IT.

- bio_variants: 2-3 DISTINCT rewrites of different tones, each 120-300 chars. Each MUST weave in \
>=2 specific TRUE details from interests/descriptors/prompts, use show-don't-tell (no bare adjectives \
or cliches), and end with ONE easy hook. If the current bio is decent, still make it materially better.
- improved_prompts: REWRITE the answer to EVERY existing prompt (keep the SAME questions). Generic \
answers MUST become specific, vivid, reply-inviting lines using his real details. Assign roles across \
prompts (one funny, one thoughtful, one cute). Empty list ONLY if he has no prompts.
- photo_assessments + recommended_photo_order: assess every photo (keep/drop, slot, strengths, issues) \
using each photo's `description` field when present (that is real visual analysis of background, outfit, \
smile, grooming, framing). Otherwise reason from metadata and say so.
- prompt_suggestions: extra prompt ideas he could add.
- gaps: concrete missing pieces (e.g. "no full-body shot", "no job listed", intent mismatch).
- Score photos and bio with the rubric's formulas (0-100); overall = your weighted judgement; be honest, \
don't inflate. Flag cliches, negativity, anything that hurts in the India safety-first market."""

CONVERSATION_TASK = """You are a dating-conversation coach for the Indian market. Using the knowledge \
pack above as your rubric, analyze ONE match's conversation and draft the user's next message.

- match_summary: 1-2 lines on what stood out about this person.
- tone + engagement: read the temperature — who invests more, response patterns, is it warming up or \
fading. Quote specifics from the chat as evidence.
- topics: shared threads worth pulling on.
- issues: anything hurting (interview-mode, one-word answers, too-fast escalation, dead air).
- next_move: one concrete strategy sentence.
- drafts: 3 reply options in the REQUESTED tone family (plus one contrasting alternative). Personalize \
to a specific detail from their bio/interests/chat. 5-60 words each, natural texting English, never \
cringe pickup lines, nothing sexual, no pressuring. If the match has gone quiet or set a boundary, keep \
drafts low-pressure or recommend a graceful pause in `notes`.
- notes: safety/pacing guidance the user should read before sending."""

ASSISTANT_TASK = """You are Wingman AI — a sharp, warm dating assistant for the Indian market, using \
the knowledge pack as your rubric. Answer the user's question using ONLY the provided context \
(their profile, matches, and conversations as JSON) plus general dating-coach judgment.

Rules:
- Be direct and specific; quote their actual data (bio lines, interests, chat messages) in your advice.
- If the context doesn't contain what you'd need (e.g. no conversations yet), say so plainly and give \
the best general advice instead of pretending.
- You never message anyone or change anything: everything you suggest is for the user to review and act on.
- Suggest 2-3 concrete follow-up questions in `followups` the user might ask next.
- Keep answers under 220 words unless a longer rewrite is genuinely needed."""

DESCRIPTION_TASK = """You are a high-effort dating-profile coach for the Indian market. The user described \
themselves in their own words. Design a brand-new optimized Tinder profile from those facts ONLY.
- bio_variants: 3 options of distinct tones (sincere, playful, witty), each 120-300 chars, showing not \
telling, one hook each, built from their real details.
- improved_prompts: 3 {q, a} prompt pairs based on their facts (question + vivid answer).
- photo_assessments + recommended_photo_order: empty lists.
- prompt_suggestions: 3 more prompt ideas.
- gaps: what they didn't tell you that a strong profile needs (habits, height, workout, languages...).
- Set the three scores to honest FIRST-DRAFT estimates (not automatically 100): bio_score for your best \
variant's quality, photo_score 50 (unknown), overall the weighted result."""


def _extract_json(text: str) -> str:
    """First top-level JSON object out of a (possibly chatty) model reply."""
    cleaned = re.sub(r"```(?:json)?\s*", "", text)
    cleaned = re.sub(r"\s*```", "", cleaned)
    start = cleaned.find("{")
    if start == -1:
        log.warning("[coach] no JSON object in output (len=%d): %s", len(text), text[:200])
        raise ValueError(f"no JSON object in model output: {text[:400]}")
    depth = 0
    for i, ch in enumerate(cleaned[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return cleaned[start:i + 1]
    log.warning("[coach] unbalanced JSON (len=%d, tail=…%s)", len(text), text[-120:])
    raise ValueError(f"unbalanced JSON in model output: {text[:400]}")


def _parse(model_cls: Type[T], text: str) -> T:
    raw = _extract_json(text)
    try:
        return model_cls.model_validate_json(raw)
    except ValidationError as e:
        log.warning("[coach] output failed %s validation: %s", model_cls.__name__, str(e)[:300])
        raise ValueError("model output did not match the expected shape") from e


def apply_report(profile: Profile, report: ProfileReport, bio_choice: int = 0) -> Profile:
    """Deterministic: apply the report to produce an improved profile (no AI call)."""
    updates: dict = {}
    if report.bio_variants:
        idx = bio_choice if 0 <= bio_choice < len(report.bio_variants) else 0
        updates["bio"] = report.bio_variants[idx].text
    if report.improved_prompts:
        updates["prompts"] = report.improved_prompts
    return profile.model_copy(update=updates)


class Coach:
    """All AI features. One instance per process; Gemini is stateless REST."""

    def __init__(self) -> None:
        self._kb = KB_PATH.read_text(encoding="utf-8") if KB_PATH.exists() else ""

    # ---------- system prompt assembly ----------

    def _system(self, task: str, model_cls: type[BaseModel]) -> str:
        schema = json.dumps(model_cls.model_json_schema())
        parts = []
        if self._kb:
            parts.append("## KNOWLEDGE PACK (your rubric)\n\n" + self._kb + "\n\n")
        parts.append(task)
        parts.append(
            "\n\nReturn ONLY a single JSON object (no markdown fences, no commentary) that "
            "conforms exactly to this JSON Schema:\n" + schema)
        return "".join(parts)

    # ---------- features ----------

    def analyze_profile(self, profile: Profile, with_photo_vision: bool = True) -> ImprovementResult:
        profile = profile.model_copy(deep=True)
        if with_photo_vision and profile.photos:
            for p in profile.photos:
                if not p.url or p.description:
                    continue
                try:
                    p.description = gemini.describe_image(p.url, PHOTO_PROMPT)
                except Exception as e:                     # vision is best-effort
                    log.info("[coach] photo vision skipped for %s: %s", p.id, e)
        system = self._system(PROFILE_TASK, ProfileReport)
        user = "Here is the user's profile as JSON:\n\n" + profile.model_dump_json(indent=2)
        report = _parse(ProfileReport, gemini.generate(system, user))
        return ImprovementResult(report=report, improved_profile=apply_report(profile, report))

    def analyze_conversation(self, match: Match, my_profile: Profile, tone: str = "balanced") -> ConversationReport:
        system = self._system(CONVERSATION_TASK, ConversationReport)
        user = (
            f"MY profile (the sender):\n{my_profile.model_dump_json(indent=2)}\n\n"
            f"REQUESTED TONE for drafts: {tone}\n\n"
            f"The MATCH and our conversation so far:\n{match.model_dump_json(indent=2)}"
        )
        return _parse(ConversationReport, gemini.generate(system, user))

    def assistant(self, question: str, my_profile: Profile | None, matches: list[Match] | None) -> AssistantAnswer:
        context_bits: list[str] = []
        if my_profile:
            context_bits.append("MY PROFILE:\n" + my_profile.model_dump_json(indent=2))
            used = ["profile"]
        else:
            used = []
        if matches:
            slim = [m.model_dump(include={"match_id", "name", "age", "bio", "interests", "conversation"}) for m in matches[:8]]
            context_bits.append("MY MATCHES AND CONVERSATIONS (most recent 8):\n" + json.dumps(slim, ensure_ascii=False, indent=1))
            used.append("matches")
        system = self._system(ASSISTANT_TASK, AssistantAnswer)
        user = "\n\n".join(context_bits) + f"\n\nQUESTION: {question}"
        return _parse(AssistantAnswer, gemini.generate(system, user))

    def suggest_prompts(self, profile: Profile, catalog: list[dict], n: int = 3) -> PromptSuggestionSet:
        if not catalog:
            return PromptSuggestionSet(suggestions=[], notes="No prompt catalog was available to choose from.")
        task = """You are a dating-profile coach for the Indian market. Pick the best prompt QUESTIONS for \
this user from the provided catalog and write a great answer for each (knowledge-pack prompts rubric).
- Choose question_ids that EXIST in the catalog — never invent one.
- Prefer questions that let the user show a SPECIFIC true detail. No generic answers.
- Role variety across the set (one funny, one thoughtful, one warm).
- Return exactly the requested number of suggestions."""
        system = self._system(task, PromptSuggestionSet)
        used = {p.get("id") or p.get("question_id") for p in profile.prompts}
        pool = [c for c in catalog if c.get("question_id") not in used] or catalog
        user = (
            "USER PROFILE (use ONLY these true facts):\n" + profile.model_dump_json(indent=2)
            + "\n\nAVAILABLE PROMPT CATALOG (pick question_id ONLY from this list):\n"
            + json.dumps(pool, ensure_ascii=False)
            + f"\n\nReturn exactly {n} suggestions."
        )
        result = _parse(PromptSuggestionSet, gemini.generate(system, user))
        by_id = {c["question_id"]: c["question_text"] for c in catalog}
        valid = []
        for s in result.suggestions:
            if s.question_id in by_id:
                s.question_text = by_id[s.question_id]
                valid.append(s)
        result.suggestions = valid[:n]
        return result

    def profile_from_description(self, description: str) -> ImprovementResult:
        system = self._system(DESCRIPTION_TASK, ProfileReport)
        report = _parse(ProfileReport, gemini.generate(system, "User self-description:\n\n" + description))
        first_bio = report.bio_variants[0].text if report.bio_variants else ""
        mock = Profile(
            name="New Profile", age=24, city="India", bio=first_bio,
            prompts=report.improved_prompts, photos=[], intent="unsure",
        )
        return ImprovementResult(report=report, improved_profile=mock)


coach = Coach()
