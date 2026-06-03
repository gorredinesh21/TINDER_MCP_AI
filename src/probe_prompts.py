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

    if "--create" in args:
        i = args.index("--create")
        qid, ans = args[i + 1], args[i + 2]
        print(f"\n=== CREATING PROMPT  question_id={qid} ===")
        try:
            print(dump(conn.create_prompt(qid, ans, confirm=True)))
            print("→ now re-checking your prompts:")
            print(dump(conn._raw_user_prompts()))
        except Exception as e:
            print("create failed:", e)


if __name__ == "__main__":
    main()
