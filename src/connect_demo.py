"""
LIVE end-to-end: pull your real Tinder profile + matches via the connector, then
run them through the AI brain. Standardizes your profile and drafts (NOT sends)
an opener for your most recent match.

Prereqs:
  - TINDER_X_AUTH_TOKEN in .env (see README "token guide")
  - an LLM backend configured (LLM_BACKEND=hf or ollama)
  - run on your OWN machine / home network (cloud IPs get accounts blocked)

    python src/connect_demo.py

Nothing is ever sent. To actually send a chosen draft, YOU call:
    TinderConnector().send_message(match_id, "your text")
"""
import sys
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from dotenv import load_dotenv

from connector import TinderConnector
from coach import DatingCoach

load_dotenv()


def main() -> None:
    conn = TinderConnector()           # raises if token missing/expired
    coach = DatingCoach()

    me = conn.get_my_profile()
    print(f"\n=== Your profile: {me.name}, {me.age}, {me.city} ===")
    report = coach.standardize_profile(me)
    print(f"Scores  photos={report.photo_score} bio={report.bio_score} overall={report.overall_score}")
    print(f"Summary: {report.summary}")
    print("Top bio rewrite:", report.bio_variants[0].text if report.bio_variants else "(none)")
    print("Gaps:", report.gaps)

    matches = conn.list_matches(limit=1, with_messages=True, enrich=True)
    if not matches:
        print("\nNo matches found.")
        return
    match = matches[0]
    print(f"\n=== Drafting for match: {match.name} (you review + send) ===")
    drafts = coach.draft_replies(match, me)
    print(f"What stood out: {drafts.match_summary}")
    for i, d in enumerate(drafts.drafts, 1):
        print(f"  {i}. [{d.tone}] {d.text}")
    print(f"Note: {drafts.notes}")
    print(f"\nTo send option 1 yourself:\n  TinderConnector().send_message('{match.match_id}', \"<your edited text>\")")


if __name__ == "__main__":
    main()
