# Tinder AI Coach

AI that **standardizes a dating profile** and **drafts messages** using Claude + a
research-backed knowledge pack tuned for the Indian market.

> **Design stance (read this).** The AI optimizes *your own* profile fully, and it
> *drafts* messages — but **you send them**. It is deliberately not built to silently
> auto-message your matches: that deceives people who didn't consent to a bot, and
> automating actions against Tinder gets accounts banned. See `knowledge/dating_profile_kb.md` §5.

## Architecture

```
CONNECTOR (replaceable)            AI BRAIN (the value — this repo)
  tinder.py + X-Auth-Token   ──▶   coach.py + knowledge/dating_profile_kb.md
  (or manual JSON paste)            • standardize_profile() → scores, bio rewrites, photo plan
        produces clean JSON         • draft_replies()       → opener/reply options (you send)
        (see src/schema.py)
                                    LLM backend is pluggable (src/llm.py):
                                      • HF Inference API   OR   • local Ollama
```

The brain only ever sees the clean `Profile` / `Match` objects in [src/schema.py](src/schema.py),
and talks to whatever LLM you pick via LangChain ([src/llm.py](src/llm.py)). Two decouplings:
the **connector** is swappable (Tinder's API is fragile) and the **LLM** is swappable
(HF token vs. local) — neither forces a rewrite of the brain.

## Pick your LLM backend (two options, no Anthropic)

| | Option A — Hugging Face API | Option B — Local (Ollama) |
|---|---|---|
| Needs | `HUGGINGFACEHUB_API_TOKEN` | Ollama installed + a model pulled |
| Runs on | HF's servers | your machine |
| Cost | HF free tier / your plan | free |
| Set in `.env` | `LLM_BACKEND=hf` | `LLM_BACKEND=ollama` |

## Setup

```powershell
cd "tinder-ai-coach"
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env        # choose LLM_BACKEND and fill the matching section
```

**Option A (HF):** put your token in `.env`, keep `LLM_BACKEND=hf`. Change `HF_MODEL` to any
instruct model your token can call (default `Qwen/Qwen2.5-7B-Instruct`).

**Option B (Ollama):** install from [ollama.com](https://ollama.com), then `ollama pull llama3.1`
(or `qwen2.5`/`mistral`), set `LLM_BACKEND=ollama`. No token, fully local.

## Run the demo (no Tinder needed — uses mock data)

```powershell
python src\demo.py            # standardize a sample profile + draft openers
python src\demo.py profile    # just the profile standardizer
python src\demo.py reply      # just the message drafter
```

## What it does

- **Profile standardizer** — scores photos & bio against the rubric, rewrites the bio into
  2-3 honest variants (never invents facts), assesses/ranks every photo (vision-capable if you
  pass real image paths/urls), suggests prompts, and lists concrete gaps.
- **Message drafter** — reads a match's bio/photos/chat and produces 2-3 opener/reply options
  of different tones with a one-line "why", plus a safety/pacing note. **You** pick and send.

## The knowledge pack (the "teach the AI" step)

[knowledge/dating_profile_kb.md](knowledge/dating_profile_kb.md) is research distilled into a
rubric the model applies and scores against: photo rules (solo-first, ≤1 selfie, 4-6 photos),
bio rules (100-300 chars, specific, ends with a hook), India market context (safety-first
audience, intentional-dating shift), opener rules (personalized, 5-15 words, no "hey"), and
always-on safety guardrails. Edit this file to retune behavior — no code changes needed.

## Connect live Tinder ([src/connector.py](src/connector.py))

The connector turns your real account into `Profile`/`Match` objects via the vendored
[rednit-team/tinder.py](https://github.com/rednit-team/tinder.py) library
(Apache-2.0, in [src/vendor/tinder](src/vendor/tinder) — vendored because its PyPI package
ships no importable code). **Reading is automated; sending is not** — `send_message()` exists
only for you to call by hand after reviewing a draft.

### Token guide (one-time)
1. Log in at **tinder.com** in your browser.
2. Open **DevTools → Network**, filter for `api.gotinder.com`.
3. Click any request → **Request Headers** → copy the value of **`X-Auth-Token`**.
4. Paste it into `.env` as `TINDER_X_AUTH_TOKEN=...`.

Using a token from your real session avoids automated login/CAPTCHA — the #1 ban trigger.

### Run it live
```powershell
python src\connect_demo.py
```
Pulls your profile + most recent match, standardizes the profile, and **drafts** an opener.
To send a draft you've chosen, you do it yourself:
```python
from connector import TinderConnector
TinderConnector().send_message("<match_id>", "<your edited text>")
```

### ⚠️ Two hard rules (from how these libraries actually behave)
- **Run on your own machine / home network.** Requests from cloud IPs (AWS, etc.) get accounts
  flagged and blocked.
- **This is unofficial and violates Tinder's ToS** — endpoints can break without notice and
  automation carries a real ban risk. Keeping sends human-in-the-loop is the safer (and honest) path.

## Models & notes

- Structured output uses prompt-and-parse (ask for JSON matching the schema, then validate with
  Pydantic) so it works on any instruct model regardless of function-calling support.
- Open text models aren't multimodal, so photos are judged from `declared_type` + caption. For
  real image analysis, use a multimodal model (Ollama `llava`, or an HF vision model) — a later step.
- Bigger models (e.g. `Qwen2.5-32B`, `Llama-3.3-70B`) follow the rubric and JSON format more
  reliably than tiny ones; if parsing fails, try a larger model or lower `LLM_TEMPERATURE`.
