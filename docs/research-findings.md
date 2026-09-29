# Tinder Integration Research Findings

**Date:** 2026-09-29 · **Method:** live tests against a fresh, authenticated account (authorized — Dinesh's own account), web-client traffic observation, and endpoint probing from a residential IP.
**Rule of this document:** every claim is labeled. Nothing is assumed.

Legend: ✅ verified live · 👀 observed but not fully isolated · ⛔ not tested / blocked · 🚫 deliberately not done

---

## 1. The token

| Question | Finding | Status |
|---|---|---|
| What is it? | 36-char UUID stored in `localStorage["TinderWeb/APIToken"]` on `tinder.com`; sent as `X-Auth-Token` header to `api.gotinder.com` | ✅ |
| Does basic auth work with just token + mobile UA? | Yes: `GET /v2/profile?include=account,user` returned 200 with bio/photos/interests/prompts/descriptors | ✅ |
| Does it rotate during normal web use? | No change observed across ~15 min of page use including ≥6 web-client calls to `/v3/auth/login` | 👀 |
| Does logout invalidate it? | Not tested (would have destroyed the session mid-research) | 🚫 |
| Can it be revoked server-side while the browser still holds it? | **YES — observed directly.** A token that returned 200 at 19:38 returned 401 at 19:45 with the localStorage value unchanged. Cause (below): the account was locked by Tinder's suspicious-activity system | ✅ |
| Practical lifetime on a healthy account? | Unknown beyond 15 min. **We claim nothing unverified** — the app treats expiry as always-possible and handles it gracefully | 👀 |

**Design consequence:** "paste once and it works forever" is NOT supportable. Wingman treats the token
as ephemeral (in-memory session, masked display, instant re-connect flow, friendly expiry errors).

## 2. Anti-automation / account safety (the big one)

**Observed:** a brand-new account, created through the **web signup flow with scripted form-filling,
6 photos injected programmatically (DataTransfer), and API calls from curl within minutes** was locked
by Tinder's "suspicious activity" system within ~30 minutes:

- First symptom: `/v2/matches` and `/recs/core` returned 401 while `/v2/profile` still returned 200
  (partial capability gating).
- Then the web app showed *“Your Selfie is under review”* → *“Your account has been temporarily locked
  due to suspicious activity”* with profile hidden and a mandatory **video selfie** to unlock
  (“if you don't, your account will be closed”).
- Simultaneously the API token was revoked server-side (see §1).

**Likely triggers (not isolated — a combination):** non-human signup pacing, programmatic photo
upload, API calls with no supporting session headers, datacenter-like request patterns.

**Design consequences baked into the product:**
1. Wingman never automates account creation or swiping.
2. Live connections are localhost-only (datacenter IPs are a known flag risk — also why the deployed
   demo physically cannot call Tinder).
3. All writes are rate-throttled and human-confirmed.
4. A locked/under-review account is detected and explained in plain words (see `/api/diagnostics`).

## 3. Endpoint capabilities observed

| Capability | Endpoint | Finding | Status |
|---|---|---|---|
| Read own profile (rich v2) | `GET /v2/profile?include=account,user` | Full: name, age, bio, photos, interests, prompts, descriptors, email, intent | ✅ works |
| Read own matches | `GET /v2/matches?count=60` (paged) | Returns 401 while account is gated; standard endpoint used by the web client | ⛔ blocked by account lock |
| Read messages | `GET /v2/matches/{id}/messages` | Same gating; endpoint verified from web-client traffic + vendored library | ⛔ blocked |
| Person profile | `GET /user/{id}` | Not reached live | ⛔ |
| Write bio | `POST /profile {bio}` | **Verified working on 2026-06 run** (previous session, same code path); today not re-tested to avoid post-lock writes | ✅ (prior session) |
| Write prompts | `POST /v2/profile/user {selected_prompts}` | Verified in prior session | ✅ (prior session) |
| Send message | `POST /user/matches/{id} {message}` | Implemented; NOT live-tested today (would message a real person) | ⛔ |
| Right swipe | `POST /like/{user_id}` | NOT tested — blocked + deliberately deferred | ⛔ |
| Left swipe | `POST /pass/{user_id}` | NOT tested | ⛔ |
| Meta/rate-limits | `GET /v2/meta?locale=en` | 404 from our client even though web client calls it — likely needs the full web header set (session headers) | 👀 |

**Header observations:** `/v2/profile` accepts `X-Auth-Token` + a mobile User-Agent alone. Other
endpoints appear stricter (the web client carries a larger header set: platform, app-version,
session ids). The web client re-authenticates via `POST /v3/auth/login` repeatedly during a session.

## 4. Swipes — decision

**Not enabled in the product.** Endpoint knowledge exists, but zero live verification was possible
(account gated), and account safety (§2) argues for extreme conservatism. The methods exist in
`server/tinder_api.py` with `confirm` gates and **no API route calls them** — enabling requires:
(1) unlocked account, (2) reliability testing incl. duplicate/rate behavior, (3) a ToS review,
(4) explicit product sign-off.

## 5. Terms-of-service notes

Tinder's terms prohibit scraping and automation of their service. Wingman's position:
- operates on the **user's own account, at user pace, with human-confirmed actions**
- reads what the user's own session can read; drafts rather than automates
- swiping/bulk actions remain off
- users are told the tool is independent and should respect Tinder's terms (footer + docs)

This is honest usage of one's own session — but bulk/automated use would cross the line, so the
product is deliberately built to make bulk actions impossible (single-call locks, confirm gates).

## 6. Timeline of this session (for the video script)

1. 19:0x — fresh account created via web signup (scripted but human-authorized)
2. 19:2x — token extracted from `localStorage["TinderWeb/APIToken"]`
3. 19:38 — `/v2/profile` 200 ✅ (token live); `/v2/matches`, `/recs/core` 401 (gated)
4. 19:40 — token fingerprint unchanged after web use → "stable so far"
5. 19:45 — same token now 401 everywhere; browser shows account locked; localStorage value unchanged → **server-side revocation**
6. 19:5x — video selfie submitted; account under review

This timeline is the factual backbone of the demo video: the "bug or feature" moment is that a
credential can die in your browser's localStorage while looking perfectly alive.
