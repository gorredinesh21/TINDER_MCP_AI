# HANDOFF LOG

Append a new entry at the TOP each session (newest first). This is the cross-device
communication channel between agents — see AGENTS.md. Keep entries short and factual.

Format:
```
## YYYY-MM-DD — <device/agent>
- did: <what changed>
- next: <what the other side should pick up>
- blocked/notes: <anything needing a human or a decision>
```

---

## 2026-06-01 — desktop / Claude Code
- did: Initial repo. Brain (HF/Ollama via LangChain) verified working on HF (Qwen2.5-7B).
  Tinder connector built (vendored tinder.py) — maps live account to Profile/Match.
  Added offline tests + CI. Removed the dead glassBead tinder-mcp-server.
- next: First LIVE run on a personal laptop: put real TINDER_X_AUTH_TOKEN + HF token in `.env`,
  run `python src/connect_demo.py`, and report back here whether the live Tinder fetch works in 2026
  (the connector code is verified but the live call is untested).
- blocked/notes: HF token used during dev was exposed in chat — ROTATE it. Live Tinder must run
  on home network (cloud IPs get blocked). AI must never auto-send (see AGENTS.md rule 1).
