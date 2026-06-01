"""
Runnable demo: standardize a sample profile, then draft (not send) openers for a
sample match. Uses mock JSON data so it runs with zero Tinder connection.

    python src/demo.py            # both steps
    python src/demo.py profile    # just the standardizer
    python src/demo.py reply      # just the drafter

Requires ANTHROPIC_API_KEY in the environment (or a .env file).
"""
import json
import sys
from pathlib import Path

# Windows consoles default to cp1252 and mangle em-dashes/curly quotes — force UTF-8.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from dotenv import load_dotenv

from coach import DatingCoach
from schema import Profile, Match

load_dotenv()
DATA = Path(__file__).resolve().parent.parent / "data"


def show_profile(coach: DatingCoach) -> None:
    profile = Profile(**json.loads((DATA / "sample_profile.json").read_text()))
    print(f"\n=== Standardizing {profile.name}'s profile ===")
    report = coach.standardize_profile(profile)

    print(f"\nScores  photos={report.photo_score}  bio={report.bio_score}  overall={report.overall_score}")
    print(f"\nSummary: {report.summary}")
    print("\nBio rewrites:")
    for i, v in enumerate(report.bio_variants, 1):
        print(f"  {i}. [{v.tone}, {v.char_count} chars] {v.text}\n     why: {v.rationale}")
    print("\nPhoto plan:")
    for a in report.photo_assessments:
        slot = f"slot {a.suggested_slot}" if a.keep else "DROP"
        print(f"  {a.photo_id}: {slot}  +{a.strengths}  -{a.issues}")
    print(f"\nRecommended order: {report.recommended_photo_order}")
    print(f"Prompt ideas: {report.prompt_suggestions}")
    print(f"Gaps: {report.gaps}")


def show_reply(coach: DatingCoach) -> None:
    profile = Profile(**json.loads((DATA / "sample_profile.json").read_text()))
    match = Match(**json.loads((DATA / "sample_match.json").read_text()))
    print(f"\n=== Drafting openers for match: {match.name} (you review + send) ===")
    drafts = coach.draft_replies(match, profile)

    print(f"\nWhat stood out: {drafts.match_summary}")
    print("\nDraft options (pick one, edit, send yourself):")
    for i, d in enumerate(drafts.drafts, 1):
        print(f"  {i}. [{d.tone}, {d.char_count} chars] {d.text}\n     why: {d.rationale}")
    print(f"\nNote: {drafts.notes}")


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    coach = DatingCoach()
    if which in ("all", "profile"):
        show_profile(coach)
    if which in ("all", "reply"):
        show_reply(coach)
