"""
Clean data format ("the contract") the AI brain works against.

The brain never talks to Tinder directly. A connector (tinder.py with an
X-Auth-Token, a thin token client, or even manual paste) produces these
objects; the brain consumes them. Swap the connector freely — the brain
doesn't change.
"""
from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field


# ---------- Inputs (produced by the connector) ----------

PhotoType = Literal["solo_portrait", "full_body", "activity", "group", "selfie", "other"]
Intent = Literal["serious", "casual", "unsure"]


class Photo(BaseModel):
    id: str
    # Provide a local path OR a url so the brain can *see* the image (vision).
    # If neither is set, the brain reasons from `declared_type` + caption only.
    path: Optional[str] = None
    url: Optional[str] = None
    declared_type: Optional[PhotoType] = None
    caption: Optional[str] = None


class Profile(BaseModel):
    """The user's OWN profile (the thing we standardize)."""
    name: str
    age: int
    city: str
    bio: str = ""
    job: Optional[str] = None
    prompts: list[dict[str, str]] = Field(default_factory=list)  # [{"q":..,"a":..}]
    photos: list[Photo] = Field(default_factory=list)
    intent: Intent = "unsure"
    verified: bool = False
    interests: list[str] = Field(default_factory=list)
    descriptors: list[dict[str, str]] = Field(default_factory=list)  # [{"name": "Zodiac", "value": "Libra"}]
    email: Optional[str] = None


class ChatTurn(BaseModel):
    sender: Literal["me", "them"]
    text: str
    ts: Optional[str] = None


class Match(BaseModel):
    """A person the user matched with (read-only; we only DRAFT replies)."""
    match_id: str
    name: Optional[str] = None
    age: Optional[int] = None
    bio: str = ""
    interests: list[str] = Field(default_factory=list)
    photos: list[Photo] = Field(default_factory=list)
    verified: bool = False
    conversation: list[ChatTurn] = Field(default_factory=list)


# ---------- Outputs (produced by the AI brain, validated by structured output) ----------

class BioVariant(BaseModel):
    text: str
    tone: str = Field(description="e.g. playful, sincere, witty-dry")
    rationale: str = Field(description="why this works, tied to the rubric")
    char_count: int


class PhotoAssessment(BaseModel):
    photo_id: str
    keep: bool
    suggested_slot: Optional[int] = Field(
        default=None, description="1-based slot in the final ordering, or null if dropped"
    )
    strengths: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)


class ProfileReport(BaseModel):
    photo_score: int = Field(ge=0, le=100)
    bio_score: int = Field(ge=0, le=100)
    overall_score: int = Field(ge=0, le=100)
    summary: str
    bio_variants: list[BioVariant]
    photo_assessments: list[PhotoAssessment]
    recommended_photo_order: list[str] = Field(description="photo ids, best-first")
    prompt_suggestions: list[str]
    gaps: list[str] = Field(description="what's missing, e.g. 'no full-body shot'")


class MessageDraft(BaseModel):
    text: str
    tone: str
    rationale: str
    char_count: int


class DraftSet(BaseModel):
    match_summary: str = Field(description="1-2 lines on what stood out about the match")
    drafts: list[MessageDraft] = Field(description="2-3 options of different tones")
    notes: str = Field(description="any safety/pacing note for the user before sending")
