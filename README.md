# 🔥 Tinder AI Coach

An AI that **optimizes your dating profile** and, with one click, **publishes the improvements
live to Tinder** — a sharper bio, punchier prompt answers, a photo plan, and a clear list of
what's holding your profile back. It runs as a small **local web dashboard** so you don't have to
touch any code.

It's tuned for the **Indian dating market** and uses open/affordable LLMs — **Hugging Face**,
**Google Gemini**, or a **local model via Ollama** — your choice. No OpenAI/Anthropic keys needed.

> ### ⚖️ How it works (and a promise)
> The AI fully optimizes **your own** profile, but it is **human-in-the-loop**: nothing is published
> to Tinder until **you** click a button. It deliberately does **not** auto-message your matches —
> that deceives people and gets accounts banned. The tool reads your profile and *drafts*; **you decide
> and publish.** Using Tinder's private API is against their Terms of Service and carries a ban risk —
> use it on your own account, at your own discretion.

---

## Table of contents
1. [What you get](#what-you-get)
2. [Prerequisites](#prerequisites)
3. [Step-by-step setup](#step-by-step-setup)
4. [Getting your API keys](#getting-your-api-keys)
   - [Hugging Face token](#a-hugging-face-token-text-brain--recommended)
   - [Google Gemini key](#b-google-gemini-key-text-brain-andor-photo-vision)
   - [Local AI with Ollama](#c-local-ai-with-ollama-no-key-fully-free)
5. [Getting your Tinder X-Auth-Token](#getting-your-tinder-x-auth-token)
6. [Using the dashboard](#using-the-dashboard)
7. [Photo (vision) analysis](#photo-vision-analysis)
8. [Command-line scripts (optional)](#command-line-scripts-optional)
9. [Configuration reference (.env)](#configuration-reference-env)
10. [Troubleshooting](#troubleshooting)
11. [How it's built](#how-its-built)
12. [Privacy & safety](#privacy--safety)

---

## What you get
- **Profile analysis** — scores your photos and bio, summarizes strengths/weaknesses.
- **Bio rewrites** — 2–3 distinct, specific bios built only from your real details (never invented).
- **Prompt suggestions** — the AI picks the best questions from Tinder's live prompt catalog and writes
  vivid answers, which you can edit and **publish live**.
- **Photo plan** — keep/drop + ordering advice; with vision enabled, it actually *looks* at your photos.
- **Habits & "what's missing"** — concrete gaps (no full-body shot, intent mismatch, not verified, …).
- **One-click publishing** — push the new bio and prompts straight to your Tinder profile.

---

## Prerequisites
- **Python 3.10+** (3.12 recommended) — <https://www.python.org/downloads/>
- **Git** — <https://git-scm.com/downloads>
- **At least one AI backend** (any one is enough):
  - a **Hugging Face** token (free), **or**
  - a **Google Gemini** key (free), **or**
  - **Ollama** installed locally (free, no key) — <https://ollama.com>
- A **Tinder account** + your **X-Auth-Token** (instructions below).
- Run on your **own machine / home network** — corporate networks often block Tinder's API and the
  photo CDN.

---

## Step-by-step setup

```bash
# 1. Clone the repo
git clone https://github.com/gorredinesh21/TINDER_MCP_AI.git
cd TINDER_MCP_AI

# 2. Create and activate a virtual environment
python -m venv .venv
#   Windows (PowerShell):
.\.venv\Scripts\Activate.ps1
#   macOS / Linux:
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create your .env from the template
cp .env.example .env          # Windows PowerShell: copy .env.example .env

# 5. Put at least one API key in .env (see "Getting your API keys" below)
#    e.g. open .env and paste your HUGGINGFACEHUB_API_TOKEN

# 6. Start the dashboard
python app.py
```

Then open **<http://127.0.0.1:8000>** in your browser. That's it.

> You can also set/switch your keys and models **from inside the dashboard** (Step ①) — it writes them
> to `.env` for you, so editing the file by hand is optional.

---

## Getting your API keys

You only need **one** text backend. Here's how to get each.

### A. Hugging Face token (text brain — recommended)
Gives you access to big, high-quality models (e.g. `Qwen/Qwen2.5-72B-Instruct`) for free.
1. Create a free account at <https://huggingface.co/join>.
2. Go to <https://huggingface.co/settings/tokens>.
3. Click **Create new token** → type **Read** → create it.
4. Copy the token (starts with `hf_`).
5. Paste it into the dashboard's **Step ① "Connect your AI engine"** field and click **Save key**
   (or put it in `.env` as `HUGGINGFACEHUB_API_TOKEN=hf_...`).
- Default model is `Qwen/Qwen2.5-72B-Instruct`. You can change `HF_MODEL` in `.env` (it must be a model
  the free Inference providers serve — `Qwen/Qwen2.5-72B-Instruct` and `meta-llama/Llama-3.3-70B-Instruct`
  are known to work).

### B. Google Gemini key (text brain and/or photo vision)
Fast and great for vision (it can actually look at your photos via the cloud).
1. Go to <https://aistudio.google.com/apikey> and sign in with a Google account.
2. Click **Create API key** → copy it (starts with `AIza...`).
3. Paste it into the dashboard's Step ① Gemini field (or `.env` as `GEMINI_API_KEY=AIza...`).
4. To use Gemini as the **text** brain, set `LLM_BACKEND=gemini`; to use it only for **photos**, set
   `VISION_BACKEND=gemini`.

### C. Local AI with Ollama (no key, fully free)
Runs models entirely on your machine — no key, no per-call cost, full privacy.
1. Install Ollama from <https://ollama.com/download> (Windows/macOS/Linux).
2. Pull a text model and/or a vision model:
   ```bash
   ollama pull llama3.1        # text brain
   ollama pull moondream       # photo vision (tiny, ~830MB) — or: ollama pull llava (~4.7GB)
   ```
3. Set `LLM_BACKEND=ollama` (and/or `VISION_BACKEND=ollama`) in `.env`.
- **Easiest path:** the dashboard's **Step ③** has a **"Set up local AI"** button that installs Ollama
  and pulls the vision model for you, streaming progress live.

---

## Getting your Tinder X-Auth-Token

This is what lets the app read and update *your* profile. It's tied to your logged-in session and
**changes/expires regularly**, so you'll usually grab a fresh one each time you use the app. You paste
it into the dashboard (it's used in memory for that request and **never stored**).

1. Open <https://tinder.com> in your browser (Chrome/Edge/Firefox) and **log in**.
2. Press **F12** to open Developer Tools, and click the **Network** tab.
3. In the Network filter box, type **`api.gotinder.com`**.
4. Click around Tinder (open your profile) so requests appear in the list.
5. Click any request to `api.gotinder.com` → open the **Headers** section → find **Request Headers**.
6. Copy the value of the **`X-Auth-Token`** header (a long string like `2afa0896-d373-...`).
7. Paste it into the dashboard's **Step ② "Analyze your profile"** field.

> Tip: if analysis suddenly fails with an auth error, your token expired — just grab a fresh one.

---

## Using the dashboard

1. **① Connect your AI engine** — paste your HF or Gemini key (or pick Ollama), choose your text/vision
   engines. Status turns green when connected.
2. **② Analyze your profile** — paste your Tinder X-Auth-Token and click **Analyze**.
   (No token yet? Click **"Try with sample data"** to see the whole thing work on a demo profile.)
3. **Review the report:**
   - **Scores** for Overall / Photos / Bio.
   - **Recommended bio** + alternatives — edit any of them, then click **"Update to Tinder 🔥"** to
     publish the one you like.
   - **Prompts** — AI-picked questions with drafted answers; swap the question, edit the answer, and
     **Publish** (Tinder allows up to 3 prompts).
   - **Photo plan**, **habits guide**, and **what's missing**.
4. Nothing goes live until you click a publish button.

---

## Photo (vision) analysis

By default the text brain reasons about your photos from metadata. To have the AI *actually see* them:
- **Gemini vision (cloud):** set `VISION_BACKEND=gemini` with a `GEMINI_API_KEY` — fast, no install.
- **Local vision (Ollama):** set `VISION_BACKEND=ollama` and install a vision model (`moondream` or
  `llava`) — free and private. Use the dashboard's **Step ③** to set it up in one click.
- Then enable the **"Also analyze my photos"** toggle in Step ②.

> Note: photo analysis needs to download your photos from Tinder's CDN (`images-ssl.gotinder.com`).
> Some office/corporate networks block this — use a home network.

---

## Command-line scripts (optional)

Prefer the terminal? With `TINDER_X_AUTH_TOKEN` set in `.env`:
- `python run_pipeline.py` — full pipeline: extract → optimize → (optionally) write back → report.
- `python src/demo.py` — runs the analyzer on the bundled sample profile (no token needed).
- `python src/improve_demo.py` — produces an improved-profile JSON from sample/extracted data.
- `python src/connect_demo.py` — live: pulls your profile + drafts a reply for a match.
- `python src/probe_prompts.py <token>` — diagnostic for the Tinder prompt endpoints (maintenance).

Run the test suite (offline, no keys/network): `pytest -q`.

---

## Configuration reference (`.env`)

| Variable | What it does |
|---|---|
| `LLM_BACKEND` | Text brain: `hf` \| `gemini` \| `ollama` |
| `LLM_TEMPERATURE` / `LLM_MAX_TOKENS` | Generation knobs |
| `HUGGINGFACEHUB_API_TOKEN` | Your HF token (for `hf`) |
| `HF_MODEL` | HF model id (default `Qwen/Qwen2.5-72B-Instruct`) |
| `GEMINI_API_KEY` | Google Gemini key (for `gemini` text and/or vision) |
| `GEMINI_MODEL` | Gemini model (default `gemini-2.5-flash`) |
| `OLLAMA_MODEL` | Local text model (for `ollama`) |
| `VISION_BACKEND` | Photo engine: `gemini` \| `ollama` |
| `VISION_MODEL` | Local vision model: `moondream` \| `llava` |
| `TINDER_X_AUTH_TOKEN` | Only for CLI scripts; the dashboard takes it per-session instead |

---

## Troubleshooting
- **"Paste your token / auth error"** → your Tinder X-Auth-Token expired; grab a fresh one.
- **HF says "no HF key"** → key not saved; re-paste in Step ① or set it in `.env`.
- **Photos don't analyze** → vision backend not configured, or your network blocks Tinder's photo CDN
  (try a home network), or the local vision model isn't pulled (Step ③).
- **Matches won't load (401)** → that token lacks matches scope; the profile/bio/prompt features still work.
- **HF model errors** → pick a model the free providers actually serve (72B Qwen or 70B Llama).
- **Port 8000 in use** → stop the other process, or change the port in `app.py`.

---

## How it's built
- **`app.py`** — FastAPI server + the dashboard (bound to `127.0.0.1`).
- **`web/index.html`** — the single-page dashboard UI.
- **`src/schema.py`** — the clean `Profile` / `Match` data contract the AI works against.
- **`src/llm.py`** — pluggable text backend (HF / Gemini / Ollama).
- **`src/vision.py`** — photo analysis (Gemini or local Ollama VLM).
- **`src/coach.py`** — the "brain": scoring, bio rewrites, prompt suggestions, message drafts.
- **`src/connector.py`** — the only part that talks to Tinder (read profile/matches, write bio/prompts).
- **`knowledge/`** — the research-backed rubric the AI follows (bio, prompts, photos, India context).
- **`data/`** — a fictional sample profile (no personal data) for the demo mode + tests.

---

## Privacy & safety
- Runs **locally** on `127.0.0.1`. Your Tinder token is used in-memory per request and **never stored
  or logged**; your API keys live only in your local `.env`.
- The AI **never** sends messages or publishes anything on its own — every write is a button you press.
- This uses Tinder's unofficial/private API, which violates Tinder's ToS and can get accounts banned.
  It's provided for personal, educational use; you accept that risk by using it.
