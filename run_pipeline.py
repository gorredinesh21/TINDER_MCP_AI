"""
Automatic pipeline:
1. Extract live Tinder profile data.
2. Send to DatingCoach (LangChain LLM) for profile optimization.
3. Automatically update the live Tinder profile bio with the best variant.
"""
import os
import sys
from pathlib import Path
from datetime import datetime

# Add src/ to path
src_dir = Path(__file__).resolve().parent / "src"
sys.path.insert(0, str(src_dir))

from dotenv import load_dotenv
from connector import TinderConnector
from coach import DatingCoach
from schema import Profile

load_dotenv()

def main():
    print("🚀 [Pipeline] Starting complete Tinder AI Profile Optimizer Pipeline...")
    
    # 1. Initialize connector and coach
    print("\n🔗 [1/3] Connecting to live Tinder account...")
    try:
        conn = TinderConnector()
    except Exception as e:
        print(f"❌ Failed to connect to Tinder: {e}")
        return

    # 2. Extract profile
    print("📥 Extracting your live profile...")
    try:
        me = conn.get_my_profile()
        print(f"✅ Connected successfully! Profile name: '{me.name}', Age: {me.age}, City: '{me.city}'")
        print(f"📝 Current Bio: {me.bio!r}")
    except Exception as e:
        print(f"❌ Failed to extract profile: {e}")
        return

    # Save raw extracted profile
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = "".join(c for c in me.name if c.isalnum() or c in (" ", "_", "-")).strip().replace(" ", "_")
    filename = f"extracted_profile_{safe_name}_{timestamp}.json"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(me.model_dump_json(indent=2))
    print(f"💾 Saved current profile snapshot to: {filename}")

    # 3. Optimize via Brain
    print("\n🧠 [2/3] Analyzing and optimizing profile via DatingCoach Brain...")
    print(f"⚙️ Using LLM backend: {os.getenv('LLM_BACKEND', 'ollama')}")
    print(f"🤖 Model: {os.getenv('HF_MODEL', 'Qwen/Qwen2.5-72B-Instruct')}")
    
    coach = DatingCoach()
    try:
        result = coach.improve_profile(me)
        report, improved = result.report, result.improved_profile
    except Exception as e:
        print(f"❌ Brain analysis failed: {e}")
        return

    print("\n📊 --- ANALYSIS REPORT ---")
    print(f"⭐ Scores: Photos = {report.photo_score}/100, Bio = {report.bio_score}/100, Overall = {report.overall_score}/100")
    print(f"💡 Summary: {report.summary}")
    print(f"⚠️ Gaps Identified: {report.gaps}")
    
    print("\n✍️ --- BIO VARIANTS GENERATED ---")
    for idx, variant in enumerate(report.bio_variants, 1):
        print(f"\nVariant {idx} [{variant.tone}]:")
        print(f"  {variant.text}")
        print(f"  Rationale: {variant.rationale}")

    # We will choose the first variant (best/top one)
    if not report.bio_variants:
        print("❌ No bio variants returned by the model. Aborting update.")
        return
        
    best_bio = report.bio_variants[0].text
    print(f"\n🎯 Selected Best Bio Variant: {best_bio!r}")

    # 4. Write back to Tinder
    print("\n📤 [3/3] Writing updated bio back to live Tinder profile...")
    try:
        res = conn.update_my_bio(best_bio, confirm=True)
        print("✅ Tinder profile updated successfully!")
        print(f"Response: {res}")
    except Exception as e:
        print(f"❌ Failed to update live Tinder bio: {e}")
        return

    # 5. Verify update by fetching again
    print("\n🔍 Verifying changes live on Tinder server...")
    try:
        verified_conn = TinderConnector()
        refetched_me = verified_conn.get_my_profile()
        print(f"📊 Refetched live bio: {refetched_me.bio!r}")
        if refetched_me.bio == best_bio:
            print("🎉 SUCCESS! Live profile matches the optimized bio perfectly.")
        else:
            print("⚠️ Warning: Refetched bio does not match. It might take a moment to update or caching is active.")
    except Exception as e:
        print(f"⚠️ Verification fetch encountered an issue: {e}")

if __name__ == "__main__":
    main()
