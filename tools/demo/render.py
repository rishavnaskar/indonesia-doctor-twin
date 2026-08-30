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
  --bg:#f5f6f8; --panel:#fff; --ink:#14171a; --muted:#5f6871; --faint:#8a939c;
  --line:#dfe3e8; --accent:#1c4fd8; --soft:#eef2fe;
  --green:#1a7f4b; --amber:#a86a00; --red:#b3261e;
  --green-bg:#eaf6ef; --amber-bg:#fdf3e2; --red-bg:#fceceb; --code:#eef1f4;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg:#131619; --panel:#1b1f23; --ink:#e8eaed; --muted:#9aa4ae; --faint:#788089;
    --line:#2b3137; --accent:#7da2ff; --soft:#1d2536;
    --green:#6ed99b; --amber:#ecb75a; --red:#f0857c;
    --green-bg:#16281f; --amber-bg:#2a2418; --red-bg:#2c1b1a; --code:#22272c;
  }
}
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--ink);
  font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }
.mono,code { font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; font-size:12.5px; }
header { padding:20px 26px; border-bottom:1px solid var(--line); background:var(--panel); }
h1 { margin:0 0 5px; font-size:19px; letter-spacing:-.01em; }
.lede { color:var(--muted); font-size:13.5px; max-width:80ch; }
.meta { margin-top:12px; display:flex; flex-wrap:wrap; gap:6px 18px; font-size:12px; color:var(--faint); }
.meta b { color:var(--muted); font-weight:600; }
.stat { margin-top:14px; padding:11px 15px; border-radius:8px; background:var(--soft);
  border:1px solid var(--line); font-size:13.5px; }
.wrap { display:grid; grid-template-columns:290px 1fr; }
@media (max-width:900px){ .wrap{ grid-template-columns:1fr; } }
nav { border-right:1px solid var(--line); background:var(--panel); }
.enc { display:block; width:100%; text-align:left; border:0; background:none; color:inherit;
  font:inherit; padding:12px 16px; border-bottom:1px solid var(--line); cursor:pointer; }
.enc:hover { background:var(--soft); }
.enc[aria-current="true"] { background:var(--soft); box-shadow:inset 3px 0 0 var(--accent); }
.enc .t { font-weight:600; font-size:13px; margin-bottom:2px; }
.enc .n { color:var(--faint); font-size:11.5px; }
.dot { display:inline-block; width:8px; height:8px; border-radius:50%; margin-right:7px; }
.dot.green{background:var(--green)} .dot.amber{background:var(--amber)} .dot.red{background:var(--red)}
main { padding:22px 26px; max-width:960px; }
.hd { font-size:17px; font-weight:650; margin:0 0 3px; }
.hd + .sub { color:var(--muted); font-size:13px; margin-bottom:14px; }
.outcome { display:inline-block; padding:3px 10px; border-radius:20px; font-size:11.5px;
  font-weight:700; letter-spacing:.04em; text-transform:uppercase; }
.outcome.green{background:var(--green-bg);color:var(--green)}
.outcome.amber{background:var(--amber-bg);color:var(--amber)}
.outcome.red{background:var(--red-bg);color:var(--red)}
.outcome.fail{background:var(--code);color:var(--muted)}
.err { border:1px solid var(--line); border-left:3px solid var(--amber); border-radius:8px;
  padding:14px 16px; margin-bottom:14px; background:var(--panel); }
.err b { display:block; margin-bottom:5px; }
.card { background:var(--panel); border:1px solid var(--line); border-radius:10px;
  padding:16px 18px; margin-bottom:14px; }
.card > h2 { margin:0 0 12px; font-size:13px; text-transform:uppercase; letter-spacing:.07em;
  color:var(--muted); font-weight:650; }
h3 { margin:16px 0 7px; font-size:12px; text-transform:uppercase; letter-spacing:.06em;
  color:var(--faint); font-weight:600; }
h3:first-of-type { margin-top:0; }
.grid2 { display:grid; grid-template-columns:1fr 1fr; gap:0 26px; }
@media (max-width:700px){ .grid2{ grid-template-columns:1fr; } }
table { width:100%; border-collapse:collapse; font-size:13.5px; }
th,td { text-align:left; padding:6px 10px 6px 0; border-bottom:1px solid var(--line); vertical-align:top; }
th { color:var(--faint); font-weight:500; font-size:12px; white-space:nowrap; width:1%; padding-right:18px; }
tr:last-child th, tr:last-child td { border-bottom:0; }
thead th { border-bottom:1px solid var(--line); width:auto; }
.plain { color:var(--muted); font-size:12.5px; }
.gloss { color:var(--muted); font-size:12.5px; font-style:italic; margin-top:3px; }
.bi { border-left:2px solid var(--line); padding-left:11px; }
.bi .id { font-size:14px; }
.tag { display:inline-block; padding:1px 7px; border-radius:5px; background:var(--code);
  font-size:11.5px; color:var(--muted); margin-left:6px; }
.tag.stale { background:var(--amber-bg); color:var(--amber); font-weight:600; }
.tag.flag { background:var(--red-bg); color:var(--red); font-weight:600; }
.band { border-radius:10px; padding:14px 16px; margin-bottom:14px; border:1px solid; }
.band.green{background:var(--green-bg);border-color:var(--green)}
.band.amber{background:var(--amber-bg);border-color:var(--amber)}
.band.red{background:var(--red-bg);border-color:var(--red)}
.band .lbl { font-size:11px; text-transform:uppercase; letter-spacing:.08em; font-weight:700; }
.band.green .lbl{color:var(--green)} .band.amber .lbl{color:var(--amber)} .band.red .lbl{color:var(--red)}
.band .h { font-size:15px; font-weight:650; margin-top:4px; }
.band ul { margin:10px 0 0; padding-left:18px; } .band li { margin-bottom:6px; }
.empty { border:1px dashed var(--line); border-radius:10px; padding:26px 20px; text-align:center;
  color:var(--muted); font-size:13px; margin-bottom:14px; }
.empty b { display:block; color:var(--ink); font-size:14.5px; margin-bottom:5px; }
.tabs { display:flex; gap:2px; margin:18px 0 14px; border-bottom:1px solid var(--line); }
.tab { border:0; background:none; color:var(--muted); font:inherit; font-size:13.5px;
  padding:8px 14px; cursor:pointer; border-bottom:2px solid transparent; margin-bottom:-1px; }
.tab[aria-selected="true"]{ color:var(--accent); border-bottom-color:var(--accent); font-weight:650; }
.chk { display:flex; gap:10px; padding:8px 0; border-bottom:1px solid var(--line); font-size:13px; }
.chk:last-child{border-bottom:0}
.chk .mark { flex:0 0 20px; font-weight:700; }
.chk.ok .mark{ color:var(--green) } .chk.hit .mark{ color:var(--red) }
.chk .ttl { font-weight:600; }
.finding { border-left:3px solid var(--red); padding:2px 0 2px 12px; margin-bottom:12px; }
.finding.warn { border-left-color:var(--amber); }
.finding .m { margin:3px 0; }
.finding .src { color:var(--faint); font-size:11.5px; }
.watch { font-size:13px; color:var(--muted); border-left:3px solid var(--accent);
  padding-left:12px; margin:0 0 14px; }
.trail { display:flex; flex-wrap:wrap; gap:5px; margin-bottom:4px; }
.trail span { background:var(--code); padding:3px 8px; border-radius:5px; font-size:11px; }
.steps { font-size:12.5px; color:var(--muted); }
.steps div { padding:3px 0; }
button.act { font:inherit; font-size:13px; font-weight:650; padding:7px 15px; border-radius:7px;
  border:1px solid var(--red); background:var(--red); color:#fff; cursor:pointer; margin-top:12px; }
button.act[disabled]{ background:transparent; color:var(--muted); border-color:var(--line); font-weight:500; }
.note { font-size:12.5px; color:var(--faint); margin-top:10px; }
.bpnow { font-size:26px; font-weight:650; letter-spacing:-.02em; }
.bpnow small { font-size:13px; font-weight:400; color:var(--muted); }
</style>
</head>
<body>
<header>
  <h1>AI clinician — adult high blood pressure, follow-up visits</h1>
  <div class="lede">A doctor's assistant, not a doctor. It drafts a plan for a return visit;
    a licensed doctor reviews and signs every one. Nine safety checks — plain code, no AI —
    sit between the draft and the doctor, and any one of them can stop it.
    Every figure below came from a real run of the system. Nothing is written by hand.
    <div style="margin-top:8px"><a href="/clinic">Build your own patient and run it &rarr;</a></div></div>
  <div class="meta" id="meta"></div>
  <div class="stat" id="drafter" style="background:var(--panel)"></div>
  <div class="stat" id="stat"></div>
</header>
<div class="wrap">
  <nav id="nav"></nav>
  <main id="main"></main>
</div>
<script>
const DATA = __DATA__;
const G = DATA.glossary || {};
let current = 0, view = "clinician";
const acked = {};
const esc = s => String(s==null?"":s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const row = (k,v) => `<tr><th>${esc(k)}</th><td>${v}</td></tr>`;

function meta(){
  const p = DATA.pack;
  document.getElementById("meta").innerHTML = [
    ["Rules pack", p.pack_id+" "+p.version], ["Clinical sign-off", p.review_status.replace(/_/g," ")],
    ["Drugs on the approved list", p.molecule_count], ["Hospitals modelled", p.site_count],
    ["Patient-facing language", p.language], ["Run at", DATA.generated_at]
  ].map(([k,v])=>`${esc(k)}: <b>${esc(v)}</b>`).join("");
  document.getElementById("drafter").innerHTML =
    `<b>Drafts written by:</b> <span class="mono">${esc(DATA.reasoner)}</span>` +
    (DATA.is_model
      ? ` &mdash; a real AI model, swapped in behind the same interface. Everything after the
          draft is unchanged: the same nine checks, the same signature rule, the same code.`
      : ` &mdash; <b>not an AI model.</b> This is the rule-following reference version, and it is
          the default on purpose: it is free, instant, and gives the identical answer every time,
          so a change in behaviour is a real change rather than the model having a different day.
          The AI model plugs into the same interface and nothing downstream moves.
          Run <span class="mono">make surface-live</span> to see it drafted by an actual model.`);
  const fails = DATA.drafter_failures || 0;
  document.getElementById("stat").innerHTML =
    `<b>${DATA.declined} of the ${DATA.total} visits below ended with no recommendation reaching the doctor.</b>
     That is the system working, not failing. Every refusal names its own reason, and you can read
     all of them under &ldquo;What the system did&rdquo;.` +
    (fails ? ` <b>A further ${fails} could not be drafted at all</b> — the model returned something
      unusable. That is a model failure, not a clinical one, and it is counted separately because
      the two mean different things.` : "");
}

function nav(){
  document.getElementById("nav").innerHTML = DATA.encounters.map((e,i)=>
    `<button class="enc" data-i="${i}" aria-current="${i===current}">
      <div class="t"><span class="dot ${e.presentation.band}"></span>${esc(e.title)}</div>
      <div class="n">${esc(e.patient.site_id)} &middot; ${esc(e.outcome.replace(/_/g," "))}</div>
    </button>`).join("");
  document.querySelectorAll(".enc").forEach(b=>b.onclick=()=>{current=+b.dataset.i;draw();});
}

function patientCard(e){
  const p = e.patient;
  const hist = p.history.length ? `<table>
    <thead><tr><th style="width:auto">Visit</th><th style="width:auto">Blood pressure</th>
    <th style="width:auto">What was decided</th></tr></thead>
    ${p.history.map(h=>`<tr><td>${esc(h.date)}</td>
      <td class="mono">${h.sbp?`${h.sbp}/${h.dbp}`:"—"}</td>
      <td class="plain">${esc(h.decision||"—")}</td></tr>`).join("")}</table>`
    : `<div class="plain">No earlier visits on record.</div>`;

  const obs = p.observations.map(o=>`<tr>
      <th>${esc(o.label)}</th>
      <td><span class="mono">${o.value}${o.unit?" "+esc(o.unit):""}</span>
        <span class="tag${o.stale?" stale":""}">${o.age_days===0?"today":esc(o.age_days)+" days old"}${o.stale?" — too old to rely on":""}</span>
        <div class="plain">${esc(o.plain)}</div></td></tr>`).join("");

  const meds = p.medications.length ? p.medications.map(m=>`<div class="bi" style="margin-bottom:10px">
      <div class="id"><b>${esc(m.text)}</b>${m.class_label?`<span class="tag">${esc(m.class_label)}</span>`:""}</div>
      <div class="plain">${esc(m.plain)}</div></div>`).join("")
    : `<div class="plain">Not on any blood-pressure medication.</div>`;

  const dx = p.diagnoses.map(d=>`<div class="bi" style="margin-bottom:9px">
      <div class="id"><code>${esc(d.code)}</code></div>
      <div class="plain">${esc(d.plain||"No plain-language entry for this code.")}</div></div>`).join("");

  const sx = p.symptoms.length
    ? p.symptoms.map(s=>`<div style="margin-bottom:5px">${esc(s.plain)}<span class="tag flag">reported</span></div>`).join("")
    : `<div class="plain">None reported.</div>`;
  const denied = p.symptoms_denied.length
    ? `<div class="note">Asked about and denied: ${p.symptoms_denied.map(s=>esc(s.plain)).join("; ")}.</div>` : "";

  return `<div class="card">
    <h2>The patient</h2>
    <div class="grid2">
      <div>
        <h3>Who</h3>
        <table>
          ${row("Record", `<span class="mono">${esc(p.patient_id)}</span>`)}
          ${row("Age and sex", `${p.age}, ${esc(p.sex)}`)}
          ${row("Seen at", `${esc(p.site_id)} — ${esc(p.site_label)}`)}
        </table>
        <h3>Blood pressure today</h3>
        <div class="bpnow">${p.sbp?`${p.sbp}/${p.dbp} <small>mmHg</small>`:"not recorded"}</div>
        <div class="plain">Top number is the pressure when the heart beats; bottom number is between beats.</div>
        <h3>Conditions on record</h3>
        ${dx || `<div class="plain">None recorded.</div>`}
        <h3>Symptoms today</h3>
        ${sx}${denied}
      </div>
      <div>
        <h3>Earlier visits</h3>
        ${hist}
        <h3>Current medication</h3>
        ${meds}
        <h3>Blood tests and readings on file</h3>
        <table>${obs}</table>
        ${p.intolerances.length?`<h3>Cannot tolerate</h3>${p.intolerances.map(i=>
          `<div class="plain">${esc(i.molecule)} (${esc(i.class_label)}) — recorded ${esc(i.documented_at)}${i.reaction?": "+esc(i.reaction):""}</div>`).join("")}`:""}
        ${p.allergies.length?`<h3>Allergies</h3>${p.allergies.map(a=>
          `<div class="plain">${esc(a.substance)}${a.reaction?" — "+esc(a.reaction):""}</div>`).join("")}`:""}
      </div>
    </div>
  </div>`;
}

function bandBlock(e){
  const p = e.presentation;
  const lines = p.lines.length ? `<ul>${p.lines.map(l=>
    `<li>${esc(l.text)}${l.rule_id?` <span class="src mono">[rule ${esc(l.rule_id)}]</span>`:""}</li>`).join("")}</ul>` : "";
  const ack = p.requires_acknowledgement ? (acked[e.key]
      ? `<button class="act" disabled>Acknowledged — the doctor may now proceed</button>`
      : `<button class="act" data-ack="${esc(e.key)}">Saya mengerti &nbsp;/&nbsp; I understand</button>`) : "";
  return `<div class="band ${p.band}">
    <div class="lbl">${esc(p.band_label)}${p.band==="red"?" / action needed":p.band==="amber"?" / worth a look":" / nothing to flag"}</div>
    <div class="h">${esc(p.headline)}</div>
    ${p.gloss?`<div class="gloss">${esc(p.gloss)}</div>`:""}
    ${lines}${ack}</div>`;
}

function draftCard(e){
  const d = e.proposal; if(!d) return "";
  const changes = d.medication_changes.map(c=>`<tr><th>${esc(c.action)}</th>
    <td><b>${esc(c.molecule)}</b> ${c.mg_per_dose}&nbsp;mg, ${c.doses_per_day}&times; a day
      ${c.class_label?`<span class="tag">${esc(c.class_label)}</span>`:""}
      <div class="plain">${esc(c.class_plain)}</div>
      <div class="plain">Reason given: ${esc(c.rationale)}</div></td></tr>`).join("");
  return `<div class="card">
    <h2>The draft — for the doctor to accept, edit or reject</h2>
    <table>
      ${row("Assessment", `${esc(d.assessment)}<div class="plain">${esc(d.assessment_plain)}</div>`)}
      ${row("Proposed action", `<b>${esc(d.recommendation.replace(/_/g," "))}</b><div class="plain">${esc(d.recommendation_plain)}</div>`)}
      ${changes}
      ${d.follow_up_interval_days?row("Come back in", `${d.follow_up_interval_days} days`):""}
      ${e.claim?row("Billing codes", e.claim.codes.map(c=>
        `<div><code>${esc(c.code)}</code> <span class="plain">${esc(c.plain)}</span></div>`).join("")):""}
      ${row("Confidence", `${(d.confidence*100).toFixed(0)}%`)}
    </table>
    ${d.patient_instructions?`<h3>What the patient is told</h3>
      <div>${esc(d.patient_instructions)} <span class="tag">${esc(DATA.pack.language)}</span></div>
      ${d.patient_instructions_gloss?`<div class="gloss">${esc(d.patient_instructions_gloss)}</div>`:""}`:""}
    ${e.signature?`<h3>Signature</h3><table>
      ${row("Signed by", `${esc(e.signature.practitioner_id)} — ${esc(e.signature.role)}`)}
      ${row("Licence valid until", esc(e.signature.licence_expires))}
      ${row("Decision", esc(e.signature.decision))}</table>
      <div class="note">The signature is refused in software if the licence has lapsed or the
      doctor is not on this hospital's roster.</div>`:""}
  </div>`;
}

function clinicianView(e){
  const p = e.presentation;
  let out = `<p class="watch">${esc(e.watch_for)}</p>`;
  if (e.error) {
    return out + `<div class="err"><b>The drafter failed on this visit.</b>
      <span class="mono">${esc(e.error)}</span>
      <div class="plain" style="margin-top:8px">Nothing reached the safety checks and nothing
      reached the doctor. The consultation continues exactly as it would without the system.
      A weak model producing unusable output is a normal event, and containing it to one visit
      rather than one outage is the behaviour worth showing.</div></div>`;
  }
  if (p.silent && p.shows_draft) {
    out += `<div class="empty"><b>No alert.</b>
      Nothing here was worth interrupting the doctor for, so the system says nothing —
      no summary, no tick, no &ldquo;all clear&rdquo;. The draft below is simply waiting in the
      consultation form. Most visits look like this, and that silence is the only reason
      a warning is worth reading when one does appear.</div>`;
  } else if (p.silent) {
    out += `<div class="empty"><b>The doctor sees nothing at all.</b>
      The safety checks refused the draft, and there is nothing here the doctor must act on —
      so they are not interrupted to be told that. They carry on exactly as they would
      without the system. The reasons were logged; they are under
      &ldquo;What the system did&rdquo;.</div>`;
  } else { out += bandBlock(e); }
  if (p.shows_draft) out += draftCard(e);
  return out;
}

function discrepancyBlock(e){
  if (!e.discrepancies || !e.discrepancies.length) return "";
  return `<div class="card"><h2>What the record and the patient disagree about</h2>
    <div class="note" style="margin:0 0 10px">Surfaced, never resolved. Both sources are
      routinely wrong in different ways — a record goes stale the moment a patient buys
      something at a pharmacy, and a patient misremembers a dose. Picking a winner would be
      guessing about what someone is currently swallowing.</div>
    ${e.discrepancies.map(d=>`<div class="finding ${d.material?"":"warn"}">
      <div class="m">${esc(d.text)}</div>
      ${d.record_says||d.patient_says?`<div class="src">Record: ${esc(d.record_says||"—")}
        &nbsp;·&nbsp; Patient: ${esc(d.patient_says||"—")}</div>`:""}
      ${d.interacts_with.length?`<div class="src">Interacts with what they already take:
        ${d.interacts_with.map(esc).join(", ")}</div>`:""}
    </div>`).join("")}</div>`;
}

function auditView(e){
  const p = e.patient;
  if (e.error) {
    return `<div class="err"><b>No draft was produced, so the safety checks never ran.</b>
      <span class="mono">${esc(e.error)}</span>
      <div class="plain" style="margin-top:8px">The failure is recorded against this visit and
      goes no further. The nine checks sit after the draft, so there was nothing for them to
      check.</div></div>`;
  }
  const steps = (G.path_steps)||{};
  const checks = e.checks.map(c=>`<div class="chk ${c.findings.length?"hit":"ok"}">
      <div class="mark">${c.findings.length?"✕":"✓"}</div>
      <div><div class="ttl">${c.number}. ${esc(c.title)}${c.findings.length
        ?` <span class="tag flag">stopped it</span>`:``}</div>
        <div class="plain">${esc(c.description)}</div></div></div>`).join("");

  const findings = e.findings.length ? e.findings.map(f=>`<div class="finding ${f.severity}">
      <div class="src">Check ${f.check} — ${esc(f.check_name.replace(/_/g," "))}
        &middot; rule <span class="mono">${esc(f.rule_id||"")}</span>
        ${f.converts_to_referral?" &middot; means: send the patient elsewhere":""}</div>
      <div class="m">${esc(f.message)}</div>
      ${f.citation?`<div class="src">Source: ${esc(f.citation)}</div>`:""}
    </div>`).join("") : `<div class="plain">No check raised anything.</div>`;

  const prov = e.proposal?e.proposal.provenance:(e.signature?e.signature.provenance:null);
  const trail = e.trail[e.trail.length-1]===e.outcome.toUpperCase()?e.trail:e.trail.concat([e.outcome.toUpperCase()]);

  return `<div class="card">
      <h2>What happened, step by step</h2>
      <div class="trail">${trail.map(t=>`<span class="mono">${esc(t)}</span>`).join("")}</div>
      <div class="steps">${trail.map(t=>steps[t]?`<div><b class="mono">${esc(t)}</b> — ${esc(steps[t])}</div>`:"").join("")}</div>
    </div>
    <div class="card">
      <h2>The nine safety checks</h2>
      <div class="note" style="margin:0 0 10px">All nine run on every draft, in plain code with no AI
        involved. They do not stop at the first problem — a doctor reviewing a rejected draft should
        see everything that was wrong with it.</div>
      ${checks}
    </div>
    <div class="card">
      <h2>What the checks found</h2>
      ${findings}
    </div>
    ${discrepancyBlock(e)}
    <div class="card">
      <h2>What this hospital can actually do</h2>
      <table>
        ${row("Hospital", `${esc(p.site_id)} — ${esc(p.site_label)}`)}
        ${row("Blood tests on site", `<span class="mono">${p.labs_available.map(esc).join(", ")||"none"}</span>`)}
        ${row("Drugs in stock", `<span class="mono">${p.stocked.map(esc).join(", ")||"none"}</span>`)}
        ${row("Information current as of", esc(p.site_as_of))}
      </table>
      ${p.evidence && p.evidence.length ? `<h3>Proof each service was actually delivered</h3>
        <table><thead><tr><th style="width:auto">Service</th>
          <th style="width:auto">Last performed</th><th style="width:auto">Last 30 days</th></tr></thead>
        ${p.evidence.map(e=>`<tr><td>${esc(e.label)}</td>
          <td>${e.last_performed?esc(e.last_performed):`<span style="color:var(--amber)">never recorded</span>`}</td>
          <td class="mono">${e.volume_30d}</td></tr>`).join("")}</table>
        <div class="note">Naming a service is not the same as delivering it. A capability listed
          with nothing behind it is the stale-registry failure this check exists to catch.</div>`:""}
      <div class="note">A plan is only a plan if this hospital can carry it out. A drug the pharmacy
        does not stock, or a test that has to travel to another island, makes the output a referral
        rather than a recommendation.</div>
    </div>
    ${prov?`<div class="card"><h2>Where this came from</h2><table>
      ${row("AI model", `<span class="mono">${esc(prov[0])}</span>`)}
      ${row("Prompt version", `<span class="mono">${esc(prov[1])}</span>`)}
      ${row("Rule set version", `<span class="mono">${esc(prov[2])}</span>`)}</table>
      <div class="note">Three separate pins. The model and the prompt change far more often than a
        medical guideline does, so a problem in either has to be traceable to the exact draft it
        produced.</div></div>`:""}`;
}

function draw(){
  const e = DATA.encounters[current];
  document.querySelectorAll(".enc").forEach(b=>b.setAttribute("aria-current", +b.dataset.i===current));
  document.getElementById("main").innerHTML =
    `<div class="hd">${esc(e.title)}</div>
     <div class="sub">${esc(e.note)}</div>
     <div style="margin-bottom:14px">
       <span class="outcome ${e.error?"fail":e.presentation.band}">${esc(e.outcome.replace(/_/g," "))}</span>
       <div class="plain" style="margin-top:6px">${esc(e.outcome_plain)}</div>
     </div>
     ${patientCard(e)}
     <div class="tabs">
       <button class="tab" data-view="clinician" aria-selected="${view==="clinician"}">What the doctor sees</button>
       <button class="tab" data-view="audit" aria-selected="${view==="audit"}">What the system did</button>
     </div>
     <div id="body">${view==="clinician"?clinicianView(e):auditView(e)}</div>`;
  document.querySelectorAll(".tab").forEach(t=>t.onclick=()=>{view=t.dataset.view;draw();});
  document.querySelectorAll("[data-ack]").forEach(b=>b.onclick=()=>{acked[b.dataset.ack]=true;draw();});
}
meta(); nav(); draw();
</script>
</body>
</html>
"""
