# Wingman AI 🔥

**Your Tinder. Smarter.** — a production-grade AI Tinder assistant built on your own account:
profile analysis, bio & prompt rewrites, photo feedback (real vision), conversation coaching,
review-then-send messaging, and honest insights. Powered by **Google Cloud Gemini** (Vertex AI).

<p>
<img alt="status" src="https://img.shields.io/badge/AI-Gemini%20on%20Vertex%20AI-FD267D"> 
<img alt="status" src="https://img.shields.io/badge/tests-11%20passing-0FA36B">
<img alt="status" src="https://img.shields.io/badge/live%20mode-localhost%20only-FF6036">
</p>

## What it does

| Feature | What you get |
|---|---|
| 🔍 Profile analysis | Scores + reasoning, gaps to close, all from your real profile |
| ✍️ Bio & prompt rewrites | 2–3 tone variants built from your true details; publish with one confirmed tap |
| 🖼️ Photo vision | Gemini looks at each photo — framing, background, outfit — and ranks them |
| 💬 Conversation coach | Per-chat tone/engagement read + reply drafts in the tone you pick |
| 📤 Review-then-send | Draft → your edit → your Send → your confirm. The AI physically cannot act (code-level separation) |
| 📊 Insights | Match stats, chat balance, shared interests — from your real history |
| 🤖 Assistant | "Which of my chats are fading?" — answered from your data |

**Deliberately NOT included:** swiping. Researched, implemented, not enabled — see the
[honest capability table](docs/research-findings.md).

## Quick start (local — live Tinder mode)

```bash
git clone git@github.com:gorredinesh21/TINDER_MCP_AI.git && cd TINDER_MCP_AI
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python app.py            # → http://127.0.0.1:8000
```

The AI layer authenticates with your `gcloud` login (Vertex AI) — or set `GEMINI_API_KEY`
(AI Studio) as a fallback. Then open the app, follow the built-in
**[Connect guide](http://127.0.0.1:8000/guide)** to copy your token from tinder.com, and paste it in.

No Tinder account handy? Click **Try the demo** — the full product runs on sample data.

## Architecture

```
Frontend (web/ — vanilla JS, zero build step)
  ↓ JSON
FastAPI backend (app.py + server/)
  ├── routes.py     — API surface, sessions, friendly errors
  ├── session.py    — token in memory ONLY · HttpOnly cookie · 2h idle TTL
  ├── tinder_api.py — the only module that talks to Tinder (writes need confirm=True)
  ├── coach.py      — AI orchestration (prompts + validation, no network rights)
  └── gemini.py     — the only module that talks to Google Cloud (text + vision)
```

Grew out of an MCP prototype — the clean tool boundary stayed, MCP became an implementation detail.

## Safety model

- **Token:** pasted by the user, held in process memory, never persisted/logged/returned;
  masked fingerprint display; instant disconnect; auto-expiry.
- **Actions:** every write (bio/prompts/message) requires an explicit user confirmation; the AI
  module cannot import the Tinder module — it can draft, never act.
- **Deployment:** the hosted instance runs in demo-only mode (`ENV=cloud`) — datacenter IPs get
  accounts flagged, so live mode is localhost-only by design.

## Docs

- [Research findings](docs/research-findings.md) — what's verified vs blocked vs not enabled, with live evidence
- [Video script](docs/video-script.md) — 10-scene product demo (the "bug or feature" story)
- In-app: full documentation at `/docs`, token guide at `/guide`, FAQ on the landing page

## Tests

```bash
python -m pytest tests/ -q     # 11 offline tests — no network, no keys, no Tinder
```

---

*Independent project, not affiliated with Tinder. Use with your own account and within Tinder's terms.*
