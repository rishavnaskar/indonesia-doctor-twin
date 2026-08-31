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
/* Palette and type follow the house system: warm paper, near-black ink, one
   ember accent. Light only, deliberately — the references commit to a single
   look rather than hedging with a dark variant that nobody tunes. */
:root {
  color-scheme: light;
  --paper:#f7f6f8; --paper-warm:#efece7; --panel:#fff;
  --ink:#0b0b0c; --graphite:#4c4c52; --ash:#68686f;
  --line:#e2ded7; --line-soft:#eeebe5;
  --ember:#f0521c; --ember-deep:#b93714;
  --green:#14684a; --amber:#8a5a12; --red:#b3261e;
  --green-bg:#edf4f0; --amber-bg:#f8f1e4; --red-bg:#fbedec; --code:#f1efea;
  --shell:1180px;
}
* { box-sizing:border-box; }
body { margin:0; background:var(--paper); color:var(--ink);
  font:15px/1.6 "DM Sans",-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
  -webkit-font-smoothing:antialiased; }
.mono,code { font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
  font-size:12.5px; }

/* Small monospaced label that names a section. Used instead of a heavier
   heading so the eye finds structure without the page shouting. */
.eyebrow { font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:11px;
  letter-spacing:.16em; text-transform:uppercase; font-weight:500; color:var(--ash);
  margin:0 0 14px; }

a, a:visited { color:var(--ink); text-underline-offset:3px;
  text-decoration-color:color-mix(in srgb, var(--ink) 30%, transparent); }
a:hover { text-decoration-color:var(--ember); }
a:focus-visible { outline:2px solid var(--ember); outline-offset:2px; border-radius:2px; }

header { padding:44px 30px 0; border-bottom:1px solid var(--line); background:var(--panel); }
.hin { max-width:none; }
.htop { display:grid; grid-template-columns:minmax(0,1fr) minmax(320px,520px);
  gap:40px 72px; align-items:start; }
@media (max-width:860px){ .htop{ grid-template-columns:1fr; gap:28px; } }
h1 { margin:0 0 16px; font-size:clamp(2rem,4.2vw,3.1rem); font-weight:500;
  letter-spacing:-.035em; line-height:.98; text-wrap:balance; }
.lede { color:var(--graphite); font-size:clamp(1rem,1.2vw,1.08rem); line-height:1.55;
  max-width:52ch; text-wrap:pretty; margin:0; }
.cta { display:inline-block; margin-top:20px; font-weight:500; font-size:14.5px;
  text-decoration:none; border-bottom:1px solid var(--ember); padding-bottom:2px; }
.cta:hover { color:var(--ember-deep); }

/* The run's facts, as hairline-separated rows rather than a filled box. There
   used to be three stacked callout panels here; three highlighted blocks in a
   row is the page insisting on all of it at once, which reads as none of it. */
.facts { border-top:1px solid var(--line); }
.facts .row { display:flex; justify-content:space-between; gap:20px;
  padding:9px 0; border-bottom:1px solid var(--line-soft); font-size:13px; }
.facts .k { color:var(--ash); }
.facts .v { text-align:right; font-weight:500; }
.facts .v.mono { font-size:12px; }

.summary { margin:36px 0 0; padding:0; max-width:62ch;
  font-size:clamp(1.05rem,1.6vw,1.3rem); line-height:1.4; letter-spacing:-.015em;
  font-weight:500; text-wrap:balance; }
.summary span { color:var(--ash); font-weight:400; }
.fineprint { max-width:68ch; margin:14px 0 0; padding-bottom:34px; font-size:12.5px;
  line-height:1.6; color:var(--ash); }
.fineprint b { color:var(--graphite); font-weight:500; }

.wrap { display:grid; grid-template-columns:290px 1fr; }
@media (max-width:900px){ .wrap{ grid-template-columns:1fr; } }
nav { border-right:1px solid var(--line); background:var(--panel); }
.trail span { font-family:ui-monospace,SFMono-Regular,Menlo,monospace; }
.enc { display:block; width:100%; text-align:left; border:0; background:none; color:inherit;
  font:inherit; padding:12px 16px; border-bottom:1px solid var(--line); cursor:pointer; }
.enc:hover { background:var(--paper-warm); }
.enc[aria-current="true"] { background:var(--paper-warm); box-shadow:inset 2px 0 0 var(--ember); }
.enc .t { font-weight:600; font-size:13px; margin-bottom:2px; }
.enc .n { color:var(--ash); font-size:11.5px; }
.dot { display:inline-block; width:8px; height:8px; border-radius:50%; margin-right:7px; }
.dot.green{background:var(--green)} .dot.amber{background:var(--amber)} .dot.red{background:var(--red)}
main { padding:26px 30px 60px; max-width:none; min-width:0; }
.hd { font-size:17px; font-weight:650; margin:0 0 3px; }
.hd + .sub { color:var(--graphite); font-size:13px; margin-bottom:14px; }
.outcome { display:inline-block; padding:3px 9px; border-radius:3px;
  font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:10.5px;
  font-weight:500; letter-spacing:.1em; text-transform:uppercase; }
.outcome.green{background:var(--green-bg);color:var(--green)}
.outcome.amber{background:var(--amber-bg);color:var(--amber)}
.outcome.red{background:var(--red-bg);color:var(--red)}
.outcome.fail{background:var(--code);color:var(--graphite)}
.err { border:1px solid var(--line); border-left:3px solid var(--amber); border-radius:8px;
  padding:14px 16px; margin-bottom:14px; background:var(--panel); }
.err b { display:block; margin-bottom:5px; }
.card { background:var(--panel); border:1px solid var(--line); border-radius:4px;
  padding:18px 20px; margin-bottom:14px; }
.card > h2 { margin:0 0 14px; font-family:ui-monospace,SFMono-Regular,Menlo,monospace;
  font-size:11px; text-transform:uppercase; letter-spacing:.16em; color:var(--ash);
  font-weight:500; }
h3 { margin:16px 0 7px; font-size:12px; text-transform:uppercase; letter-spacing:.06em;
  color:var(--ash); font-weight:600; }
h3:first-of-type { margin-top:0; }
.grid2 { display:grid; grid-template-columns:1fr 1fr; gap:0 26px; }
@media (max-width:700px){ .grid2{ grid-template-columns:1fr; } }
table { width:100%; border-collapse:collapse; font-size:13.5px; }
th,td { text-align:left; padding:6px 10px 6px 0; border-bottom:1px solid var(--line); vertical-align:top; }
th { color:var(--ash); font-weight:500; font-size:12px; white-space:nowrap; width:1%; padding-right:18px; }
tr:last-child th, tr:last-child td { border-bottom:0; }
thead th { border-bottom:1px solid var(--line); width:auto; }
.plain { color:var(--graphite); font-size:12.5px; }
.gloss { color:var(--graphite); font-size:12.5px; font-style:italic; margin-top:3px; }
.bi { border-left:2px solid var(--line); padding-left:11px; }
.bi .id { font-size:14px; }
.tag { display:inline-block; padding:1px 7px; border-radius:5px; background:var(--code);
  font-size:11.5px; color:var(--graphite); margin-left:6px; }
.tag.stale { background:var(--amber-bg); color:var(--amber); font-weight:600; }
.tag.flag { background:var(--red-bg); color:var(--red); font-weight:600; }
.band { border-radius:4px; padding:15px 17px; margin-bottom:14px; border:1px solid;
  border-left-width:3px; }
.band.green{background:var(--green-bg);border-color:var(--green)}
.band.amber{background:var(--amber-bg);border-color:var(--amber)}
.band.red{background:var(--red-bg);border-color:var(--red)}
.band .lbl { font-size:11px; text-transform:uppercase; letter-spacing:.08em; font-weight:700; }
.band.green .lbl{color:var(--green)} .band.amber .lbl{color:var(--amber)} .band.red .lbl{color:var(--red)}
.band .h { font-size:15px; font-weight:650; margin-top:4px; }
.band ul { margin:10px 0 0; padding-left:18px; } .band li { margin-bottom:6px; }
.empty { border:1px dashed var(--line); border-radius:10px; padding:26px 20px; text-align:center;
  color:var(--graphite); font-size:13px; margin-bottom:14px; }
.empty b { display:block; color:var(--ink); font-size:14.5px; margin-bottom:5px; }
.tabs { display:flex; gap:2px; margin:18px 0 14px; border-bottom:1px solid var(--line); }
.tab { border:0; background:none; color:var(--graphite); font:inherit; font-size:13.5px;
  padding:8px 14px; cursor:pointer; border-bottom:2px solid transparent; margin-bottom:-1px; }
.tab[aria-selected="true"]{ color:var(--ember); border-bottom-color:var(--ember); font-weight:650; }
.chk { display:flex; gap:10px; padding:8px 0; border-bottom:1px solid var(--line); font-size:13px; }
.chk:last-child{border-bottom:0}
.chk .mark { flex:0 0 20px; font-weight:700; }
.chk.ok .mark{ color:var(--green) } .chk.hit .mark{ color:var(--red) }
.chk .ttl { font-weight:600; }
.finding { border-left:3px solid var(--red); padding:2px 0 2px 12px; margin-bottom:12px; }
.finding.warn { border-left-color:var(--amber); }
.finding .m { margin:3px 0; }
.finding .src { color:var(--ash); font-size:11.5px; }
.watch { font-size:13px; color:var(--graphite); border-left:3px solid var(--ember);
  padding-left:12px; margin:0 0 14px; }
.trail { display:flex; flex-wrap:wrap; gap:5px; margin-bottom:4px; }
.trail span { background:var(--code); padding:3px 8px; border-radius:5px; font-size:11px; }
.steps { font-size:12.5px; color:var(--graphite); }
.steps div { padding:3px 0; }
button.act { font:inherit; font-size:13px; font-weight:650; padding:7px 15px; border-radius:7px;
  border:1px solid var(--red); background:var(--red); color:#fff; cursor:pointer; margin-top:12px; }
button.act[disabled]{ background:transparent; color:var(--graphite); border-color:var(--line); font-weight:500; }
.note { font-size:12.5px; color:var(--ash); margin-top:10px; }
.bpnow { font-size:26px; font-weight:650; letter-spacing:-.02em; }
.bpnow small { font-size:13px; font-weight:400; color:var(--graphite); }
</style>
</head>
<body>
<header>
  <div class="hin">
    <div class="htop">
      <div>
        <p class="eyebrow" id="eyebrow"></p>
        <h1>A doctor&rsquo;s assistant.<br>Not a doctor.</h1>
        <p class="lede">It drafts the plan for a return visit. A licensed doctor signs every
          one. Nine checks sit in between &mdash; plain code, no model &mdash; and any one of
          them stops the draft before anyone sees it. Nothing on this page was written by hand.</p>
        <a class="cta" href="/clinic">Build your own patient and run it &rarr;</a>
      </div>
      <div class="facts" id="facts"></div>
    </div>
    <p class="summary" id="stat"></p>
    <p class="fineprint" id="fineprint"></p>
  </div>
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
  const p = DATA.pack, st = DATA.store || {};
  // Named by the pack, so adding a third pathway changes this line without
  // anyone editing the surface.
  document.getElementById("eyebrow").textContent =
    (DATA.pathways || []).map(x => x.label).join("  \u00b7  ") + "  \u00b7  follow-up visits";
  // Facts as hairline rows, not a filled panel. Everything here is read off a
  // real run — the drafter's name included, so a page claiming a model wrote
  // something is a page the model actually wrote.
  const rows = [
    ["Drafted by", DATA.reasoner, true],
    ["Rules pack", p.pack_id + " " + p.version, true],
    ["Clinical sign-off", p.review_status.replace(/_/g, " "), false],
    ["Drugs on the list", p.molecule_count, false],
    ["Hospitals modelled", p.site_count, false],
    ["Patient language", p.language, false],
    ["State kept in", st.location || "memory only", true],
    ["On record", `${st.encounters_checkpointed} visits, ${st.signatures} signatures`, false],
    ["This page", DATA.resumed
      ? `${DATA.resumed} of ${DATA.total} replayed, not re-run` : "every visit run fresh", false],
    ["Run at", DATA.generated_at, true],
  ];
  document.getElementById("facts").innerHTML = rows.map(([k, v, mono]) =>
    `<div class="row"><span class="k">${esc(k)}</span>
      <span class="v${mono ? " mono" : ""}">${esc(v)}</span></div>`).join("");

  const fails = DATA.drafter_failures || 0;
  document.getElementById("stat").innerHTML =
    `${DATA.declined} of these ${DATA.total} visits ended with no plan reaching the doctor.
     <span>That is the system working. Every refusal says why.</span>` +
    (fails ? ` <span>${fails} more could not be drafted at all &mdash; the model returned
      something unusable. Different failure, counted separately.</span>` : "");

  // Quiet, not a callout. The point is that a reader who wonders about it finds
  // the answer, not that everyone is stopped and told.
  const notes = [];
  if (DATA.hosted) {
    notes.push(`<b>Public demo, synthetic patients only.</b> Health data has to stay in
      Indonesia and this server does not. So nothing real is on it, and a record that is not
      marked synthetic never leaves the machine &mdash; the check runs before the request is
      built, not after.`);
  }
  if (!DATA.is_model) {
    notes.push(`<b>Drafted by rule-following code, not a model.</b> That is the default: free,
      instant, and identical every run, so a change in behaviour is a real change rather than
      the model having a different day. A real model plugs into the same interface and nothing
      downstream moves.`);
  }
  document.getElementById("fineprint").innerHTML = notes.join(" ");
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
    `<li>${esc(l.text)}${l.rule_id?` <span class="src mono">[rule ${esc(l.rule_id)}]</span>`:""}
       ${l.gloss?`<div class="gloss">${esc(l.gloss)}</div>`:""}</li>`).join("")}</ul>` : "";
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
      <div>${esc(d.patient_instructions_gloss || d.patient_instructions)}</div>
      ${d.patient_instructions_gloss?`<div class="gloss">${esc(d.patient_instructions)}
        <span class="tag">as sent, in ${esc(DATA.pack.language)}</span></div>`:""}`:""}
    ${e.signature?`<h3>Signature</h3><table>
      ${row("Signed by", `${esc(e.signature.practitioner_id)} — ${esc(e.signature.role)}`)}
      ${row("Licence valid until", esc(e.signature.licence_expires))}
      ${row("Decision", esc(e.signature.decision))}</table>
      <div class="note">The signature is refused in software if the licence has lapsed or the
      doctor is not on this hospital's roster.</div>`:""}
  </div>`;
}

function exclusionBlock(e){
  if (!e.exclusions || !e.exclusions.length) return "";
  return `<div class="band amber">
    <div class="lbl">Out of scope</div>
    <div class="h">${esc(e.message || "Not handled by the assistant.")}</div>
    <ul>${e.exclusions.map(x=>`<li><b>${esc(x.label)}</b>
      <span class="src mono">[${esc(x.id)}]</span>
      <div class="gloss">${esc(x.reason)}</div></li>`).join("")}</ul>
    <div class="note" style="margin-top:8px">A handoff is a terminal state that
      counts as a success. The clinician gets the encounter untouched, with a
      stated reason and no clinical content from us.</div></div>`;
}

function clinicianView(e){
  const p = e.presentation;
  let out = `<p class="watch">${esc(e.watch_for)}</p>`;
  if (e.exclusions && e.exclusions.length) return out + exclusionBlock(e);
  if (e.error) {
    return out + `<div class="err"><b>The drafter failed on this visit.</b>
      <span class="mono">${esc(e.error)}</span>
      <div class="plain" style="margin-top:8px">Nothing reached the checks. Nothing reached the
      doctor. The consultation carries on as if the system were not there.
      Weak models return junk sometimes. That should cost one visit, not the whole page.</div></div>`;
  }
  if (p.silent && p.shows_draft) {
    out += `<div class="empty"><b>No alert.</b>
      Nothing here needed the doctor's attention, so the system says nothing. No summary,
      no tick, no &ldquo;all clear&rdquo;. The draft is just waiting in the consultation form.
      Most visits look like this. The quiet is what makes a warning mean something.</div>`;
  } else if (p.silent) {
    out += `<div class="empty"><b>The doctor sees nothing at all.</b>
      The checks refused the draft. There was nothing here to act on, so nobody is
      interrupted to be told that. The reasons are logged either way &mdash; they are
      under &ldquo;What the system did&rdquo;.</div>`;
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
      ${f.message_local?`<div class="gloss">${esc(f.message_local)}</div>`:""}
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
    ${e.proposal && e.proposal.concerns && e.proposal.concerns.length ? `<div class="card">
      <h2>Raised by the drafter, not by a rule</h2>
      <div class="note" style="margin:0 0 10px">The deterministic red flags are the
        floor and catch what somebody enumerated. This is the channel for something
        those rules were never written to look for. It can only add to what the
        clinician sees — it cannot quieten an alert or mark a patient as fine.</div>
      ${e.proposal.concerns.map(c=>`<div class="finding ${c.urgency==="escalate"?"":"warn"}">
        <div class="src">${c.urgency === "escalate" ? "Escalate" : "Mention"}</div>
        <div class="m">${esc(c.text)}</div></div>`).join("")}</div>` : ""}
    ${e.exclusions && e.exclusions.length ? `<div class="card">
      <h2>Why this patient is out of scope</h2>
      ${e.exclusions.map(x=>`<div class="finding">
        <div class="src">Exclusion ${esc(x.id)} — checked before any model call</div>
        <div class="m"><b>${esc(x.label)}</b></div>
        <div class="src">${esc(x.reason)}</div></div>`).join("")}
      <div class="note">An excluded encounter costs zero tokens. That is a nice
        property and not the point: deciding "this patient is not ours" is a rules
        decision, and asking a model to notice it should not be involved is
        strictly worse than checking.</div></div>` : ""}
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
        <div class="note">Claiming a service is not the same as providing it. A capability with
          nothing behind it is the stale registry this check exists to catch.</div>`:""}
      <div class="note">A plan only counts if this hospital can carry it out. If the pharmacy has
        no stock, or the test has to travel to another island, the answer is a referral.</div>
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
