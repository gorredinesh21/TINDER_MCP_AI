# Wingman AI — Product Demo Video Script

**Format:** ~4–5 minute demo/build-in-public style video · English narration · screen recording
**Golden rule:** the real token is NEVER visible on camera. Every credential shot uses a redacted
overlay or the masked fingerprint (`bff5…0258`).

---

## Scene 1 — Hook (0:00–0:15)

> **"I found a bug on Tinder. I don't know whether it's a bug or a feature."**

*On screen: the Wingman AI logo fading in over a blurred Tinder tab.*

> "It's about the credential that keeps you logged in. It can die — get revoked server-side —
> while sitting in your browser, looking perfectly alive. Let me show you the whole thing, and the
> AI assistant I built around it."

## Scene 2 — Where the credential lives (0:15–0:50)

*On screen: tinder.com open in a controlled test account, logged in.*

> "This is my own test account. When you log into Tinder on the web, your browser stores a
> 36-character login token. Right here —"
>
> *Open DevTools → Application → Local Storage → `TinderWeb/APIToken` (value blurred).*
>
> "— under Local Storage, key `TinderWeb/APIToken`. This one value is the key to your whole
> account. Everything I'm about to show you uses exactly this, on my own account, at my own pace."

## Scene 3 — The product (0:50–1:30)

*On screen: localhost Wingman AI landing page → Connect screen.*

> "This is Wingman AI — my AI Tinder assistant. The connection flow is deliberately simple:
> you copy that token yourself, and paste it here."
>
> *Paste (pasted value shown as •••), press Connect. Green "Connected as …" appears.*
>
> "Notice what just happened: the app verified the credential against Tinder, created a session,
> and the token now lives in server memory only — masked in the UI, never written to disk.
> Disconnect, and it's gone."

## Scene 4 — The discovery (1:30–2:20)

*On screen: split view — Wingman's Connection Health panel + the timeline from research.*

> "Here's the bug-or-feature part. While building this, I profiled the token's behavior:
> at 7:38 PM it worked perfectly. At 7:45 PM — same token, same request — 401. Unauthorized.
>
> I checked the browser: localStorage still held the same value. Tinder had revoked it
> server-side, and the browser had no idea. Any tool that cached that token would keep
> sending a dead credential.
>
> And there's a second layer: fresh accounts that act even slightly non-human get locked behind
> a video-selfie review — my test account did exactly that mid-build. So I designed Wingman
> around fragile credentials: session-only storage, instant reconnect, and honest error
> messages. No tool should pretend a token is forever. I only claim what I actually verified."

## Scene 5 — AI reads your profile (2:20–3:00)

*On screen: Profile tab → Analyze.*

> "Now the assistant itself. Gemini on Google Cloud reads my real profile — bio, prompts,
> photos. Actual vision: it looks at each photo and judges framing, background, outfit."
>
> *Show scores appearing, then scroll through bio variants and photo feedback.*
>
> "Scores, three rewritten bios in different tones, sharper prompt answers, photo order —
> every suggestion built from my real data, nothing fabricated."

## Scene 6 — Publishing is a human action (3:00–3:25)

*On screen: "Use this bio →" → confirmation modal → publish.*

> "Publishing is always two steps: the AI proposes, I confirm. The AI layer literally cannot
> send anything — in the code, drafting and acting are separate modules with no import between
> them."

## Scene 7 — Conversations (3:25–4:05)

*On screen: demo account conversations (sample data OK here) → pick a chat → tone: funny → Analyze.*

> "For chats: Wingman reads a conversation, tells me the tone, whether it's fading, what topics
> are alive — and drafts replies in the tone I pick. I edit inline, I press Send, I confirm.
> Draft, review, send — in that order, always."

## Scene 8 — The bigger idea (4:05–4:30)

> "Zoom out: this is a dating account becoming an API you can reason about — profile as data,
> conversations as context, an AI wingman reading both. The interesting version of this future
> is the safe one: your account, your token in memory only, your finger on every send button."

## Scene 9 — Close (4:30–4:50)

*On screen: landing page hero — "Your Tinder. Smarter."*

> "Wingman AI. Built as a real product — onboarding a normal human can finish, honest docs,
> open research log. Link's in the description. Swipe responsibly."

---

## Production notes

- **Redaction:** blur/overlay ANY visible token value; use `bff5…0258`-style masks in shots.
- **Accounts:** use the authorized test account only; sample-data demo mode is fine for Scene 7
  if no real conversations exist.
- **B-roll:** the timeline graphic from Scene 4 can be a simple card stack built in the Wingman UI
  itself (Connection Health panel).
- Do not show other people's identifiable photos beyond what's necessary; prefer demo data on camera.
- CTA: GitHub link + "run it locally in 2 minutes" guide.
