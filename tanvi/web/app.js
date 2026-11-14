"use strict";

const $ = (sel) => document.querySelector(sel);
const store = {
  get(k) { try { return localStorage.getItem(k); } catch { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch {} },
  del(k) { try { localStorage.removeItem(k); } catch {} },
};

let providers = [];
let conversation = [];   // turns after the initial prompt: plan, then follow-ups
let transcriptMd = "";   // what Copy / Download export
let controller = null;

// ---------- profile form ----------
async function loadControls() {
  const res = await fetch("/api/controls");
  const controls = await res.json();
  const byFn = {};
  for (const c of controls) (byFn[c.function] ||= []).push(c);
  const box = $("#controls");
  for (const [fn, list] of Object.entries(byFn)) {
    const group = document.createElement("div");
    group.className = "group";
    group.innerHTML = `<div class="group-name">${fn}</div>`;
    for (const c of list) {
      const label = document.createElement("label");
      label.innerHTML = `<input type="checkbox" value="${c.id}">`;
      label.append(c.name);
      group.append(label);
    }
    box.append(group);
  }
}

function readProfile() {
  const f = $("#profile");
  const val = (n) => f.elements[n].value.trim();
  const chips = (name) =>
    [...f.querySelectorAll(`[data-name="${name}"] input:checked`)].map((i) => i.value);
  const controls = {};
  f.querySelectorAll("#controls input").forEach((i) => (controls[i.value] = i.checked));
  return {
    org_name: val("org_name"),
    industry: val("industry"),
    employees: val("employees"),
    budget: val("budget"),
    security_staff: Math.max(0, parseInt(val("security_staff"), 10) || 0),
    timeframe_months: Math.min(36, Math.max(3, parseInt(val("timeframe_months"), 10) || 12)),
    regions: val("regions").split(",").map((s) => s.trim()).filter(Boolean),
    infrastructure: chips("infrastructure"),
    data_types: chips("data_types"),
    compliance: chips("compliance"),
    controls,
    recent_incidents: val("recent_incidents"),
    concerns: val("concerns"),
    goals: val("goals"),
  };
}

function saveProfile() { store.set("tanvi.profile", JSON.stringify(readProfile())); }

function restoreProfile() {
  let p;
  try { p = JSON.parse(store.get("tanvi.profile") || "null"); } catch { p = null; }
  if (!p) return;
  const f = $("#profile");
  for (const k of ["org_name", "industry", "employees", "budget", "security_staff",
                   "timeframe_months", "recent_incidents", "concerns", "goals"]) {
    if (p[k] !== undefined && f.elements[k]) f.elements[k].value = p[k];
  }
  if (Array.isArray(p.regions)) f.elements.regions.value = p.regions.join(", ");
  for (const name of ["infrastructure", "data_types", "compliance"]) {
    f.querySelectorAll(`[data-name="${name}"] input`).forEach((i) => {
      i.checked = (p[name] || []).includes(i.value);
    });
  }
  f.querySelectorAll("#controls input").forEach((i) => (i.checked = !!(p.controls || {})[i.value]));
}

// ---------- baseline ----------
let baselineTimer;
function scheduleBaseline() {
  clearTimeout(baselineTimer);
  baselineTimer = setTimeout(runBaseline, 150);
}

const VERDICTS = {
  1: "Early stage. A few foundational safeguards would remove most of your risk.",
  2: "Making progress. Close the critical gaps below to reach a dependable baseline.",
  3: "A solid foundation. Finish the remaining gaps and test what you already have.",
  4: "A strong posture. Keep your safeguards tested and reviewed.",
};
let allGaps = [];
let showAllGaps = false;

async function runBaseline() {
  saveProfile();
  updateStepMeta();
  const res = await fetch("/api/baseline", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(readProfile()),
  });
  if (!res.ok) return;
  const b = await res.json();

  const ring = $("#ring");
  ring.style.setProperty("--p", b.maturity_score);
  ring.dataset.tier = b.tier;
  $("#score").textContent = b.maturity_score;
  $("#tier").textContent = `Tier ${b.tier} · ${b.tier_name}`;
  $("#verdict").textContent = VERDICTS[b.tier];
  const total = b.in_place.length + b.gaps.length;
  const critical = b.gaps.filter((g) => g.severity === "critical").length;
  $("#stats").innerHTML =
    `<span class="stat"><b>${b.in_place.length}</b> of ${total} safeguards in place</span>` +
    (critical ? `<span class="stat bad"><b>${critical}</b> critical gap${critical > 1 ? "s" : ""}</span>` : "");

  $("#coverage").innerHTML = Object.entries(b.csf_coverage).map(([fn, pct]) => {
    const cls = pct >= 70 ? "ok" : pct >= 40 ? "mid" : "";
    return `<div class="cov"><span>${fn}</span>` +
      `<div class="bar"><i class="${cls}" style="width:${Math.max(pct, 2)}%"></i></div>` +
      `<span class="pct">${pct}%</span></div>`;
  }).join("");

  allGaps = b.gaps;
  renderGaps();

  $("#risks").innerHTML = b.risk_drivers.slice(0, 5).map((r) => {
    const cls = r.score >= 8 ? "" : r.score >= 5 ? "mid" : "ok";
    return `<li class="risk"><div class="risk-top"><span>${escapeHtml(r.threat)}</span>` +
      `<span class="risk-score">${r.score} / 10</span></div>` +
      `<div class="bar"><i class="${cls}" style="width:${r.score * 10}%"></i></div>` +
      `<div class="risk-why">${escapeHtml(r.reason)}</div></li>`;
  }).join("");
}

function renderGaps() {
  const list = showAllGaps ? allGaps : allGaps.slice(0, 5);
  $("#gaps").innerHTML = allGaps.length
    ? list.map((g) =>
        `<li class="gap"><div class="gap-top"><span class="gap-name">${escapeHtml(g.name)}</span>` +
        `<span class="pill ${g.severity}">${g.severity}</span></div>` +
        `<div class="gap-why">${escapeHtml(g.why)}</div>` +
        `<div class="gap-ref">${g.function} · ${escapeHtml(g.cis)}</div></li>`).join("")
    : `<li class="gap done">Every safeguard in the catalogue is in place. Nice work.</li>`;
  const more = $("#moreGaps");
  more.hidden = allGaps.length <= 5;
  more.textContent = showAllGaps ? "Show fewer" : `Show all ${allGaps.length} gaps`;
}

function updateStepMeta() {
  const p = readProfile();
  const meta = (k, text) => { const el = document.querySelector(`[data-meta="${k}"]`); if (el) el.textContent = text; };
  meta("basics", [p.industry, `${p.employees} people`].join(" · "));
  const env = p.infrastructure.length + p.data_types.length + p.compliance.length;
  meta("env", env ? `${env} selected` : "");
  const total = Object.keys(p.controls).length;
  const have = Object.values(p.controls).filter(Boolean).length;
  meta("controls", `${have} / ${total}`);
  const ctx = [p.recent_incidents, p.concerns, p.goals].filter(Boolean).length;
  meta("context", ctx ? `${ctx} filled` : "");
}

// ---------- provider settings ----------
async function loadProviders() {
  const res = await fetch("/api/providers");
  const data = await res.json();
  providers = data.providers.filter((p) => p.id !== "custom" || data.custom_base_url_allowed);
  const sel = $("#provider");
  sel.innerHTML = providers.map((p) => `<option value="${p.id}">${p.name}</option>`).join("");
  sel.value = store.get("tanvi.provider") || "anthropic";
  if (!sel.value) sel.value = providers[0].id;
  $("#baseUrl").disabled = !data.custom_base_url_allowed;
  applyProvider();
}

function current() { return providers.find((p) => p.id === $("#provider").value); }
const keySlot = (id) => `tanvi.key.${id}`;

function applyProvider() {
  const p = current();
  store.set("tanvi.provider", p.id);
  $("#model").value = store.get(`tanvi.model.${p.id}`) || p.default_model;
  $("#model").placeholder = p.default_model || "model name";
  const local = !p.needs_key;
  $("#baseUrlWrap").hidden = !(p.id === "custom" || local);
  $("#baseUrl").value = store.get(`tanvi.base.${p.id}`) || p.base_url || "";
  const saved = store.get(keySlot(p.id));
  $("#apiKey").value = saved || "";
  $("#rememberKey").checked = !!saved;
  $("#apiKey").placeholder = local ? "Not needed for local models" : "Paste your API key";
  $("#modelList").innerHTML = "";
  $("#modelHint").textContent = p.id === "huggingface"
    ? "Any chat model served by Hugging Face Inference Providers. Click Browse to pick one."
    : "";
  const hints = [];
  if (p.key_in_env) hints.push(`Server already has ${p.env_key} set; leave blank to use it.`);
  if (p.docs_url) hints.push(`<a href="${p.docs_url}" target="_blank" rel="noopener">Get a key</a>`);
  $("#keyHint").innerHTML = hints.join(" · ");
}

async function browseModels() {
  const p = current();
  const btn = $("#browseModels");
  btn.disabled = true;
  btn.textContent = "Loading…";
  showError("");
  const headers = { "Content-Type": "application/json" };
  const key = $("#apiKey").value.trim();
  if (key) headers["X-API-Key"] = key;
  try {
    const res = await fetch("/api/models", {
      method: "POST", headers,
      body: JSON.stringify({ provider: p.id, base_url: $("#baseUrlWrap").hidden ? "" : $("#baseUrl").value.trim() }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Could not load models");
    $("#modelList").innerHTML = data.models.map((m) => `<option value="${escapeHtml(m)}">`).join("");
    $("#modelHint").textContent = `${data.models.length} models available. Click the model box to choose one, or type to filter.`;
    $("#model").focus();
  } catch (err) {
    showError(err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "Browse";
  }
}

function persistSettings() {
  const p = current();
  store.set(`tanvi.model.${p.id}`, $("#model").value.trim());
  if ($("#baseUrl").value.trim()) store.set(`tanvi.base.${p.id}`, $("#baseUrl").value.trim());
  if ($("#rememberKey").checked && $("#apiKey").value.trim()) {
    store.set(keySlot(p.id), $("#apiKey").value.trim());
  } else {
    store.del(keySlot(p.id));
  }
}

// ---------- generation ----------
function render(md, streaming) {
  const out = $("#output");
  out.classList.remove("empty");
  out.innerHTML = DOMPurify.sanitize(marked.parse(md));
  out.classList.toggle("cursor", streaming);
  buildToc(streaming);
}

function buildToc(streaming) {
  const toc = $("#toc");
  const heads = [...$("#output").querySelectorAll("h2")];
  if (streaming || heads.length < 3) { toc.hidden = true; return; }
  toc.innerHTML = "";
  heads.forEach((h, i) => {
    h.id = `sec-${i}`;
    const a = document.createElement("a");
    a.href = `#sec-${i}`;
    a.textContent = h.textContent.replace(/^\d+\.\s*/, "");
    toc.append(a);
  });
  toc.hidden = false;
}

function setBusy(busy) {
  $("#generate").disabled = busy;
  $("#stop").hidden = !busy;
  $("#followupForm").querySelector("button").disabled = busy;
  $("#copy").disabled = busy || !transcriptMd;
  $("#download").disabled = busy || !transcriptMd;
}

function showError(msg) {
  const e = $("#error");
  e.hidden = !msg;
  e.textContent = msg || "";
}

async function generate(followup = "") {
  persistSettings();
  showError("");
  const p = current();
  const prior = followup ? transcriptMd + `\n\n<div class="q">${escapeHtml(followup)}</div>\n\n` : "";
  if (!followup) conversation = [];

  const headers = { "Content-Type": "application/json" };
  const key = $("#apiKey").value.trim();
  if (key) headers["X-API-Key"] = key;

  controller = new AbortController();
  setBusy(true);
  render(prior, true);
  let answer = "";
  try {
    const res = await fetch("/api/plan", {
      method: "POST", headers, signal: controller.signal,
      body: JSON.stringify({
        profile: readProfile(), provider: p.id, model: $("#model").value.trim(),
        base_url: $("#baseUrlWrap").hidden ? "" : $("#baseUrl").value.trim(),
        conversation, followup,
      }),
    });
    if (!res.ok) {
      let msg = `Request failed (${res.status})`;
      try { const j = await res.json(); msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail); } catch {}
      throw new Error(msg);
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      answer += decoder.decode(value, { stream: true });
      render(prior + answer, true);
    }
  } catch (err) {
    if (err.name !== "AbortError") showError(err.message);
  } finally {
    controller = null;
    if (answer) {
      if (followup) conversation.push({ role: "user", content: followup });
      conversation.push({ role: "assistant", content: answer });
      transcriptMd = prior + answer;
      $("#followupForm").hidden = false;
    }
    render(transcriptMd || prior, false);
    if (!transcriptMd) { $("#output").classList.add("empty"); $("#output").textContent = "Your plan will appear here."; }
    setBusy(false);
  }
}

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function exportMarkdown() {
  return transcriptMd.replace(/<div class="q">(.*?)<\/div>/g, "## Follow-up: $1");
}

// ---------- wiring ----------
async function init() {
  await loadControls();
  restoreProfile();
  await loadProviders();
  runBaseline();

  $("#profile").addEventListener("input", scheduleBaseline);
  $("#profile").addEventListener("change", scheduleBaseline);
  $("#profile").addEventListener("submit", (e) => e.preventDefault());
  $("#provider").addEventListener("change", applyProvider);
  $("#rememberKey").addEventListener("change", persistSettings);
  $("#browseModels").addEventListener("click", browseModels);
  $("#moreGaps").addEventListener("click", () => { showAllGaps = !showAllGaps; renderGaps(); });
  $("#generate").addEventListener("click", () => generate());
  $("#stop").addEventListener("click", () => controller && controller.abort());
  $("#followupForm").addEventListener("submit", (e) => {
    e.preventDefault();
    const q = $("#followup").value.trim();
    if (!q || controller) return;
    $("#followup").value = "";
    generate(q);
  });
  $("#copy").addEventListener("click", async () => {
    await navigator.clipboard.writeText(exportMarkdown());
    $("#copy").textContent = "Copied";
    setTimeout(() => ($("#copy").textContent = "Copy"), 1200);
  });
  $("#download").addEventListener("click", () => {
    const blob = new Blob([exportMarkdown()], { type: "text/markdown" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "security-strategy.md";
    a.click();
    URL.revokeObjectURL(a.href);
  });
}

init();
