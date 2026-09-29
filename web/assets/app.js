/* Wingman AI — dashboard SPA */
"use strict";

const $ = (sel, el = document) => el.querySelector(sel);
const $$ = (sel, el = document) => Array.from(el.querySelectorAll(sel));
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const mdLite = (s) => esc(s)
  .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
  .replace(/(^|\n)- (.+)/g, "$1• $2")
  .replace(/\n/g, "<br>");

let session = null;          // {connected, mode, name, token_fingerprint}
let profile = null;          // my Profile
let matches = null;          // serialized matches
let analysis = null;         // last profile analysis result
const convoState = {};       // match_id -> {report, drafts, tone}

/* ================= api + feedback ================= */

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    ...opts,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  let data = null;
  try { data = await res.json(); } catch { /* non-JSON */ }
  if (!res.ok) {
    const err = (data && data.error) || {};
    const e = new Error(err.message || "Something went wrong. Please try again.");
    e.code = err.code || "unknown";
    e.status = res.status;
    throw e;
  }
  return data;
}

function toast(msg, kind = "") {
  const el = document.createElement("div");
  el.className = "toast " + kind;
  el.innerHTML = msg;
  $("#toasts").appendChild(el);
  setTimeout(() => { el.style.opacity = "0"; el.style.transition = "opacity .4s"; setTimeout(() => el.remove(), 450); }, 5200);
}

function confirmModal({ title, body, confirmLabel = "Confirm", danger = false }) {
  return new Promise((resolve) => {
    $("#modalRoot").innerHTML = `
      <div class="modal-back">
        <div class="modal">
          <h3>${esc(title)}</h3>
          <div class="muted" style="margin:10px 0 22px;">${body}</div>
          <div style="display:flex; gap:10px; justify-content:flex-end;">
            <button class="btn ghost small" id="mCancel">Cancel</button>
            <button class="btn small ${danger ? "danger" : ""}" id="mOk">${esc(confirmLabel)}</button>
          </div>
        </div>
      </div>`;
    $("#mCancel").onclick = () => { $("#modalRoot").innerHTML = ""; resolve(false); };
    $("#mOk").onclick = () => { $("#modalRoot").innerHTML = ""; resolve(true); };
  });
}

const loading = (label = "Working…") => `<div class="loading-pane"><div class="big"><span class="spinner" style="width:34px;height:34px;"></span></div>${esc(label)}</div>`;

/* ================= boot & connection ================= */

async function boot() {
  try { session = await api("/api/session"); }
  catch { session = { connected: false }; }
  if (session.connected) {
    $("#onboard").style.display = "none";
    $("#shell").style.display = "";
    $("#connText").textContent = (session.mode === "live" ? "Live · " : "Demo · ") + (session.name || "");
    setView("overview");
  } else {
    $("#onboard").style.display = "";
    $("#shell").style.display = "none";
  }
}

async function loadCore() {
  const jobs = [
    api("/api/profile").then(d => { profile = d; }).catch(e => { throw e; }),
    api("/api/matches").then(d => { matches = d.matches; }).catch(e => { matches = []; if (e.code !== "account_locked" && e.code !== "not_found") throw e; }),
  ];
  await Promise.all(jobs);
}

async function disconnect() {
  const ok = await confirmModal({
    title: "Disconnect your account?",
    body: "Your token is dropped from memory immediately. You can reconnect anytime with a fresh paste.",
    confirmLabel: "Disconnect", danger: true,
  });
  if (!ok) return;
  await api("/api/disconnect", { method: "POST" });
  location.reload();
}

/* ================= onboarding ================= */

$("#connectBtn").onclick = async () => {
  const btn = $("#connectBtn");
  const tok = $("#tokInput").value.trim();
  if (!tok) { toast("Paste your token first — or open the guide to get it.", "err"); return; }
  btn.disabled = true; btn.textContent = "Verifying…";
  try {
    const r = await api("/api/connect", { method: "POST", body: { token: tok } });
    $("#tokInput").value = "";
    toast(`Connected as <strong>${esc(r.profile.name)}</strong> 🎉`, "ok");
    await new Promise(r2 => setTimeout(r2, 400));
    location.reload();
  } catch (e) {
    if (e.code === "cloud_live_blocked") toast(`☁️ ${e.message} <a href="/docs" target="_blank" style="text-decoration:underline">Run it locally</a>.`, "err");
    else toast(esc(e.message), "err");
    btn.disabled = false; btn.textContent = "Connect";
  }
};
$("#demoLink").onclick = async (ev) => {
  ev.preventDefault();
  try { await api("/api/demo", { method: "POST" }); location.reload(); }
  catch (e) { toast(esc(e.message), "err"); }
};
$("#descBtn").onclick = async () => {
  const desc = $("#descInput").value.trim();
  if (desc.length < 40) { toast("Tell us a bit more (a couple of lines at least).", "err"); return; }
  const out = $("#descResult");
  out.innerHTML = loading("Designing your profile with Gemini…");
  try {
    const r = await api("/api/ai/profile-from-description", { method: "POST", body: { description: desc } });
    const rep = r.report;
    out.innerHTML = `
      <div class="card" style="box-shadow:none;">
        <div class="score-row" style="margin-bottom:16px;">
          <div class="score-ring" style="--p:${rep.overall_score}; width:96px;height:96px;"><b style="font-size:24px;">${rep.overall_score}</b></div>
          <div><strong>Strategy</strong><div class="muted small">${mdLite(rep.summary)}</div></div>
        </div>
        ${rep.bio_variants.map((b, i) => `
          <div class="draft"><span class="d-tone">Bio option ${i + 1} · ${esc(b.tone)}</span>
            <div class="d-text">${esc(b.text)}</div>
            <div class="d-why">${esc(b.rationale)}</div></div>`).join("")}
        ${rep.improved_prompts.length ? `<h3 style="margin-top:18px;">Prompt ideas</h3>` +
          rep.improved_prompts.map(p => `<div class="draft"><span class="d-tone">${esc(p.q)}</span><div class="d-text">${esc(p.a)}</div></div>`).join("") : ""}
        <div class="small muted" style="margin-top:14px;">Like it? <a href="#" onclick="location.reload();return false;">Connect your account</a> to get this from your real profile.</div>
      </div>`;
  } catch (e) { out.innerHTML = ""; toast(esc(e.message), "err"); }
};

/* ================= view plumbing ================= */

const VIEWS = {};
let currentView = "overview";

function setView(name) {
  currentView = name;
  $$(".side-item").forEach(b => b.classList.toggle("active", b.dataset.view === name));
  const root = $("#viewRoot");
  root.innerHTML = loading();
  Promise.resolve(VIEWS[name](root)).catch(e => {
    if (e.code === "no_session" || e.code === "not_connected") { session = { connected: false }; boot(); return; }
    root.innerHTML = `<div class="empty"><span class="em">😕</span>${esc(e.message)}<div style="margin-top:12px;"><button class="btn ghost small" onclick="setView('${name}')">Try again</button></div></div>`;
  });
}
$$(".side-item").forEach(b => b.onclick = () => setView(b.dataset.view));

async function ensureCore() {
  if (!profile) await loadCore();
}

/* ================= OVERVIEW ================= */

VIEWS.overview = async (root) => {
  await ensureCore();
  const waiting = (matches || []).filter(m => m.waiting_on_me).length;
  const withChat = (matches || []).filter(m => m.message_count > 0).length;
  root.innerHTML = `
    <div class="view-head">
      <div>
        <h2>Welcome back, ${esc(profile?.name || session.name || "there")} 👋</h2>
        <p class="sub">${session.mode === "demo" ? "Demo mode — sample data, safe to click everything." : "Your account is connected. Everything you see is your real data."}</p>
      </div>
      <div class="conn-chip" style="padding-top:8px;"><span class="dot"></span>
        <span>${session.mode === "live" ? `token ${esc(session.token_fingerprint || "")} · expires after 2h idle` : "demo session"}</span></div>
    </div>
    <div class="stat-grid" style="margin-bottom:22px;">
      <div class="stat"><div class="v gtext">${(matches || []).length}</div><div class="k">Matches</div></div>
      <div class="stat"><div class="v">${waiting}</div><div class="k">Chats waiting on you</div></div>
      <div class="stat"><div class="v">${withChat}</div><div class="k">Conversations</div></div>
      <div class="stat"><div class="v">${profile?.photos?.length ?? 0}</div><div class="k">Photos</div></div>
    </div>
    <div class="grid cols-2">
      <div class="card hoverable" style="cursor:pointer;" onclick="setView('profile')">
        <div class="icon-chip">🔍</div><h3>Analyze my profile</h3>
        <p class="muted">Scores, bio rewrites, prompt upgrades, and photo feedback from Gemini.</p>
        <span class="btn small">Run analysis →</span>
      </div>
      <div class="card hoverable" style="cursor:pointer;" onclick="setView('conversations')">
        <div class="icon-chip">💬</div><h3>${waiting ? `${waiting} chat${waiting > 1 ? "s" : ""} waiting on you` : "Conversations"}</h3>
        <p class="muted">Analysis, tone-picked reply drafts, and review-then-send messaging.</p>
        <span class="btn small">Open chats →</span>
      </div>
    </div>
    <div class="card" style="margin-top:22px;" id="healthCard">${loading("Checking connection health…")}</div>
  `;
  // connection health
  try {
    const d = await api("/api/diagnostics");
    const rows = d.checks.map(c => `
      <div style="display:flex; gap:10px; align-items:center; padding:8px 0; border-bottom:1px solid var(--line);">
        <span>${c.ok ? "✅" : "⚠️"}</span><strong style="min-width:190px;">${esc(c.name)}</strong>
        <span class="muted small">${esc(c.note)}</span></div>`).join("");
    $("#healthCard").innerHTML = `
      <h3 style="display:flex;align-items:center;gap:9px;">Connection health</h3>
      ${rows}
      ${d.note ? `<p class="small muted" style="margin:12px 0 0;">ℹ️ ${esc(d.note)}</p>` : ""}`;
  } catch (e) {
    $("#healthCard").innerHTML = `<h3>Connection health</h3><p class="muted small">${esc(e.message)}</p>`;
  }
};

/* ================= PROFILE ================= */

VIEWS.profile = async (root) => {
  await ensureCore();
  const p = profile;
  const photoTiles = (p.photos || []).map((ph, i) => {
    const a = analysis?.report?.photo_assessments?.find(x => x.photo_id === ph.id);
    const slot = analysis?.report?.recommended_photo_order?.indexOf(ph.id);
    return `<div class="photo-tile">
      ${ph.url ? `<img src="${esc(ph.url)}" alt="" referrerpolicy="no-referrer"/>` : `<div class="ph">🖼️</div>`}
      <div class="slot">${slot != null && slot >= 0 ? `#${slot + 1} best` : i + 1}</div>
      ${a ? `<div class="verdict" style="${a.keep ? "" : "background:linear-gradient(transparent,rgba(217,58,78,.85));"}">${a.keep ? "✓ keep" : "✕ consider replacing"}</div>` : ""}
    </div>`;
  }).join("");

  root.innerHTML = `
    <div class="view-head">
      <div><h2>Your profile</h2><p class="sub">What Tinder shows today — and what Wingman thinks of it.</p></div>
      <button class="btn" id="analyzeBtn">${analysis ? "Re-run analysis" : "Analyze with AI ✨"}</button>
    </div>

    <div class="card" style="margin-bottom:22px;">
      <div style="display:flex; gap:16px; align-items:center; flex-wrap:wrap;">
        <div style="width:64px;height:64px;border-radius:20px;background:var(--flame);color:#fff;display:grid;place-items:center;font:700 26px var(--display);">${esc((p.name || "?")[0])}</div>
        <div>
          <strong style="font-size:19px;">${esc(p.name)}, ${p.age}</strong> ${p.verified ? '<span class="chip" style="font-size:11px;padding:3px 10px;">✓ verified</span>' : ""}
          <div class="muted small">${esc(p.city)} · ${p.interests.slice(0, 6).map(esc).join(" · ") || "no interests set"}</div>
        </div>
      </div>
      <hr class="divider"/>
      <strong>Bio</strong>
      <p style="white-space:pre-wrap;">${p.bio ? esc(p.bio) : '<span class="muted">No bio yet — the analysis will draft you three.</span>'}</p>
      ${(p.prompts || []).length ? `<strong>Prompts</strong>` +
        p.prompts.map(pr => `<div class="draft"><span class="d-tone">${esc(pr.q)}</span><div class="d-text">${esc(pr.a)}</div></div>`).join("") : ""}
    </div>

    ${(p.photos || []).length ? `<div class="card" style="margin-bottom:22px;"><strong>Photos (${p.photos.length})</strong>
      <div class="photo-grid" style="margin-top:14px;">${photoTiles}</div></div>` : ""}

    <div id="analysisPane">${analysis ? renderAnalysis(analysis) : ""}</div>
  `;

  $("#analyzeBtn").onclick = async (ev) => {
    const btn = ev.target;
    btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Analyzing…';
    $("#analysisPane").innerHTML = loading("Gemini is reading your profile" + (session.mode === "live" ? " and photos" : "") + "… (10–30s)");
    try {
      analysis = await api("/api/ai/analyze-profile", { method: "POST", body: { photo_vision: true } });
      $("#analysisPane").innerHTML = renderAnalysis(analysis);
      setView("profile");
    } catch (e) {
      $("#analysisPane").innerHTML = "";
      toast(esc(e.message), "err");
      btn.disabled = false; btn.textContent = "Analyze with AI ✨";
    }
  };
  wireAnalysisActions();
};

function renderAnalysis(r) {
  const rep = r.report;
  const bios = rep.bio_variants.map((b, i) => `
    <div class="draft">
      <span class="d-tone">Bio ${i + 1} · ${esc(b.tone)} · ${b.char_count} chars</span>
      <div class="d-text" style="white-space:pre-wrap;">${esc(b.text)}</div>
      <div class="d-why">${esc(b.rationale)}</div>
      <div class="d-actions">
        <button class="btn small" data-apply-bio="${i}">Use this bio →</button>
      </div>
    </div>`).join("");
  const prompts = (rep.improved_prompts || []).map((pr, i) => `
    <div class="draft">
      <span class="d-tone">${esc(pr.q)}</span>
      <div class="d-text" style="white-space:pre-wrap;">${esc(pr.a)}</div>
      <div class="d-actions"><button class="btn small" data-apply-prompts="1">Publish all prompt rewrites →</button></div>
    </div>`).join("");
  const photos = (rep.photo_assessments || []).filter(a => (a.strengths.length || a.issues.length)).map(a => {
    const ph = (profile?.photos || []).find(x => x.id === a.photo_id);
    const desc = ph?.description ? `<div class="d-why">👀 AI saw: ${esc(ph.description)}</div>` : "";
    return `<div class="draft">
      <span class="d-tone">Photo ${a.suggested_slot ? `#${a.suggested_slot}` : ""} · ${a.keep ? "✓ keep" : "✕ replace"}</span>
      ${desc}
      ${a.strengths.length ? `<div class="small"><strong>Strengths:</strong> ${a.strengths.map(esc).join(" · ")}</div>` : ""}
      ${a.issues.length ? `<div class="small muted"><strong>Fix:</strong> ${a.issues.map(esc).join(" · ")}</div>` : ""}
    </div>`;
  }).join("");
  return `
    <div class="card">
      <div class="score-row" style="margin-bottom:8px;">
        <div class="score-ring" style="--p:${rep.overall_score};"><b>${rep.overall_score}</b></div>
        <div>
          <strong style="font-size:18px;">Overall score</strong>
          <div class="muted small" style="max-width:430px;">${mdLite(rep.summary)}</div>
          <div style="display:flex; gap:18px; margin-top:10px;">
            <div class="mini-score"><div class="n">${rep.bio_score}</div><div class="l">Bio</div></div>
            <div class="mini-score"><div class="n">${rep.photo_score}</div><div class="l">Photos</div></div>
          </div>
        </div>
      </div>
      ${rep.gaps.length ? `<div style="margin-top:14px;"><strong>Gaps to close</strong>
        <ul class="muted small" style="margin:8px 0 0; padding-left:20px;">${rep.gaps.map(g => `<li>${esc(g)}</li>`).join("")}</ul></div>` : ""}
    </div>
    <h3 style="margin:28px 0 12px;">✍️ Bio rewrites</h3>${bios}
    ${prompts ? `<h3 style="margin:28px 0 12px;">💬 Prompt rewrites</h3>${prompts}` : ""}
    ${photos ? `<h3 style="margin:28px 0 12px;">🖼️ Photo feedback</h3>${photos}` : ""}
    ${rep.prompt_suggestions.length ? `<h3 style="margin:28px 0 12px;">💡 More ideas</h3>
      <div class="pill-list">${rep.prompt_suggestions.map(s => `<span class="tag">${esc(s)}</span>`).join("")}</div>` : ""}`;
}

function wireAnalysisActions() {
  $$("[data-apply-bio]").forEach(btn => btn.onclick = async () => {
    const idx = +btn.dataset.applyBio;
    const text = analysis.report.bio_variants[idx].text;
    const ok = await confirmModal({
      title: "Update your live Tinder bio?",
      body: `<div class="draft" style="box-shadow:none;border-color:var(--line-strong);"><div class="d-text" style="white-space:pre-wrap;">${esc(text)}</div></div>
             <p class="small">This replaces your current bio on your real profile. ${session.mode === "demo" ? "<strong>Demo mode: this is a simulation.</strong>" : ""}</p>`,
      confirmLabel: "Yes, publish bio",
    });
    if (!ok) return;
    btn.disabled = true;
    try {
      const r = await api("/api/actions/bio", { method: "POST", body: { bio: text, confirm: true } });
      toast(esc(r.message), "ok");
      profile.bio = text;
    } catch (e) { toast(esc(e.message), "err"); btn.disabled = false; }
  });
  $$("[data-apply-prompts]").forEach(btn => btn.onclick = async () => {
    const merged = (profile.prompts || []).map(pp => {
      const imp = analysis.report.improved_prompts.find(ip => ip.q === pp.q);
      return { id: pp.id, question_id: pp.question_id, answer_text: imp ? imp.a : pp.a, q: imp ? imp.q : pp.q };
    });
    const ok = await confirmModal({
      title: "Publish prompt rewrites?",
      body: `Updates ${analysis.report.improved_prompts.length} prompt answer(s) on your real profile with the sharper versions. Your questions stay the same.`,
      confirmLabel: "Yes, publish prompts",
    });
    if (!ok) return;
    btn.disabled = true;
    try {
      const r = await api("/api/actions/prompts", { method: "POST", body: { prompts: merged, confirm: true } });
      toast(esc(r.message), "ok");
    } catch (e) { toast(esc(e.message), "err"); btn.disabled = false; }
  });
}

/* ================= CONVERSATIONS ================= */

const TONES = ["balanced", "casual", "funny", "flirty", "confident"];

VIEWS.conversations = async (root) => {
  await ensureCore();
  if (!matches) matches = [];
  if (!matches.length) {
    root.innerHTML = `
      <div class="view-head"><div><h2>Conversations</h2></div></div>
      <div class="empty"><span class="em">💬</span>
        ${session.mode === "demo" ? "The demo has conversations — weird. Restart the demo?" :
        "No matches to coach you on yet. When people match with you, their chats appear here with AI analysis and reply drafts."}
      </div>`;
    return;
  }
  const listHtml = matches.map(m => `
    <div class="match-item" data-mid="${esc(m.match_id)}">
      <div class="av">${esc((m.name || "?")[0])}</div>
      <div class="mi-body">
        <div class="mi-name">${esc(m.name || "Match")}${m.waiting_on_me ? '<span class="waiting-pill">waiting on you</span>' : (m.is_new ? '<span class="waiting-pill" style="background:var(--good-soft);color:var(--good);">new</span>' : "")}</div>
        <div class="mi-last">${m.last_message ? esc(m.last_message.text).slice(0, 46) : "no messages yet"}</div>
      </div>
    </div>`).join("");

  root.innerHTML = `
    <div class="view-head">
      <div><h2>Conversations</h2><p class="sub">Pick a chat — Wingman analyzes it and drafts your next message. You review, you send.</p></div>
    </div>
    <div class="convo-wrap">
      <div class="match-list">${listHtml}</div>
      <div id="threadPane"><div class="empty"><span class="em">👈</span>Select a conversation</div></div>
    </div>`;
  $$(".match-item").forEach(el => el.onclick = () => {
    $$(".match-item").forEach(x => x.classList.remove("selected"));
    el.classList.add("selected");
    openThread(el.dataset.mid, $("#threadPane"));
  });
};

async function openThread(mid, pane) {
  const summary = matches.find(m => m.match_id === mid);
  pane.innerHTML = loading("Loading conversation…");
  let m;
  try { m = await api(`/api/matches/${encodeURIComponent(mid)}`); }
  catch (e) { pane.innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }
  const st = convoState[mid] || { tone: "balanced" };
  convoState[mid] = st;

  const threadHtml = m.conversation.length
    ? m.conversation.map(t => `<div class="bubble ${t.sender}"><div class="who">${t.sender === "me" ? "You" : esc(m.name || "Them")}</div>${esc(t.text)}</div>`).join("")
    : `<div class="empty" style="padding:26px;"><span class="em">👋</span>No messages yet — a great opener matters. Ask Wingman below.</div>`;

  pane.innerHTML = `
    <div class="card">
      <div style="display:flex; gap:14px; align-items:center; margin-bottom:14px;">
        <div class="av" style="width:46px;height:46px;border-radius:14px;background:var(--flame-soft);display:grid;place-items:center;font-weight:700;color:var(--accent);">${esc((m.name || "?")[0])}</div>
        <div><strong style="font-size:17px;">${esc(m.name || "Match")}${m.age ? ", " + m.age : ""}</strong>
          <div class="muted small">${m.bio ? esc(m.bio).slice(0, 110) : "no bio"}${m.interests.length ? " · " + m.interests.slice(0, 4).map(esc).join(" · ") : ""}</div></div>
      </div>
      <div class="thread">${threadHtml}</div>
      <div style="display:flex; gap:10px; margin-top:14px;">
        <input type="text" id="composer" placeholder="${session.mode === "demo" ? "Draft a message (sending is disabled in demo)…" : "Type your message…"}" />
        ${session.mode === "live" ? `<button class="btn" id="sendBtn">Send ↗</button>` : `<button class="btn ghost" id="sendBtn" disabled>Send (demo)</button>`}
      </div>
    </div>
    <div class="card" style="margin-top:18px;">
      <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px;">
        <strong>🤖 AI coaching for this chat</strong>
        <button class="btn small" id="aiBtn">Analyze &amp; draft replies ✨</button>
      </div>
      <div class="tone-bar">${TONES.map(t => `<button class="tone-btn ${t === st.tone ? "active" : ""}" data-tone="${t}" style="text-transform:capitalize;">${t}</button>`).join("")}</div>
      <div id="aiPane">${st.report ? renderConvoAI(st, m) : '<p class="muted small" style="margin:4px 0 0;">Pick a tone and press analyze — you\'ll get a read on the conversation plus three drafts to edit and send.</p>'}</div>
    </div>`;

  $$(".tone-btn", pane).forEach(b => b.onclick = () => {
    st.tone = b.dataset.tone;
    $$(".tone-btn", pane).forEach(x => x.classList.toggle("active", x === b));
  });
  $("#aiBtn").onclick = async (ev) => {
    const btn = ev.target;
    btn.disabled = true; btn.innerHTML = '<span class="spinner"></span>&nbsp;Thinking…';
    $("#aiPane").innerHTML = loading("Reading the conversation with Gemini… (10–25s)");
    try {
      st.report = await api("/api/ai/conversation", { method: "POST", body: { match_id: mid, tone: st.tone } });
      $("#aiPane").innerHTML = renderConvoAI(st, m);
      wireDraftButtons(pane, mid, m);
    } catch (e) {
      $("#aiPane").innerHTML = `<div class="empty">${esc(e.message)}</div>`;
    } finally {
      btn.disabled = false; btn.textContent = "Analyze & draft replies ✨";
    }
  };
  wireDraftButtons(pane, mid, m);

  const composer = $("#composer");
  const doSend = async () => {
    const text = composer.value.trim();
    if (!text) return;
    const ok = await confirmModal({
      title: `Send to ${m.name || "your match"}?`,
      body: `<div class="draft" style="box-shadow:none;border-color:var(--line-strong);"><div class="d-text">${esc(text)}</div></div>
             <p class="small">This sends for real from your account — exactly like pressing send in the Tinder app.</p>`,
      confirmLabel: "Send message",
    });
    if (!ok) return;
    try {
      const r = await api("/api/actions/send", { method: "POST", body: { match_id: mid, text, confirm: true } });
      toast("✅ " + esc(r.message), "ok");
      composer.value = "";
      openThread(mid, pane);   // reload thread
    } catch (e) { toast(esc(e.message), "err"); }
  };
  $("#sendBtn").onclick = doSend;
}

function renderConvoAI(st, m) {
  const r = st.report;
  return `
    <div style="border-left:3px solid var(--accent); padding-left:14px; margin:6px 0 14px;">
      <div><strong>${esc(r.match_summary)}</strong></div>
      <div class="small muted" style="margin-top:4px;">Tone: ${esc(r.tone)} · Engagement: ${esc(r.engagement)}</div>
      ${r.topics.length ? `<div class="small" style="margin-top:6px;">🧵 Topics: ${r.topics.map(esc).join(" · ")}</div>` : ""}
      ${r.issues.length ? `<div class="small muted" style="margin-top:4px;">⚠️ ${r.issues.map(esc).join(" · ")}</div>` : ""}
      <div class="small" style="margin-top:6px;">➡️ <strong>Next move:</strong> ${esc(r.next_move)}</div>
    </div>
    ${r.drafts.map((d, i) => `
      <div class="draft">
        <span class="d-tone">${esc(d.tone)} · ${d.char_count} chars</span>
        <div class="d-text" contenteditable="true" id="draft-${i}">${esc(d.text)}</div>
        <div class="d-why">${esc(d.rationale)}</div>
        <div class="d-actions">
          <button class="btn small" data-use-draft="${i}">Use this ↘</button>
          ${session.mode === "live" ? `<button class="btn ghost small" data-send-draft="${i}">Send this →</button>` : ""}
        </div>
      </div>`).join("")}
    ${r.notes ? `<p class="small muted" style="margin-top:10px;">📝 ${esc(r.notes)}</p>` : ""}`;
}

function wireDraftButtons(pane, mid, m) {
  $$("[data-use-draft]", pane).forEach(b => b.onclick = () => {
    const i = +b.dataset.useDraft;
    const composer = $("#composer");
    composer.value = $(`#draft-${i}`, pane).textContent.trim();
    composer.focus();
    toast("Draft loaded — edit freely, then Send when ready.", "ok");
  });
  $$("[data-send-draft]", pane).forEach(b => b.onclick = async () => {
    const i = +b.dataset.sendDraft;
    const text = $(`#draft-${i}`, pane).textContent.trim();
    const ok = await confirmModal({
      title: `Send to ${m.name || "your match"}?`,
      body: `<div class="draft" style="box-shadow:none;border-color:var(--line-strong);"><div class="d-text">${esc(text)}</div></div>
             <p class="small">Sent for real, from your account.</p>`,
      confirmLabel: "Send message",
    });
    if (!ok) return;
    try {
      const r = await api("/api/actions/send", { method: "POST", body: { match_id: mid, text, confirm: true } });
      toast("✅ " + esc(r.message), "ok");
      openThread(mid, $("#threadPane"));
    } catch (e) { toast(esc(e.message), "err"); }
  });
}

/* ================= INSIGHTS ================= */

VIEWS.insights = async (root) => {
  await ensureCore();
  const ms = matches || [];
  const withMsgs = ms.filter(m => m.message_count > 0);
  const myMsgs = ms.reduce((n, m) => n + (m.conversation || []).filter(t => t.sender === "me").length, 0);
  const theirMsgs = ms.reduce((n, m) => n + (m.conversation || []).filter(t => t.sender === "them").length, 0);
  // interest overlap with my profile
  const mine = new Set((profile?.interests || []).map(i => i.toLowerCase()));
  const overlap = {};
  ms.forEach(m => (m.interests || []).forEach(i => { if (mine.has(i.toLowerCase())) overlap[i] = (overlap[i] || 0) + 1; }));
  const shared = Object.entries(overlap).sort((a, b) => b[1] - a[1]).slice(0, 8);

  root.innerHTML = `
    <div class="view-head"><div><h2>Insights</h2><p class="sub">Patterns across your ${ms.length} match${ms.length === 1 ? "" : "es"} — computed from your real history.</p></div></div>
    ${ms.length === 0 ? `<div class="empty"><span class="em">📊</span>Insights arrive with your first matches.</div>` : `
    <div class="stat-grid" style="margin-bottom:24px;">
      <div class="stat"><div class="v">${ms.length}</div><div class="k">Total matches</div></div>
      <div class="stat"><div class="v">${ms.filter(m => m.is_new).length}</div><div class="k">New, not messaged</div></div>
      <div class="stat"><div class="v">${ms.filter(m => m.waiting_on_me).length}</div><div class="k">Waiting on you</div></div>
      <div class="stat"><div class="v">${withMsgs.length}</div><div class="k">Active conversations</div></div>
      <div class="stat"><div class="v">${myMsgs}</div><div class="k">Messages you sent</div></div>
      <div class="stat"><div class="v">${theirMsgs}</div><div class="k">Messages received</div></div>
      <div class="stat"><div class="v">${withMsgs.length ? Math.round((myMsgs + theirMsgs) / withMsgs.length) : 0}</div><div class="k">Avg messages / chat</div></div>
      <div class="stat"><div class="v">${myMsgs + theirMsgs ? Math.round(100 * Math.min(myMsgs, theirMsgs) / Math.max(myMsgs, theirMsgs)) : 0}%</div><div class="k">Chat balance</div></div>
    </div>
    ${shared.length ? `<div class="card"><strong>Shared interests with your matches</strong>
      <div class="pill-list" style="margin-top:12px;">${shared.map(([i, n]) => `<span class="tag">${esc(i)} ×${n}</span>`).join("")}</div></div>` : ""}
    <div class="card" style="margin-top:20px;">
      <strong>🤖 Ask the assistant about any of this</strong>
      <p class="muted small">“Which of my chats are fading?”, “What should I fix first on my profile?” — the Assistant view answers from your real data.</p>
      <button class="btn small" onclick="setView('assistant')">Open Assistant →</button>
    </div>`}
  `;
};

/* ================= ASSISTANT ================= */

VIEWS.assistant = async (root) => {
  root.innerHTML = `
    <div class="view-head"><div><h2>AI Assistant</h2><p class="sub">Ask anything about your profile, matches, or conversations.</p></div></div>
    <div class="card chat-box" style="min-height:420px;">
      <div id="chatLog" style="display:flex;flex-direction:column;gap:14px;">
        <div class="msg ai">👋 I'm your Wingman. I can see ${session.mode === "demo" ? "the demo profile and chats" : "your connected profile, matches, and conversations"} — ask me anything.</div>
      </div>
      <div class="suggest-chips">
        ${["Analyze my profile", "Improve my bio", "Which of my chats are fading?", "Give me 3 openers for my newest match"].map(q => `<button class="tone-btn" data-q="${esc(q)}">${esc(q)}</button>`).join("")}
      </div>
      <div class="chat-input">
        <textarea id="askBox" placeholder="Ask your Wingman…"></textarea>
        <button class="btn" id="askBtn">Ask ↗</button>
      </div>
    </div>`;

  const log = $("#chatLog");
  const addMsg = (html, cls) => { const d = document.createElement("div"); d.className = "msg " + cls; d.innerHTML = html; log.appendChild(d); log.scrollIntoView({ block: "end", behavior: "smooth" }); return d; };
  const ask = async (q) => {
    addMsg(esc(q), "user");
    const thinking = addMsg('<span class="spinner"></span> thinking…', "ai");
    try {
      const r = await api("/api/ai/assistant", { method: "POST", body: { question: q, include_matches: true } });
      thinking.innerHTML = mdLite(r.answer);
      if (r.followups?.length) {
        const chips = document.createElement("div");
        chips.className = "suggest-chips"; chips.style.marginTop = "4px";
        chips.innerHTML = r.followups.slice(0, 3).map(f => `<button class="tone-btn" data-q="${esc(f)}">${esc(f)}</button>`).join("");
        thinking.appendChild(chips);
        $$("button", chips).forEach(b => b.onclick = () => ask(b.dataset.q));
      }
    } catch (e) { thinking.innerHTML = "😕 " + esc(e.message); }
  };
  $("#askBtn").onclick = () => { const v = $("#askBox").value.trim(); if (v) { $("#askBox").value = ""; ask(v); } };
  $("#askBox").onkeydown = (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("#askBtn").click(); } };
  $$("[data-q]").forEach(b => b.onclick = () => ask(b.dataset.q));
};

/* ================= SETTINGS ================= */

VIEWS.settings = async (root) => {
  root.innerHTML = `
    <div class="view-head"><div><h2>Settings</h2><p class="sub">Session, safety, and connection.</p></div></div>
    <div class="card">
      <h3>🔐 Session</h3>
      <table style="width:100%; font-size:14.5px; border-collapse:collapse;">
        <tr><td class="muted" style="padding:7px 0;">Mode</td><td><strong>${session.mode === "live" ? "Live — your real Tinder account" : "Demo — sample data"}</strong></td></tr>
        <tr><td class="muted" style="padding:7px 0;">Connected as</td><td>${esc(session.name || "—")}</td></tr>
        <tr><td class="muted" style="padding:7px 0;">Token</td><td>${session.mode === "live" ? `<code>${esc(session.token_fingerprint || "")}</code> <span class="muted small">(masked — full value never shown or stored)</span>` : "none (demo)"}</td></tr>
        <tr><td class="muted" style="padding:7px 0;">Auto-expiry</td><td>After 2 hours idle</td></tr>
      </table>
      <div style="display:flex; gap:10px; margin-top:18px; flex-wrap:wrap;">
        <button class="btn danger" id="discoBtn">Disconnect account</button>
        <button class="btn ghost" id="healthBtn">Run connection check</button>
      </div>
      <div id="settingsHealth" style="margin-top:16px;"></div>
    </div>
    <div class="card" style="margin-top:20px;">
      <h3>🛡️ How Wingman treats your access</h3>
      <ul class="muted small" style="margin:8px 0 0; padding-left:20px; line-height:1.9;">
        <li>Token lives in server memory only — never a file, database, or log</li>
        <li>Every write (bio, prompts, messages) requires your explicit confirmation</li>
        <li>The AI can draft, never act — sending is always your click</li>
        <li>Live mode runs on your machine; the public demo instance cannot reach Tinder</li>
      </ul>
    </div>`;
  $("#discoBtn").onclick = disconnect;
  $("#healthBtn").onclick = async () => {
    $("#settingsHealth").innerHTML = loading("Checking…");
    try {
      const d = await api("/api/diagnostics");
      $("#settingsHealth").innerHTML = d.checks.map(c =>
        `<div class="small" style="padding:6px 0; border-bottom:1px solid var(--line);">${c.ok ? "✅" : "⚠️"} <strong>${esc(c.name)}</strong> — ${esc(c.note)}</div>`).join("");
    } catch (e) { $("#settingsHealth").innerHTML = `<p class="small">${esc(e.message)}</p>`; }
  };
};

/* boot */
boot();
