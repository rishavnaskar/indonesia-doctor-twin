"""Render a run as a single self-contained page.

One file, no network, no CDN, no fonts to fetch. That is a constraint from the
architecture rather than a preference: this system is not allowed a hosted
control plane, and a demo that quietly phones out to a CDN while the document
argues for data residency is an own goal in front of exactly the audience that
will notice.

The page has two views, and the toggle between them is the whole argument.
The clinician view is what a doctor sees mid-consultation, which on a green
visit is nothing at all. The audit view is everything the system checked to
decide it could stay quiet.
"""

from __future__ import annotations

import html
import json
from typing import Any

BAND_ORDER = {"red": 0, "amber": 1, "green": 2}


def render(data: dict[str, Any], *, title: str = "AI clinician — demo") -> str:
    payload = json.dumps(data, ensure_ascii=False, indent=None)
    return _TEMPLATE.replace("__TITLE__", html.escape(title)).replace(
        "__DATA__", payload.replace("</", "<\\/")
    )


_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
:root {
  --bg: #f6f7f9; --panel: #ffffff; --ink: #14171a; --muted: #626b75;
  --line: #dfe3e8; --accent: #1c4fd8; --accent-soft: #eef2fe;
  --green: #1a7f4b; --amber: #a86a00; --red: #b3261e;
  --green-bg: #eaf6ef; --amber-bg: #fdf3e2; --red-bg: #fceceb;
  --code: #f0f2f5;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #14171a; --panel: #1c2024; --ink: #e8eaed; --muted: #9aa4ae;
    --line: #2c3238; --accent: #7da2ff; --accent-soft: #1e2637;
    --green: #6ed99b; --amber: #ecb75a; --red: #f0857c;
    --green-bg: #16281f; --amber-bg: #2a2418; --red-bg: #2c1b1a;
    --code: #22272c;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--ink);
  font: 15px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
}
code, .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12.5px; }
header {
  padding: 22px 28px; border-bottom: 1px solid var(--line); background: var(--panel);
}
h1 { margin: 0 0 4px; font-size: 19px; letter-spacing: -0.01em; }
.sub { color: var(--muted); font-size: 13.5px; }
.meta { margin-top: 14px; display: flex; flex-wrap: wrap; gap: 8px 20px; font-size: 12.5px; color: var(--muted); }
.meta b { color: var(--ink); font-weight: 600; }
.headline-stat {
  margin-top: 16px; padding: 12px 16px; border-radius: 8px;
  background: var(--accent-soft); border: 1px solid var(--line); font-size: 14px;
}
.headline-stat b { font-size: 16px; }
.wrap { display: grid; grid-template-columns: 320px 1fr; gap: 0; align-items: start; }
@media (max-width: 860px) { .wrap { grid-template-columns: 1fr; } }
nav { border-right: 1px solid var(--line); background: var(--panel); min-height: 70vh; }
.enc {
  display: block; width: 100%; text-align: left; border: 0; background: none;
  padding: 14px 18px; border-bottom: 1px solid var(--line); cursor: pointer;
  color: inherit; font: inherit;
}
.enc:hover { background: var(--accent-soft); }
.enc[aria-current="true"] { background: var(--accent-soft); box-shadow: inset 3px 0 0 var(--accent); }
.enc .t { font-weight: 600; font-size: 13.5px; margin-bottom: 3px; }
.enc .n { color: var(--muted); font-size: 12px; }
.dot { display: inline-block; width: 9px; height: 9px; border-radius: 50%; margin-right: 7px; vertical-align: 1px; }
.dot.green { background: var(--green); } .dot.amber { background: var(--amber); } .dot.red { background: var(--red); }
main { padding: 26px 30px; max-width: 900px; }
.tabs { display: flex; gap: 4px; margin-bottom: 20px; border-bottom: 1px solid var(--line); }
.tab {
  border: 0; background: none; color: var(--muted); font: inherit; font-size: 13.5px;
  padding: 9px 14px; cursor: pointer; border-bottom: 2px solid transparent; margin-bottom: -1px;
}
.tab[aria-selected="true"] { color: var(--accent); border-bottom-color: var(--accent); font-weight: 600; }
.card { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 20px 22px; margin-bottom: 18px; }
.card h2 { margin: 0 0 4px; font-size: 15px; }
.card h3 { margin: 22px 0 8px; font-size: 12px; text-transform: uppercase; letter-spacing: 0.07em; color: var(--muted); }
.card h3:first-child { margin-top: 0; }
.band { border-radius: 10px; padding: 16px 18px; margin-bottom: 18px; border: 1px solid; }
.band.green { background: var(--green-bg); border-color: var(--green); }
.band.amber { background: var(--amber-bg); border-color: var(--amber); }
.band.red { background: var(--red-bg); border-color: var(--red); }
.band .label { font-size: 11.5px; text-transform: uppercase; letter-spacing: 0.08em; font-weight: 700; }
.band.green .label { color: var(--green); } .band.amber .label { color: var(--amber); } .band.red .label { color: var(--red); }
.band .head { font-size: 15.5px; font-weight: 600; margin-top: 5px; }
.band .gloss { color: var(--muted); font-size: 13px; margin-top: 3px; font-style: italic; }
.band ul { margin: 12px 0 0; padding-left: 18px; }
.band li { margin-bottom: 7px; }
.empty {
  border: 1px dashed var(--line); border-radius: 10px; padding: 34px 22px;
  text-align: center; color: var(--muted); font-size: 13.5px;
}
.empty b { display: block; color: var(--ink); font-size: 14.5px; margin-bottom: 6px; }
table { width: 100%; border-collapse: collapse; font-size: 13.5px; }
th, td { text-align: left; padding: 7px 10px 7px 0; border-bottom: 1px solid var(--line); vertical-align: top; }
th { color: var(--muted); font-weight: 500; font-size: 12px; white-space: nowrap; width: 1%; padding-right: 22px; }
tr:last-child td, tr:last-child th { border-bottom: 0; }
.pill { display: inline-block; padding: 2px 8px; border-radius: 20px; font-size: 11.5px; font-weight: 600; }
.pill.block { background: var(--red-bg); color: var(--red); }
.pill.warn { background: var(--amber-bg); color: var(--amber); }
.pill.none { background: var(--green-bg); color: var(--green); }
.finding { border-left: 3px solid var(--line); padding: 2px 0 2px 14px; margin-bottom: 14px; }
.finding.block { border-left-color: var(--red); }
.finding.warn { border-left-color: var(--amber); }
.finding .m { margin: 4px 0; }
.finding .src { color: var(--muted); font-size: 12px; }
.ack { margin-top: 14px; }
button.act {
  font: inherit; font-size: 13px; font-weight: 600; padding: 8px 16px; border-radius: 7px;
  border: 1px solid var(--red); background: var(--red); color: #fff; cursor: pointer;
}
button.act[disabled] { background: transparent; color: var(--muted); border-color: var(--line); cursor: default; font-weight: 500; }
.watch { font-size: 13px; color: var(--muted); border-left: 3px solid var(--accent); padding-left: 14px; margin: 0 0 20px; }
.trail { display: flex; flex-wrap: wrap; gap: 6px; }
.trail span { background: var(--code); padding: 3px 9px; border-radius: 5px; font-size: 11.5px; }
.toggle { float: right; font-size: 12.5px; color: var(--muted); }
.toggle input { vertical-align: -1px; margin-right: 4px; }
.note { font-size: 12.5px; color: var(--muted); margin-top: 14px; }
.kv { color: var(--muted); }
</style>
</head>
<body>
<header>
  <h1>AI clinician — adult hypertension follow-up</h1>
  <div class="sub">Every field on this page came from a real run. Nothing here is written by hand.</div>
  <div class="meta" id="meta"></div>
  <div class="headline-stat" id="stat"></div>
</header>

<div class="wrap">
  <nav id="nav"></nav>
  <main>
    <div class="tabs">
      <button class="tab" data-view="clinician">What the clinician sees</button>
      <button class="tab" data-view="audit">What the system did</button>
      <label class="toggle"><input type="checkbox" id="gloss"> English gloss</label>
    </div>
    <div id="body"></div>
  </main>
</div>

<script>
const DATA = __DATA__;
let current = 0, view = "clinician", showGloss = false;
const esc = s => String(s == null ? "" : s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const acked = {};

function meta() {
  const p = DATA.pack;
  document.getElementById("meta").innerHTML = [
    ["Pack", p.pack_id + " " + p.version],
    ["Clinical sign-off", p.review_status.replace(/_/g, " ")],
    ["Formulary", p.molecule_count + " molecules"],
    ["Sites", p.site_count],
    ["Language", p.language],
    ["Reasoner", DATA.reasoner],
    ["Generated", DATA.generated_at]
  ].map(([k, v]) => `${esc(k)}: <b>${esc(v)}</b>`).join("");

  document.getElementById("stat").innerHTML =
    `<b>${DATA.declined} of ${DATA.total} encounters ended without a recommendation.</b> ` +
    `That is the system working, not the system failing. Each refusal names its own reason, ` +
    `and every one of them is visible in the audit view.`;
}

function nav() {
  document.getElementById("nav").innerHTML = DATA.encounters.map((e, i) =>
    `<button class="enc" data-i="${i}" aria-current="${i === current}">
       <div class="t"><span class="dot ${e.presentation.band}"></span>${esc(e.title)}</div>
       <div class="n">${esc(e.patient.site_id)} · ${esc(e.outcome)}</div>
     </button>`).join("");
  document.querySelectorAll(".enc").forEach(b =>
    b.onclick = () => { current = +b.dataset.i; draw(); });
}

function bandBlock(e) {
  const p = e.presentation;
  const lines = p.lines.length
    ? `<ul>${p.lines.map(l => `<li>${esc(l.text)}${l.rule_id ? ` <span class="src mono">[${esc(l.rule_id)}]</span>` : ""}</li>`).join("")}</ul>`
    : "";
  const ack = p.requires_acknowledgement
    ? `<div class="ack">${acked[e.key]
        ? `<button class="act" disabled>Acknowledged — the order may now be committed</button>`
        : `<button class="act" data-ack="${esc(e.key)}">Saya mengerti${showGloss ? " (I understand)" : ""}</button>`}</div>`
    : "";
  return `<div class="band ${p.band}">
    <div class="label">${esc(p.band_label)}</div>
    <div class="head">${esc(p.headline)}</div>
    ${showGloss && p.gloss ? `<div class="gloss">${esc(p.gloss)}</div>` : ""}
    ${lines}${ack}</div>`;
}

function draft(e) {
  const d = e.proposal;
  if (!d) return "";
  const changes = d.medication_changes.map(c =>
    `<tr><th>${esc(c.action)}</th><td><b>${esc(c.molecule)}</b> ${c.mg_per_dose}&nbsp;mg &times;${c.doses_per_day}/day
     <div class="src kv">${esc(c.rationale)}</div></td></tr>`).join("");
  return `<div class="card">
    <h2>Draft — for the doctor to accept, edit or reject</h2>
    <h3>Plan</h3>
    <table><tr><th>Assessment</th><td>${esc(d.assessment)}</td></tr>
    <tr><th>Recommendation</th><td><b>${esc(d.recommendation)}</b></td></tr>
    ${changes}
    ${d.follow_up_interval_days ? `<tr><th>Follow-up</th><td>in ${d.follow_up_interval_days} days</td></tr>` : ""}
    ${e.claim ? `<tr><th>Coded</th><td class="mono">${e.claim.codes.map(esc).join(", ")}</td></tr>` : ""}
    </table>
    ${d.patient_instructions ? `<h3>For the patient</h3><div>${esc(d.patient_instructions)}</div>` : ""}
    ${e.signature ? `<h3>Signature</h3><table>
      <tr><th>Signed by</th><td>${esc(e.signature.practitioner_id)} (${esc(e.signature.role)})</td></tr>
      <tr><th>Licence valid to</th><td>${esc(e.signature.licence_expires)}</td></tr>
      <tr><th>Decision</th><td>${esc(e.signature.decision)}</td></tr></table>` : ""}
  </div>`;
}

function clinicianView(e) {
  const p = e.presentation;
  let out = `<p class="watch">${esc(e.watch_for)}</p>`;
  if (p.silent && p.shows_draft) {
    // Green with a draft: the alert channel is silent, but the draft is sitting
    // in the consultation form. "Silent" is about interruption, never about
    // withholding work the clinician asked for.
    out += `<div class="empty"><b>No alert.</b>
      The system found nothing worth interrupting for, so it says nothing — not a
      summary, not a tick, not a &ldquo;no issues found&rdquo;. The draft below is
      simply present in the consultation form, the way a prepared note would be.
      Most visits look like this, and that silence is the only reason an amber is
      worth reading.</div>`;
  } else if (p.silent) {
    out += `<div class="empty"><b>The clinician sees nothing at all.</b>
      The gate refused the draft, and there is nothing here the clinician must act
      on — so they are not interrupted to be told that. They continue exactly as
      they would without the system. The reasons are logged, and they are in the
      audit view.</div>`;
  } else {
    out += bandBlock(e);
  }
  if (p.shows_draft) out += draft(e);
  return out;
}

function auditView(e) {
  const pt = e.patient;
  const findings = e.findings.length ? e.findings.map(f =>
    `<div class="finding ${f.severity}">
      <span class="pill ${f.severity}">${esc(f.severity)}</span>
      <span class="src mono"> check ${f.check} · ${esc(f.rule_id || f.check_name)}</span>
      ${f.converts_to_referral ? `<span class="src"> · converts to referral</span>` : ""}
      <div class="m">${esc(f.message)}</div>
      ${f.citation ? `<div class="src">source: ${esc(f.citation)}</div>` : ""}
    </div>`).join("") : `<div class="src">No check produced a finding.</div>`;

  const prov = e.proposal ? e.proposal.provenance : (e.signature ? e.signature.provenance : null);

  return `<div class="card">
    <h2>${esc(e.title)}</h2>
    <div class="sub">${esc(e.note)}</div>
    <h3>Path taken</h3>
    <div class="trail">${(e.trail[e.trail.length - 1] === e.outcome.toUpperCase()
        ? e.trail : e.trail.concat([e.outcome.toUpperCase()]))
        .map(t => `<span class="mono">${esc(t)}</span>`).join("")}</div>
    <h3>Patient</h3>
    <table>
      <tr><th>Record</th><td class="mono">${esc(pt.patient_id)}, age ${pt.age}</td></tr>
      ${pt.sbp ? `<tr><th>Blood pressure</th><td>${pt.sbp}/${pt.dbp} mmHg</td></tr>` : ""}
      <tr><th>Regimen</th><td>${pt.medications.length ? pt.medications.map(esc).join("<br>") : "none"}</td></tr>
      ${pt.diagnoses.length ? `<tr><th>Coded</th><td class="mono">${pt.diagnoses.map(esc).join(", ")}</td></tr>` : ""}
    </table>
    <h3>Site capability</h3>
    <table>
      <tr><th>Site</th><td>${esc(pt.site_id)} — ${esc(pt.site_label)} (${esc(pt.site_tier)})</td></tr>
      <tr><th>Labs on site</th><td class="mono">${pt.labs_available.map(esc).join(", ") || "none"}</td></tr>
      <tr><th>Capability as of</th><td>${esc(pt.site_as_of)}</td></tr>
    </table>
    <h3>Gate findings — nine checks, plain code, no model</h3>
    ${findings}
    ${prov ? `<h3>Provenance — three pins, not one</h3>
      <table>
        <tr><th>Model</th><td class="mono">${esc(prov[0])}</td></tr>
        <tr><th>Prompt template</th><td class="mono">${esc(prov[1])}</td></tr>
        <tr><th>Corpus</th><td class="mono">${esc(prov[2])}</td></tr>
      </table>
      <div class="note">Model and prompt change far more often than a guideline does.
      A regression in either has to be traceable to the exact proposal it produced.</div>` : ""}
    ${e.presentation.silent && e.presentation.audit.length ? `<h3>What was concluded while staying silent</h3>
      <div class="note">The clinician saw none of this. Silence is not ignorance —
      a silent system with an empty audit trail is indistinguishable from a broken one.</div>` : ""}
  </div>`;
}

function draw() {
  const e = DATA.encounters[current];
  document.querySelectorAll(".tab").forEach(t =>
    t.setAttribute("aria-selected", t.dataset.view === view));
  document.querySelectorAll(".enc").forEach(b =>
    b.setAttribute("aria-current", +b.dataset.i === current));
  document.getElementById("body").innerHTML =
    view === "clinician" ? clinicianView(e) : auditView(e);
  document.querySelectorAll("[data-ack]").forEach(b =>
    b.onclick = () => { acked[b.dataset.ack] = true; draw(); });
}

meta(); nav();
document.querySelectorAll(".tab").forEach(t => t.onclick = () => { view = t.dataset.view; draw(); });
document.getElementById("gloss").onchange = ev => { showGloss = ev.target.checked; draw(); };
draw();
</script>
</body>
</html>
"""
