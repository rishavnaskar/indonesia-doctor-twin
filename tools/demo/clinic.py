"""The interactive surface: build a patient, then run the clinician.

Kept apart from render.py because it is a different thing. That page is a
record of a run; this one is a place to poke the system and watch it react.
Both drive the identical pipeline — a demo whose interactive mode took a
different path through the system would be demonstrating something other
than the system.
"""

CLINIC_HTML = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AI clinician — build a patient</title>
<style>
:root{--bg:#f5f6f8;--panel:#fff;--ink:#14171a;--muted:#5f6871;--faint:#66707c;--line:#dfe3e8;
--accent:#1c4fd8;--on-accent:#fff;--soft:#eef2fe;--green:#1a7f4b;--amber:#8f5a00;--red:#b3261e;
--green-bg:#eaf6ef;--amber-bg:#fdf3e2;--red-bg:#fceceb;--code:#eef1f4}
@media (prefers-color-scheme:dark){:root{--bg:#131619;--panel:#1b1f23;--ink:#e8eaed;--muted:#9aa4ae;
--faint:#98a1ab;--line:#2b3137;--accent:#7da2ff;--on-accent:#10141a;--soft:#1d2536;--green:#6ed99b;--amber:#ecb75a;
--red:#f0857c;--green-bg:#16281f;--amber-bg:#2a2418;--red-bg:#2c1b1a;--code:#22272c}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
.mono,code{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:12.5px}
header{padding:18px 26px;border-bottom:1px solid var(--line);background:var(--panel)}
h1{margin:0 0 4px;font-size:18px}
.lede{color:var(--muted);font-size:13.5px;max-width:88ch}
a,a:visited{color:var(--accent)}
a:focus-visible{outline:2px solid var(--accent);outline-offset:2px;border-radius:2px}
main{padding:20px 26px;max-width:1180px}
.bar{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px 16px;
margin-bottom:16px;display:flex;flex-wrap:wrap;gap:12px 18px;align-items:flex-end}
/* A select sizes to its longest option, and these options are sentences. On a
   narrow screen that pushed the whole page sideways. */
.bar > div{min-width:0}
.bar select{max-width:100%}
@media (max-width:560px){
  .bar{flex-direction:column;align-items:stretch}
  .bar > div{width:100%}
  .bar button{width:100%}
  select,input[type=number],input[type=text]{width:100%}
  input[type=number]{width:100%}
  main{padding:16px 14px}
  .row > div{flex:1 1 40%}
}
label.f{display:block;font-size:11.5px;text-transform:uppercase;letter-spacing:.06em;
color:var(--faint);margin-bottom:4px;font-weight:600}
select,input[type=number],input[type=text],textarea{font:inherit;font-size:13.5px;padding:6px 8px;
border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--ink)}
input[type=number]{width:78px}
button{font:inherit;font-size:13.5px;font-weight:600;padding:8px 16px;border-radius:7px;
border:1px solid var(--accent);background:var(--accent);color:var(--on-accent);cursor:pointer}
button.ghost{background:transparent;color:var(--accent)}
button[disabled]{opacity:.5;cursor:default}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:14px}
.p{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px 16px}
.p h3{margin:0 0 10px;font-size:13.5px;display:flex;justify-content:space-between;align-items:center}
.rm{border:0;background:none;color:var(--faint);font-size:16px;padding:0 6px;cursor:pointer;
line-height:1;font-weight:400}
.rm:hover{color:var(--red)}
.row{display:flex;gap:8px;flex-wrap:wrap;align-items:flex-end;margin-bottom:10px}
.sec{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--faint);
font-weight:600;margin:12px 0 6px}
.chips{display:flex;flex-wrap:wrap;gap:5px}
.chip{font-size:11.5px;padding:3px 9px;border-radius:20px;border:1px solid var(--line);
background:var(--bg);cursor:pointer;user-select:none;color:var(--muted)}
.chip.on{background:var(--red-bg);border-color:var(--red);color:var(--red);font-weight:600}
.chip.on.flag{background:var(--soft);border-color:var(--accent);color:var(--accent)}
.med{display:flex;gap:6px;align-items:center;margin-bottom:6px}
.med select{flex:1}
.verdict{margin-top:12px;border-top:1px solid var(--line);padding-top:11px}
.pill{display:inline-block;padding:3px 10px;border-radius:20px;font-size:11px;font-weight:700;
letter-spacing:.04em;text-transform:uppercase}
.pill.green{background:var(--green-bg);color:var(--green)}
.pill.amber{background:var(--amber-bg);color:var(--amber)}
.pill.red{background:var(--red-bg);color:var(--red)}
.pill.fail{background:var(--code);color:var(--muted)}
.plain{color:var(--muted);font-size:12.5px}
.find{border-left:3px solid var(--red);padding-left:10px;margin:8px 0;font-size:12.5px}
.find.warn{border-left-color:var(--amber)}
.find .src{color:var(--faint);font-size:11px}
.stat{background:var(--soft);border:1px solid var(--line);border-radius:8px;padding:11px 15px;
margin-bottom:16px;font-size:13.5px}
.err{background:var(--red-bg);border:1px solid var(--red);border-radius:8px;padding:11px 15px;
margin-bottom:16px;font-size:13.5px}
.tog{display:flex;align-items:center;gap:6px;font-size:12.5px;color:var(--muted)}
details{margin-top:8px}summary{cursor:pointer;font-size:12.5px;color:var(--accent)}
body.busy .p{opacity:.75}
body.busy input,body.busy select,body.busy textarea{pointer-events:none;background:var(--code);color:var(--muted)}
body.busy .chip,body.busy .rm,body.busy button{pointer-events:none;opacity:.55}
body.busy #msg{opacity:1}
.pipe{display:flex;flex-wrap:wrap;gap:4px;margin-top:10px}
.pipe span{font-size:10.5px;padding:2px 7px;border-radius:4px;background:var(--code);
color:var(--faint);font-family:ui-monospace,Menlo,monospace}
.pipe span.at{background:var(--accent);color:#fff;font-weight:700}
.pipe span.past{background:var(--soft);color:var(--accent)}
.working{font-size:12px;color:var(--accent);font-weight:600;margin-top:8px;display:flex;
align-items:center;gap:7px}
.spin{width:11px;height:11px;border:2px solid var(--line);border-top-color:var(--accent);
border-radius:50%;animation:sp .7s linear infinite}
@keyframes sp{to{transform:rotate(360deg)}}
.chk{display:flex;gap:8px;padding:5px 0;border-bottom:1px solid var(--line);font-size:12px}
.chk:last-child{border-bottom:0}
.chk .mk{flex:0 0 14px;font-weight:700}
.chk.ok .mk{color:var(--green)}.chk.hit .mk{color:var(--red)}
.kv{display:flex;gap:8px;font-size:12px;padding:3px 0}
.kv b{color:var(--faint);font-weight:500;min-width:96px}
textarea{width:100%;min-height:120px;font-family:ui-monospace,Menlo,monospace;font-size:12px}
.warnbox{background:var(--amber-bg);border:1px solid var(--amber);border-radius:8px;
padding:11px 15px;margin-bottom:12px;font-size:12.5px}
.cmp{background:var(--panel);border:1px solid var(--line);border-radius:10px;
padding:16px 18px;margin-bottom:16px}
.cmp h3{margin:0 0 4px;font-size:14px}
.cmp table{width:100%;border-collapse:collapse;font-size:12.5px;margin-top:10px}
.cmp th,.cmp td{text-align:left;padding:6px 10px 6px 0;border-bottom:1px solid var(--line)}
.cmp th{color:var(--faint);font-weight:500;font-size:11.5px}
.cmp tr.diff td{background:var(--soft)}
.cmp .o{font-weight:600}
.cmp .o.committed{color:var(--green)}
.cmp .o.abstain,.cmp .o.handoff{color:var(--muted)}
.cmp .o.escalate{color:var(--red)}
.cmp .o.request_info{color:var(--amber)}
</style></head><body>
<header>
<h1>Build a patient, then run the clinician</h1>
<div class="lede">Generate or edit patients, change anything about them, and watch what the
system does. The same pipeline as the <a href="/">scripted scenarios</a> — same nine checks,
same gate, same signature rule. Change a blood pressure, add a symptom, move the patient to a
hospital without a potassium assay, and the verdict moves with it.</div>
</header>
<main>
<div class="bar">
  <div><label class="f">How many</label><input type="number" id="n" value="3" min="1" max="12"></div>
  <div><label class="f">Starting profile</label><select id="profile"></select></div>
  <div><label class="f">Hospital</label><select id="site"></select></div>
  <div><button id="gen">Generate patients</button></div>
  <div><button class="ghost" id="add">Add a blank one</button></div>
  <div style="flex:1"></div>
  <div class="tog"><input type="checkbox" id="live"><label for="live">Draft with a real AI model</label></div>
  <div><button id="run" disabled>Run the AI clinician</button></div>
  <div><button class="ghost" id="compare" disabled title="Run these patients at every hospital">Compare hospitals</button></div>
</div>
<div id="restored"></div>
<div id="msg"></div>
<div class="grid" id="grid"></div>
<details style="margin-top:20px"><summary>Paste a patient record as JSON</summary>
  <div class="warnbox"><b>Records are not marked synthetic unless you say so.</b>
  A record without <code>"is_synthetic": true</code> will be refused by the residency guard
  before any request is built, because health data must be processed in-country and a hosted
  model is outside that boundary. That refusal is the guard working. Use the deterministic
  reasoner for records you have not marked.</div>
  <textarea id="paste" placeholder='[{"patient_id":"X1","age":54,"sex":"M","is_synthetic":true,
 "observations":[{"code":"sbp","value":168,"age_days":0},{"code":"dbp","value":98,"age_days":0}],
 "medications":[{"molecule":"amlodipine","mg_per_dose":5,"doses_per_day":1}],
 "diagnoses":["I10"],"flags":{"on_antihypertensive_treatment":true}}]'></textarea>
  <button class="ghost" id="load" style="margin-top:8px">Load these</button>
</details>
</main>
<script>
let V = null, patients = [], results = {};
let running = false, live_steps = {}, finished_steps = {};
const esc = s => String(s==null?"":s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const $ = id => document.getElementById(id);
const off = () => running ? " disabled" : "";
const obsOf = (p,code) => (p.observations||[]).find(o=>o.code===code) || null;

function setObs(p, code, value, ageDays){
  p.observations = (p.observations||[]).filter(o=>o.code!==code);
  if (value !== "" && value !== null && !isNaN(value))
    p.observations.push({code, value:Number(value), age_days:Number(ageDays||0)});
}

async function boot(){
  V = await (await fetch("/api/vocabulary")).json();
  $("profile").innerHTML = V.profiles.map(p=>`<option value="${esc(p.key)}">${esc(p.label)}</option>`).join("");
  $("site").innerHTML = V.sites.map(s=>
    `<option value="${esc(s.site_id)}">${esc(s.site_id)} — ${esc(s.label)}</option>`).join("");
  await restore();
}

// Everything run here in an earlier session, read back from the store. This
// page used to keep its results in a dict in the server process and its
// patients in the tab, so closing either one lost the work — while the store
// had been recording all of it and nothing ever read it back.
async function restore(){
  let h;
  try { h = await (await fetch("/api/history")).json(); }
  catch (e) { return; }                      // a page that cannot restore still works
  const visits = (h.visits||[]).filter(v=>v.wire);
  if (!visits.length) return;

  patients = visits.map(v=>v.wire);
  visits.forEach(v=>{ results[v.key] = v; });
  draw();

  const last = visits[0].ran_at || "";
  $("restored").innerHTML = `<div class="stat">
    <b>${visits.length} visit(s) restored from ${esc(h.backend)}</b>
    <span class="mono">${esc(h.location||"")}</span>. Last run ${esc(last.replace("T"," ").slice(0,19))}.
    These are the patients and verdicts from earlier sessions — edit and re-run any of them.
    <button class="ghost" id="forget" style="margin-left:10px">Clear this list</button>
    </div>`;
  $("forget").onclick = async ()=>{
    // Nothing is deleted. The store refuses UPDATE and DELETE, so clearing
    // writes a marker forward and the page starts after it — the visits stay on
    // the record and `python -m tools.store` still replays them. An audit log
    // with a working clear button would not be an audit log.
    await fetch("/api/history/clear", {method:"POST", body:"{}"});
    patients = []; results = {};
    $("restored").innerHTML = `<div class="stat">List cleared from this page. Nothing was
      deleted — the store is append-only, so every visit is still on the record and still
      replayable with <span class="mono">python -m tools.store</span>.</div>`;
    draw();
  };
}

function medRow(p, i){
  const m = p.medications[i];
  return `<div class="med">
    <select data-p="${p._i}" data-med="${i}" data-k="molecule"${off()}>
      ${V.molecules.map(x=>`<option value="${esc(x.molecule)}"${x.molecule===m.molecule?" selected":""}>${esc(x.molecule)}</option>`).join("")}
    </select>
    <input type="number" step="0.5" value="${m.mg_per_dose}" data-p="${p._i}" data-med="${i}" data-k="mg_per_dose" title="mg per dose"${off()}>
    <input type="number" value="${m.doses_per_day}" style="width:56px" data-p="${p._i}" data-med="${i}" data-k="doses_per_day" title="doses per day"${off()}>
    <button class="rm" data-rmmed="${p._i}:${i}"${off()}>&times;</button></div>`;
}

const STEPS = ["ELIGIBLE","INTAKE","RECONCILE","PROPOSE","GATE","PRESENT","SIGNED","COMMIT"];

function pipeline(p){
  // Only ever shows steps the workflow actually reported. Nothing here is
  // animated ahead of the system.
  const at = live_steps[p._i + 1];
  const finished = results[p.patient_id];
  let reached = finished ? (finished.trail || []) : [];
  const idx = at ? STEPS.indexOf(at) : -1;
  return `<div class="pipe">${STEPS.map((sName,i)=>{
    const cls = at && sName===at ? "at" : (idx>i || reached.includes(sName)) ? "past" : "";
    return `<span class="${cls}">${sName}</span>`;
  }).join("")}</div>`;
}

function auditPanel(r){
  const checks = (r.checks||[]).map(c=>`<div class="chk ${c.findings.length?"hit":"ok"}">
    <div class="mk">${c.findings.length?"\u2715":"\u2713"}</div>
    <div><b>${c.number}. ${esc(c.title)}</b>
    <div class="plain">${esc(c.description)}</div></div></div>`).join("");
  const prov = r.proposal ? r.proposal.provenance : (r.signature ? r.signature.provenance : null);
  const site = r.patient;
  return `<details><summary>How do I know it actually checked?</summary>
    <div class="sec">Path taken</div>
    <div class="pipe">${(r.trail||[]).map(t=>`<span class="past">${esc(t)}</span>`).join("")}</div>
    <div class="sec">The nine checks — plain code, no AI</div>${checks}
    <div class="sec">What this hospital can do</div>
    <div class="kv"><b>Hospital</b><span>${esc(site.site_id)} — ${esc(site.site_label)}</span></div>
    <div class="kv"><b>Labs on site</b><span class="mono">${site.labs_available.map(esc).join(", ")||"none"}</span></div>
    <div class="kv"><b>Drugs stocked</b><span class="mono">${site.stocked.map(esc).join(", ")||"none"}</span></div>
    <div class="kv"><b>Current as of</b><span>${esc(site.site_as_of)}</span></div>
    ${prov?`<div class="sec">Where the draft came from</div>
      <div class="kv"><b>AI model</b><span class="mono">${esc(prov[0])}</span></div>
      <div class="kv"><b>Prompt version</b><span class="mono">${esc(prov[1])}</span></div>
      <div class="kv"><b>Rule set</b><span class="mono">${esc(prov[2])}</span></div>`:""}
    ${r.signature?`<div class="sec">Signature</div>
      <div class="kv"><b>Signed by</b><span>${esc(r.signature.practitioner_id)} (${esc(r.signature.role)})</span></div>
      <div class="kv"><b>Licence to</b><span>${esc(r.signature.licence_expires)}</span></div>`:""}
  </details>`;
}

function verdict(p){
  const r = results[p.patient_id];
  if (running) {
    const at = live_steps[p._i + 1], fin = finished_steps[p._i + 1];
    if (!fin) return `<div class="verdict"><div class="working"><span class="spin"></span>
      ${at ? esc(at === "PROPOSE" ? "Drafting — waiting on the model" : "Working: " + at) : "Queued"}</div>
      ${pipeline(p)}</div>`;
  }
  if (!r) return "";
  if (r.error) return `<div class="verdict"><span class="pill fail">drafter failed</span>
    <div class="plain" style="margin-top:6px"><span class="mono">${esc(r.error)}</span></div></div>`;
  const findings = r.findings.map(f=>`<div class="find ${f.severity}">
      <div class="src">Check ${f.check} · ${esc(f.rule_id||"")}</div>
      ${esc(f.message)}
      ${f.message_local?`<div class="src" style="font-style:italic">${esc(f.message_local)}</div>`:""}</div>`).join("");
  const d = r.proposal;
  return `<div class="verdict">
    <span class="pill ${r.presentation.band}">${esc(r.outcome.replace(/_/g," "))}</span>
    <div class="plain" style="margin-top:6px">${esc(r.outcome_plain)}</div>
    ${d && r.presentation.shows_draft ? `<div class="sec">Draft</div>
      <div><b>${esc(d.recommendation.replace(/_/g," "))}</b> — ${esc(d.recommendation_plain)}</div>
      ${d.medication_changes.map(c=>`<div class="plain">${esc(c.action)} ${esc(c.molecule)} ${c.mg_per_dose}mg ×${c.doses_per_day}</div>`).join("")}
      ${r.claim?`<div class="plain">Coded: ${r.claim.codes.map(c=>esc(c.code)).join(", ")}</div>`:""}` : ""}
    ${(r.exclusions||[]).length ? `<div class="sec">Why this patient is out of scope</div>
      ${r.exclusions.map(x=>`<div class="find">
        <div class="src">Exclusion ${esc(x.id)}</div><b>${esc(x.label)}</b>
        <div class="plain">${esc(x.reason)}</div></div>`).join("")}` : ""}
    ${findings ? `<div class="sec">Why the gate stopped it</div>${findings}` : ""}
    ${(r.proposal && r.proposal.concerns || []).length ? `<div class="sec">Raised by the drafter, not by a rule</div>
      ${r.proposal.concerns.map(c=>`<div class="find ${c.urgency==="escalate"?"":"warn"}">
        <div class="src">${c.urgency==="escalate"?"Escalate":"Mention"}</div>${esc(c.text)}</div>`).join("")}` : ""}
    ${(r.discrepancies||[]).length ? `<div class="sec">Record vs what the patient says</div>
      ${r.discrepancies.map(d=>`<div class="find ${d.material?"":"warn"}">${esc(d.text)}
        ${d.record_says||d.patient_says?`<div class="src">Record: ${esc(d.record_says||"—")}
          · Patient: ${esc(d.patient_says||"—")}</div>`:""}
        ${d.interacts_with.length?`<div class="src">Interacts with ${d.interacts_with.map(esc).join(", ")}</div>`:""}
      </div>`).join("")}` : ""}
    ${auditPanel(r)}
  </div>`;
}

function card(p){
  const sbp = obsOf(p,"sbp"), dbp = obsOf(p,"dbp"), k = obsOf(p,"k"), egfr = obsOf(p,"egfr");
  return `<div class="p">
    <h3><span class="mono">${esc(p.patient_id)}</span>
      <button class="rm" data-rm="${p._i}"${off()}>&times;</button></h3>
    <div class="row">
      <div><label class="f">Age</label><input type="number" value="${p.age}" data-p="${p._i}" data-k="age"${off()}></div>
      <div><label class="f">Sex</label><select data-p="${p._i}" data-k="sex"${off()}>
        <option value="M"${p.sex==="M"?" selected":""}>M</option>
        <option value="F"${p.sex==="F"?" selected":""}>F</option></select></div>
      <div><label class="f">Systolic</label><input type="number" value="${sbp?sbp.value:""}" data-p="${p._i}" data-obs="sbp"${off()}></div>
      <div><label class="f">Diastolic</label><input type="number" value="${dbp?dbp.value:""}" data-p="${p._i}" data-obs="dbp"${off()}></div>
    </div>
    <div class="sec">Blood tests — value, and how many days old</div>
    <div class="row">
      <div><label class="f">Potassium</label><input type="number" step="0.1" value="${k?k.value:""}" data-p="${p._i}" data-obs="k"${off()}></div>
      <div><input type="number" value="${k?k.age_days:0}" style="width:64px" data-p="${p._i}" data-age="k" title="days old"${off()}></div>
      <div><label class="f">eGFR</label><input type="number" value="${egfr?egfr.value:""}" data-p="${p._i}" data-obs="egfr"${off()}></div>
      <div><input type="number" value="${egfr?egfr.age_days:0}" style="width:64px" data-p="${p._i}" data-age="egfr" title="days old"${off()}></div>
    </div>
    <div class="sec">Current medication</div>
    ${p.medications.map((_,i)=>medRow(p,i)).join("")}
    <button class="ghost" style="padding:4px 10px;font-size:12px" data-addmed="${p._i}"${off()}>+ drug</button>
    <div class="sec">Symptoms reported today</div>
    <div class="chips">${V.symptoms.map(s=>
      `<span class="chip${p.symptoms&&p.symptoms[s.code]?" on":""}" data-p="${p._i}" data-sym="${esc(s.code)}">${esc(s.plain)}</span>`).join("")}</div>
    <div class="sec">Other facts</div>
    <div class="chips">${V.flags.map(f=>
      `<span class="chip flag${p.flags&&p.flags[f.code]?" on":""}" data-p="${p._i}" data-flag="${esc(f.code)}">${esc(f.plain)}</span>`).join("")}</div>
    ${p.is_synthetic ? "" : `<div class="plain" style="margin-top:10px;color:var(--amber)">
      Not marked synthetic — a hosted model will refuse this record.</div>`}
    ${verdict(p)}</div>`;
}

function setBusy(on){
  running = on;
  document.body.classList.toggle("busy", on);
  // Belt and braces: the class blocks pointer events, and this stops anything
  // reaching a control by keyboard or autofill while the run is in flight.
  ["n","profile","site","gen","add","live","load","paste","compare"].forEach(id=>{
    const el = $(id); if (el) el.disabled = on;
  });
  $("run").textContent = on ? "Running…" : "Run the AI clinician";
  $("run").disabled = on || patients.length === 0;
  $("compare").disabled = on || patients.length === 0;
}

function draw(){
  patients.forEach((p,i)=>p._i=i);
  $("grid").innerHTML = patients.map(card).join("");
  $("run").disabled = running || patients.length === 0;
  $("compare").disabled = running || patients.length === 0;
}

document.addEventListener("input", e=>{
  if (running) return;  // a run must reflect exactly what was submitted
  const t = e.target, i = t.dataset.p;
  if (i === undefined) return;
  const p = patients[+i];
  if (t.dataset.k && t.dataset.med === undefined)
    p[t.dataset.k] = t.dataset.k === "age" ? +t.value : t.value;
  else if (t.dataset.med !== undefined)
    p.medications[+t.dataset.med][t.dataset.k] =
      t.dataset.k === "molecule" ? t.value : +t.value;
  else if (t.dataset.obs) {
    const cur = obsOf(p, t.dataset.obs);
    setObs(p, t.dataset.obs, t.value, cur ? cur.age_days : 0);
  } else if (t.dataset.age) {
    const cur = obsOf(p, t.dataset.age);
    if (cur) cur.age_days = +t.value;
  }
});

document.addEventListener("click", e=>{
  if (running && e.target.closest(".p")) return;
  const t = e.target;
  if (t.dataset.sym !== undefined){
    const p = patients[+t.dataset.p];
    p.symptoms = p.symptoms || {};
    p.symptoms[t.dataset.sym] = !p.symptoms[t.dataset.sym];
    draw(); return;
  }
  if (t.dataset.flag !== undefined){
    const p = patients[+t.dataset.p];
    p.flags = p.flags || {};
    p.flags[t.dataset.flag] = !p.flags[t.dataset.flag];
    draw(); return;
  }
  if (t.dataset.rm !== undefined){ patients.splice(+t.dataset.rm,1); draw(); return; }
  if (t.dataset.addmed !== undefined){
    patients[+t.dataset.addmed].medications.push(
      {molecule:V.molecules[0].molecule, mg_per_dose:5, doses_per_day:1});
    draw(); return;
  }
  if (t.dataset.rmmed !== undefined){
    const [pi,mi] = t.dataset.rmmed.split(":").map(Number);
    patients[pi].medications.splice(mi,1); draw(); return;
  }
});

$("gen").onclick = async ()=>{
  $("msg").innerHTML = "";
  const r = await fetch("/api/generate", {method:"POST", body: JSON.stringify(
    {n:+$("n").value, profile:$("profile").value, seed: Math.floor(Math.random()*9000)})});
  const j = await r.json();
  if (j.error){ $("msg").innerHTML = `<div class="err">${esc(j.error)}</div>`; return; }
  patients = j.patients; results = {}; draw();
};

$("add").onclick = ()=>{
  patients.push({patient_id:`NEW-${patients.length+1}`, age:55, sex:"M", is_synthetic:true,
    diagnoses:["I10"], medications:[], observations:[
      {code:"sbp",value:150,age_days:0},{code:"dbp",value:94,age_days:0}],
    symptoms:{}, flags:{on_antihypertensive_treatment:true}, history:[]});
  draw();
};

const MAX_PASTED = 12;

$("load").onclick = ()=>{
  let parsed;
  try {
    parsed = JSON.parse($("paste").value);
  } catch (err) {
    $("msg").innerHTML = `<div class="err">That is not valid JSON: ${esc(err.message)}</div>`;
    return;
  }

  const rows = Array.isArray(parsed) ? parsed : [parsed];

  // Validate before touching what is on screen. An earlier version assigned
  // first and validated never, so pasting [1,2,3] surfaced a JavaScript
  // internal error — a crash leaking into a place a reader reads as a
  // statement about their data.
  if (!rows.length){
    $("msg").innerHTML = `<div class="err">That JSON is empty — no records to load.
      Nothing on screen was changed.</div>`;
    return;
  }
  if (rows.length > MAX_PASTED){
    $("msg").innerHTML = `<div class="err">${rows.length} records is more than this
      surface runs at once. Paste ${MAX_PASTED} or fewer.</div>`;
    return;
  }
  const bad = rows.findIndex(r => r === null || typeof r !== "object" || Array.isArray(r));
  if (bad !== -1){
    $("msg").innerHTML = `<div class="err">Entry ${bad + 1} is not a patient record — each
      one has to be an object like the example. Nothing on screen was changed.</div>`;
    return;
  }

  patients = rows.map((p,i)=>({
    ...p,
    medications: p.medications || [],
    observations: p.observations || [],
    patient_id: p.patient_id || `UPLOAD-${i+1}`,
  }));
  results = {};
  const unmarked = patients.filter(p => !p.is_synthetic).length;
  $("msg").innerHTML = `<div class="stat">Loaded ${patients.length} record(s).` +
    (unmarked ? ` <b>${unmarked} not marked synthetic</b> — a hosted model will refuse
      those before any request is built. The rule-following reasoner runs them fine.` : "") +
    `</div>`;
  draw();
};

function summarise(j){
  return `<div class="stat">
    <b>${j.declined} of ${j.total} ended with no recommendation reaching the doctor.</b>
    ${j.drafter_failures?` ${j.drafter_failures} could not be drafted at all — the model
      returned something unusable, which is a model failure rather than a clinical one.`:""}
    ${j.residency_refused?` <b>${j.residency_refused} refused before any request was
      built</b> — not marked synthetic, so nothing left the machine.`:""}
    ${j.unreadable?` ${j.unreadable} record(s) could not be read at all.`:""}
    Drafted by <span class="mono">${esc(j.reasoner)}</span>.</div>`;
}

$("run").onclick = async ()=>{
  results = {}; live_steps = {}; finished_steps = {};
  setBusy(true);
  $("msg").innerHTML = `<div class="stat">Running ${patients.length} visit(s). Editing is
    locked until this finishes, so what you see is what was run.</div>`;
  draw();

  const started = await (await fetch("/api/run", {method:"POST", body: JSON.stringify(
    {patients, site_id:$("site").value, live:$("live").checked})})).json();
  if (started.error){
    $("msg").innerHTML = `<div class="err">${esc(started.error)}</div>`; setBusy(false); return;
  }

  while (true) {
    const s = await (await fetch(`/api/job?id=${encodeURIComponent(started.job_id)}`)).json();
    if (s.error){ $("msg").innerHTML = `<div class="err">${esc(s.error)}</div>`; break; }
    live_steps = {}; finished_steps = {};
    Object.entries(s.steps||{}).forEach(([k,v])=>live_steps[+k]=v);
    Object.entries(s.finished||{}).forEach(([k,v])=>finished_steps[+k]=v);
    if (s.ready){
      const j = s.result;
      j.encounters.forEach(e=>results[e.key]=e);
      $("msg").innerHTML = summarise(j);
      break;
    }
    const doneN = Object.keys(finished_steps).length;
    $("msg").innerHTML = `<div class="stat">Running ${doneN} of ${s.total} done ·
      ${s.elapsed}s elapsed. Editing is locked until this finishes.</div>`;
    draw();
    await new Promise(r=>setTimeout(r, 400));
  }
  setBusy(false);
  draw();
};

$("compare").onclick = async ()=>{
  setBusy(true);
  $("msg").innerHTML = `<div class="stat">Running these patients at every hospital…</div>`;
  const j = await (await fetch("/api/compare", {method:"POST", body: JSON.stringify(
    {patients, live:$("live").checked})})).json();
  setBusy(false);
  if (j.error){ $("msg").innerHTML = `<div class="err">${esc(j.error)}</div>`; return; }

  const head = j.sites.map(s=>`<th>${esc(s.site_id)}<div class="plain">${esc(s.label)}</div></th>`).join("");
  const rows = j.patients.map(k=>{
    const cells = j.sites.map(s=>{
      const cell = j.by_site[s.site_id][k];
      return `<td><span class="o ${esc(cell.outcome)}">${esc(cell.outcome.replace(/_/g," "))}</span>
        ${cell.reasons.length?`<div class="plain">${esc(cell.reasons[0].slice(0,90))}</div>`:""}</td>`;
    }).join("");
    return `<tr class="${j.divergent.includes(k)?"diff":""}"><td class="mono">${esc(k)}</td>${cells}</tr>`;
  }).join("");

  $("msg").innerHTML = `<div class="cmp">
    <h3>The same patients, at every hospital</h3>
    <div class="plain">${j.divergent.length} of ${j.patients.length} get a different answer
      depending on where they are standing. That is not inconsistency — a plan is only a plan
      if the hospital in front of the patient can carry it out, so the right answer genuinely
      differs. Highlighted rows are the ones that diverge.</div>
    <table><tr><th>Patient</th>${head}</tr>${rows}</table>
  </div>`;
};

boot();
</script></body></html>
"""
