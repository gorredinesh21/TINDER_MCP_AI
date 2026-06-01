"""
Profile JSON in -> improved profile JSON out (+ the analysis report).

Reads the most recent extracted_profile_*.json (what the connector dumps from your live
Tinder), or falls back to data/sample_profile.json. Runs the brain's improve_profile(),
prints the report, and writes improved_profile_<name>_<timestamp>.json.

Photos are intentionally left UNCHANGED for now (vision/photo-reading is a separate test to
run on your personal laptop where the image URLs open).

    python src/improve_demo.py

Needs an LLM backend (LLM_BACKEND=hf or ollama). Does NOT need a Tinder token — it reads the
already-extracted profile JSON. To push the improved bio to your live profile, see the printed
write-back line (manual-confirm).
"""
import glob
import sys
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from dotenv import load_dotenv

from coach import DatingCoach
from schema import Profile

load_dotenv()
ROOT = Path(__file__).resolve().parent.parent


def _load_profile() -> Profile:
    extracted = sorted(glob.glob(str(ROOT / "extracted_profile_*.json")))
    src = Path(extracted[-1]) if extracted else (ROOT / "data" / "sample_profile.json")
    print(f"[improve] input profile: {src.name}")
    return Profile.model_validate_json(src.read_text(encoding="utf-8"))


def main() -> None:
    profile = _load_profile()
    coach = DatingCoach()
    result = coach.improve_profile(profile)
    report, improved = result.report, result.improved_profile

    print(f"\n=== Report for {profile.name} ===")
    print(f"Scores  photos={report.photo_score} bio={report.bio_score} overall={report.overall_score}")
    print(f"Summary: {report.summary}")
    print(f"Gaps: {report.gaps}")

    print("\n=== Applied changes (photos untouched) ===")
    print(f"OLD bio: {profile.bio!r}")
    print(f"NEW bio: {improved.bio!r}")
    if improved.prompts != profile.prompts:
        print("Prompts rewritten:")
        for p in improved.prompts:
            print(f"  Q: {p.get('q','')}\n  A: {p.get('a','')}")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe = "".join(c for c in profile.name if c.isalnum() or c in " _-").strip().replace(" ", "_")
    out = ROOT / f"improved_profile_{safe}_{ts}.json"
    out.write_text(improved.model_dump_json(indent=2), encoding="utf-8")
    print(f"\nImproved profile JSON written to: {out.name}")

    print("\nTo push the new bio to your LIVE profile (manual-confirm, run on your laptop):")
    print("  from connector import TinderConnector")
    print(f'  TinderConnector().update_my_bio({improved.bio!r}, confirm=True)')


if __name__ == "__main__":
    main()
