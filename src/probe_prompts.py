"""
Live Tinder PROMPTS discovery — RUN THIS ON YOUR PERSONAL LAPTOP.

Tinder's prompt-catalog + write endpoints aren't documented, so this script hits the live API
with your token to (1) show your current prompts, (2) probe every candidate "available prompts"
endpoint and print what each returns, (3) show the parsed question catalog, and optionally
(4) actually create a prompt. Paste the output back so we lock in the right endpoint, then wire
it into the dashboard + AI.

Needs a working token and an unblocked network (your home laptop, not the office one).

    python src/probe_prompts.py                         # token from .env (TINDER_X_AUTH_TOKEN)
    python src/probe_prompts.py <X-Auth-Token>          # or pass the token directly
    python src/probe_prompts.py <token> --create <question_id> "<your answer>"
"""
import json
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")
from connector import TinderConnector


def dump(obj, limit=1800):
    s = json.dumps(obj, indent=2, ensure_ascii=False)
    return s if len(s) <= limit else s[:limit] + "\n… (truncated)"


def write_test(conn, target_id, answer):
    """Try several endpoint/payload shapes to set prompt `target_id`'s answer, re-reading after
    each to see which one actually PERSISTS. This is how we find the real prompt-write path.
    NOTE: this changes the live answer of that prompt — set it back afterward if you like."""
    import requests
    current = conn._raw_user_prompts()
    full, found = [], False
    for p in current:
        e = {"id": p.get("id"), "answer_text": p.get("answer_text")}
        if p.get("id") == target_id:
            e["answer_text"] = answer; found = True
        full.append(e)
    if not found:
        full.append({"id": target_id, "answer_text": answer})

    candidates = [
        # WORKING endpoint & payload discovered!
        ("POST", "https://api.gotinder.com/v2/profile/user?locale=en", {"selected_prompts": [{"id": target_id, "answer_text": answer}]}),
        # NEW top hypothesis: writes nested under "user" (how descriptor writes are shaped)
        ("POST", "https://api.gotinder.com/v2/profile", {"user": {"user_prompts": {"prompts": full}}}),
        ("POST", "https://api.gotinder.com/profile",    {"user": {"user_prompts": {"prompts": full}}}),
        ("POST", "https://api.gotinder.com/v2/profile?locale=en", {"user": {"user_prompts": {"prompts": full}}}),
        # already-tried shapes (kept for completeness)
        ("POST", "https://api.gotinder.com/v2/profile", {"user_prompts": {"prompts": full}}),
        ("POST", "https://api.gotinder.com/v2/profile", {"prompts": full}),
    ]
    print(f"\n=== WRITE TEST on {target_id} (target answer: {answer!r}) ===")
    for method, url, body in candidates:
        try:
            r = requests.request(method, url, headers=conn._api_headers(), json=body, timeout=15)
            after = conn._raw_user_prompts()
            got = next((x.get("answer_text") for x in after if x.get("id") == target_id), None)
            tag = "✅ PERSISTED" if got == answer else "✗ no change"
            print(f"[{r.status_code}] {method} {url}  payload_keys={list(body)}  -> answer now {got!r}  {tag}")
            if got == answer:
                print(f"   >>> THIS is the working write path: {method} {url}  body={list(body)}")
                return
        except Exception as e:
            print(f"[ERR] {method} {url}: {e}")
    print("None persisted — the prompt write needs a different endpoint (capture it from tinder.com DevTools).")


def main() -> None:
    args = list(sys.argv[1:])
    token = args.pop(0) if args and not args[0].startswith("--") else None
    conn = TinderConnector(auth_token=token)  # falls back to .env if token is None

    print("=== YOUR CURRENT PROMPTS ===")
    try:
        cur = conn._raw_user_prompts()
        print(dump(cur))
        print(f"({len(cur)} prompt(s) currently on your profile)")
    except Exception as e:
        print("error:", e)

    print("\n=== RAW user_prompts (ALL fields — looking for position / instance id we may be dropping) ===")
    try:
        import requests
        r = requests.get("https://api.gotinder.com/v2/profile?locale=en&include=user",
                         headers=conn._api_headers(), timeout=15)
        print(dump(r.json().get("data", {}).get("user", {}).get("user_prompts", {}), 2000))
    except Exception as e:
        print("error:", e)

    print("\n=== AVAILABLE-PROMPTS ENDPOINT PROBE ===")
    raw = conn.fetch_available_prompts()
    for url, res in raw.items():
        status = res.get("status", res.get("error"))
        print(f"\n[{status}] {url}")
        if "body" in res:
            print(dump(res["body"], 1200))

    print("\n=== PARSED QUESTION CATALOG (best-effort) ===")
    catalog = conn.parse_available_prompts(raw)
    print(dump(catalog[:40]))
    print(f"({len(catalog)} questions parsed)")

    if "--write-test" in args:
        i = args.index("--write-test")
        write_test(conn, args[i + 1], args[i + 2])

    if "--create" in args:
        i = args.index("--create")
        qid, ans = args[i + 1], args[i + 2]
        print(f"\n=== CREATING PROMPT  id={qid} ===")
        try:
            print(dump(conn.create_prompt(qid, ans, confirm=True)))
            print("→ now re-checking your prompts:")
            print(dump(conn._raw_user_prompts()))
        except Exception as e:
            print("create failed:", e)


if __name__ == "__main__":
    main()
