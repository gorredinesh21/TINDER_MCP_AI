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
    
    # 1. Initialize connector
    print("\n🔗 [1/5] Connecting to live Tinder account...")
    try:
        conn = TinderConnector()
    except Exception as e:
        print(f"❌ Failed to connect to Tinder: {e}")
        return

    # 2. Extract profile
    print("\n📥 [2/5] Extracting your live profile...")
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

    # 3. Run local vision analysis on profile photos
    print("\n👁️ [3/5] Running local vision analysis on profile photos...")
    try:
        from vision import TinderVision
        vision = TinderVision()
        me.photos = vision.describe_photos(me.photos)
        print("✅ Visual analysis completed!")
        
        # Save analyzed profile snapshot containing vision descriptions
        analyzed_filename = f"analyzed_profile_{safe_name}_{timestamp}.json"
        with open(analyzed_filename, "w", encoding="utf-8") as f:
            f.write(me.model_dump_json(indent=2))
        print(f"💾 Saved analyzed profile snapshot (with vision descriptions) to: {analyzed_filename}")
    except Exception as e:
        print(f"⚠️ Vision analysis encountered a warning (continuing without vision): {e}")

    # 4. Optimize via Brain
    print("\n🧠 [4/5] Analyzing and optimizing profile via DatingCoach Brain...")
    print(f"⚙️ Using LLM backend: {os.getenv('LLM_BACKEND', 'ollama')}")
    print(f"🤖 Model: {os.getenv('HF_MODEL', 'Qwen/Qwen2.5-72B-Instruct')}")
    
    coach = DatingCoach()
    try:
        result = coach.improve_profile(me)
        report, improved = result.report, result.improved_profile
    except Exception as e:
        print(f"❌ Brain analysis failed: {e}")
        return

    print("\n==================================================================")
    print("🏆      TINDER PROFILE AI COACH ASSESSMENT REPORT SUMMARY      🏆")
    print("==================================================================")
    print(f"📊 Overall Score: {report.overall_score}/100")
    print(f"📸 Photo Score:   {report.photo_score}/100")
    print(f"📝 Bio Score:     {report.bio_score}/100")
    print("------------------------------------------------------------------")
    print("\n💡 OVERALL SUMMARY:")
    print(report.summary)
    
    print("\n❌ DETECTED PROFILE GAPS:")
    for gap in report.gaps:
        print(f"  • {gap}")
        
    print("\n📸 PHOTO-BY-PHOTO ASSESSMENT:")
    for idx, pa in enumerate(report.photo_assessments, 1):
        status = "✅ KEEP" if pa.keep else "❌ DROP"
        slot_str = f"Slot {pa.suggested_slot}" if pa.suggested_slot else "N/A"
        print(f"\nPhoto {idx} [ID: {pa.photo_id}] -> {status} (Recommended Placement: {slot_str})")
        print("  Strengths:")
        for s in pa.strengths:
            print(f"    + {s}")
        print("  Issues/Recommendations:")
        for i in pa.issues:
            print(f"    - {i}")
            
    print("\n✨ RECOMMENDED PHOTO LINEUP ORDER:")
    print(" -> ".join(report.recommended_photo_order))
    
    print("\n💬 SUGGESTED PROMPT ANSWER REWRITES:")
    for idx, rewrite in enumerate(report.improved_prompts, 1):
        print(f"\nPrompt {idx}: \"{rewrite.get('q')}\"")
        print(f"  👉 Rewrite: \"{rewrite.get('a')}\"")
        
    print("\n✍️ --- HIGH-EFFORT BIO VARIANTS GENERATED ---")
    for idx, variant in enumerate(report.bio_variants, 1):
        print(f"\nVariant {idx} [{variant.tone}]:")
        print(f"  \"{variant.text}\"")
        print(f"  Rationale: {variant.rationale}")

    # Save a premium markdown report
    report_filename = "TINDER_COACH_REPORT.md"
    try:
        with open(report_filename, "w", encoding="utf-8") as f:
            f.write("# 🏆 Tinder Profile AI Coach Assessment Report 🏆\n\n")
            f.write(f"## 📊 Profile Optimization Scorecard\n")
            f.write(f"- **Overall Profile Score:** {report.overall_score}/100\n")
            f.write(f"- **Photo Score:** {report.photo_score}/100\n")
            f.write(f"- **Bio Score:** {report.bio_score}/100\n\n")
            
            f.write("## 💡 Executive Summary\n")
            f.write(f"{report.summary}\n\n")
            
            f.write("## ❌ Profile Gaps & Checklist\n")
            for gap in report.gaps:
                f.write(f"- [ ] {gap}\n")
            f.write("\n")
            
            f.write("## 📸 Photo-by-Photo Rubric Assessment\n\n")
            for idx, pa in enumerate(report.photo_assessments, 1):
                status = "✅ **KEEP**" if pa.keep else "❌ **DROP**"
                slot_str = f"Slot {pa.suggested_slot}" if pa.suggested_slot else "N/A (Drop)"
                f.write(f"### Photo {idx} - {status}\n")
                f.write(f"- **Recommended Placement:** {slot_str}\n")
                f.write(f"- **Photo ID:** `{pa.photo_id}`\n")
                matching_photos = [p for p in me.photos if p.id == pa.photo_id]
                if matching_photos and matching_photos[0].url:
                    f.write(f"- **Secure CDN URL:** [Link to Photo]({matching_photos[0].url})\n")
                
                f.write("- **Strengths:**\n")
                for s in pa.strengths:
                    f.write(f"  - {s}\n")
                f.write("- **Issues & Areas to Improve:**\n")
                for i in pa.issues:
                    f.write(f"  - {i}\n")
                f.write("\n")
                
            f.write("## ✨ Recommended Photo Lineup Order\n")
            f.write(" -> ".join([f"`{pid}`" for pid in report.recommended_photo_order]) + "\n\n")
            
            f.write("## 💬 Suggested Prompt Answer Rewrites\n\n")
            for idx, rewrite in enumerate(report.improved_prompts, 1):
                f.write(f"### Prompt {idx}: \"{rewrite.get('q')}\"\n")
                f.write(f"> **Rewrite:** \"{rewrite.get('a')}\"\n\n")
                
            f.write("## ✍️ Generated High-Effort Bio Variants\n\n")
            for idx, variant in enumerate(report.bio_variants, 1):
                f.write(f"### Variant {idx} [{variant.tone}]\n")
                f.write(f"**Bio Text:**\n")
                f.write(f"> \"{variant.text}\"\n\n")
                f.write(f"**Rationale:** {variant.rationale}\n\n")
                
        print(f"💾 Saved premium visual report card to: {report_filename}")
    except Exception as e:
        print(f"⚠️ Failed to write markdown report: {e}")

    # We will choose the first variant (best/top one)
    if not report.bio_variants:
        print("❌ No bio variants returned by the model. Aborting update.")
        return
        
    best_bio = report.bio_variants[0].text
    print(f"\n🎯 Selected Best Bio Variant: {best_bio!r}")

    # 5. Write back to Tinder
    print("\n📤 [5/5] Writing updated bio back to live Tinder profile...")
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
