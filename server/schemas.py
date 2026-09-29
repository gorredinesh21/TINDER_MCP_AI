"""Wingman AI — data contract between Tinder, the AI, and the UI.

The AI layer never talks to Tinder and the Tinder layer never talks to the AI; both
speak these Pydantic models. That keeps each side swappable and the whole thing
testable offline.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

# ---------- Inputs (Tinder side) ----------

PhotoType = Literal["solo_portrait", "full_body", "activity", "group", "selfie", "other"]
Intent = Literal["serious", "casual", "unsure"]


class Photo(BaseModel):
    id: str
    url: Optional[str] = None
    declared_type: Optional[PhotoType] = None
    caption: Optional[str] = None
    description: Optional[str] = None   # filled by Gemini photo vision


class Profile(BaseModel):
    """The user's OWN profile."""
    name: str
    age: int
    city: str
    bio: str = ""
    job: Optional[str] = None
    prompts: list[dict[str, str]] = Field(default_factory=list)   # [{q, a, id?, question_id?}]
    photos: list[Photo] = Field(default_factory=list)
    intent: Intent = "unsure"
    verified: bool = False
    interests: list[str] = Field(default_factory=list)
    descriptors: list[dict[str, str]] = Field(default_factory=list)
    email: Optional[str] = None


class ChatTurn(BaseModel):
    sender: Literal["me", "them"]
    text: str
    ts: Optional[str] = None


class Match(BaseModel):
    """A person the user matched with (read-only; Wingman only DRAFTS replies)."""
    match_id: str
    name: Optional[str] = None
    age: Optional[int] = None
    bio: str = ""
    interests: list[str] = Field(default_factory=list)
    photos: list[Photo] = Field(default_factory=list)
    verified: bool = False
    conversation: list[ChatTurn] = Field(default_factory=list)
    last_activity: Optional[str] = None
    is_new: bool = False


# ---------- Outputs (AI side) ----------

class BioVariant(BaseModel):
    text: str
    tone: str
    rationale: str
    char_count: int


class PhotoAssessment(BaseModel):
    photo_id: str
    keep: bool
    suggested_slot: Optional[int] = None
    strengths: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)


class ProfileReport(BaseModel):
    photo_score: int = Field(ge=0, le=100)
    bio_score: int = Field(ge=0, le=100)
    overall_score: int = Field(ge=0, le=100)
    summary: str
    bio_variants: list[BioVariant]
    photo_assessments: list[PhotoAssessment]
    recommended_photo_order: list[str]
    prompt_suggestions: list[str]
    gaps: list[str]
    improved_prompts: list[dict[str, str]] = Field(default_factory=list)


class ImprovementResult(BaseModel):
    report: ProfileReport
    improved_profile: Profile


class MessageDraft(BaseModel):
    text: str
    tone: str
    rationale: str
    char_count: int


class ConversationReport(BaseModel):
    """What the AI says about one match + conversation."""
    match_summary: str
    tone: str
    engagement: str                       # e.g. "high — she replies fast and asks back"
    topics: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    next_move: str                        # concrete suggestion for the next message
    drafts: list[MessageDraft]
    notes: str = ""


class AssistantAnswer(BaseModel):
    answer: str
    used_context: list[str] = Field(default_factory=list)
    followups: list[str] = Field(default_factory=list)


class PromptSuggestion(BaseModel):
    question_id: str
    question_text: str
    answer: str
    rationale: str


class PromptSuggestionSet(BaseModel):
    suggestions: list[PromptSuggestion]
    notes: str = ""
