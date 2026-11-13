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

function saveProfile() { store.set("secplan.profile", JSON.stringify(readProfile())); }

function restoreProfile() {
  let p;
  try { p = JSON.parse(store.get("secplan.profile") || "null"); } catch { p = null; }
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

async function runBaseline() {
  saveProfile();
  const res = await fetch("/api/baseline", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(readProfile()),
  });
  if (!res.ok) return;
  const b = await res.json();
  $("#score").textContent = b.maturity_score;
  $("#tier").textContent = `Tier ${b.tier} · ${b.tier_name}`;
  $("#coverage").innerHTML = Object.entries(b.csf_coverage).map(([fn, pct]) =>
    `<div class="cov"><div>${fn} <span class="muted">${pct}%</span></div>` +
    `<div class="bar"><i style="width:${pct}%"></i></div></div>`).join("");
  const gaps = $("#gaps");
  gaps.innerHTML = "";
  if (!b.gaps.length) gaps.innerHTML = "<li>No gaps in the baseline catalogue.</li>";
  for (const g of b.gaps.slice(0, 6)) {
    const li = document.createElement("li");
    li.title = g.why;
    li.textContent = g.name;
    li.insertAdjacentHTML("beforeend", ` <span class="sev ${g.severity}">${g.severity}</span>`);
    gaps.append(li);
  }
  const risks = $("#risks");
  risks.innerHTML = "";
  for (const r of b.risk_drivers.slice(0, 6)) {
    const li = document.createElement("li");
    li.title = r.reason;
    li.textContent = `${r.threat} `;
    li.insertAdjacentHTML("beforeend", `<span class="risk-score">${r.score}/10</span>`);
    risks.append(li);
  }
}

// ---------- provider settings ----------
async function loadProviders() {
  const res = await fetch("/api/providers");
  const data = await res.json();
  providers = data.providers.filter((p) => p.id !== "custom" || data.custom_base_url_allowed);
  const sel = $("#provider");
  sel.innerHTML = providers.map((p) => `<option value="${p.id}">${p.name}</option>`).join("");
  sel.value = store.get("secplan.provider") || "anthropic";
  if (!sel.value) sel.value = providers[0].id;
  $("#baseUrl").disabled = !data.custom_base_url_allowed;
  applyProvider();
}

function current() { return providers.find((p) => p.id === $("#provider").value); }
const keySlot = (id) => `secplan.key.${id}`;

function applyProvider() {
  const p = current();
  store.set("secplan.provider", p.id);
  $("#model").value = store.get(`secplan.model.${p.id}`) || p.default_model;
  $("#model").placeholder = p.default_model || "model name";
  const local = !p.needs_key;
  $("#baseUrlWrap").hidden = !(p.id === "custom" || local);
  $("#baseUrl").value = store.get(`secplan.base.${p.id}`) || p.base_url || "";
  const saved = store.get(keySlot(p.id));
  $("#apiKey").value = saved || "";
  $("#rememberKey").checked = !!saved;
  $("#apiKey").placeholder = local ? "Not needed for local models" : "Paste your API key";
  const hints = [];
  if (p.key_in_env) hints.push(`Server already has ${p.env_key} set; leave blank to use it.`);
  if (p.docs_url) hints.push(`<a href="${p.docs_url}" target="_blank" rel="noopener">Get a key</a>`);
  $("#keyHint").innerHTML = hints.join(" · ");
}

function persistSettings() {
  const p = current();
  store.set(`secplan.model.${p.id}`, $("#model").value.trim());
  if ($("#baseUrl").value.trim()) store.set(`secplan.base.${p.id}`, $("#baseUrl").value.trim());
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
    if (!transcriptMd) $("#output").classList.add("empty");
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
