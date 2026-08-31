"""The site capability registry, rendered.

Gate check 9 is the least legible thing this system does. A reader watching
SITE-C turn a correct plan into a referral is told the site cannot run the
assay, and until now had no way to check that, so the most interesting refusal
in the demo read as an assertion rather than as a consequence of a record.

The page is built from `sites_view()`, which reads the pack and asks the gate's
own `evidence_gap` for the staleness verdicts. Nothing here is written by hand.
"""

from __future__ import annotations

import json
from typing import Any

STYLE = r"""
:root{
--paper:#f7f6f8;--paper-warm:#efece7;--panel:#fff;--ink:#0b0b0c;--graphite:#4c4c52;
--ash:#68686f;--line:#e2ded7;--line-soft:#eeebe5;--ember:#f0521c;--ember-deep:#b93714;
--sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Helvetica,Arial,sans-serif;
--mono:ui-monospace,SFMono-Regular,"SF Mono",Menlo,monospace;
}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);font-family:var(--sans);
  font-size:15px;line-height:1.55;-webkit-font-smoothing:antialiased}
header{padding:40px 30px 30px;border-bottom:1px solid var(--line);background:var(--panel)}
h1{font-size:30px;font-weight:500;letter-spacing:-.02em;margin:6px 0 12px}
h2{font-size:17px;font-weight:500;letter-spacing:-.01em;margin:0 0 4px}
.eyebrow{font-family:var(--mono);font-size:11px;letter-spacing:.16em;text-transform:uppercase;
  color:var(--ash);margin:0}
.lede{max-width:70ch;color:var(--graphite)}
a,a:visited{color:var(--ember)}
main{padding:28px 30px 60px;max-width:1400px}
section{margin-bottom:34px}
.sec{font-family:var(--mono);font-size:11px;letter-spacing:.14em;text-transform:uppercase;
  color:var(--ash);margin:0 0 10px;padding-bottom:6px;border-bottom:1px solid var(--line)}
table{border-collapse:collapse;width:100%;font-size:13.5px}
th,td{text-align:left;padding:7px 10px;border-bottom:1px solid var(--line-soft);vertical-align:top}
th{font-family:var(--mono);font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;
  color:var(--ash);font-weight:500;white-space:nowrap}
td.c,th.c{text-align:center}
.wrap{overflow-x:auto;border:1px solid var(--line);border-radius:6px;background:var(--panel)}
.yes{color:var(--ink);font-weight:600}
.no{color:var(--ash)}
.warn{color:var(--ember-deep);font-weight:600}
.note{font-size:11.5px;color:var(--ember-deep);display:block;line-height:1.35;margin-top:1px}
.mono{font-family:var(--mono);font-size:12.5px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:16px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:18px 20px}
.card h2{margin-bottom:2px}
.sub{font-size:12.5px;color:var(--ash);margin-bottom:14px}
.kv{display:flex;justify-content:space-between;gap:14px;padding:5px 0;
  border-bottom:1px solid var(--line-soft);font-size:13px}
.kv b{font-weight:500;color:var(--graphite)}
.kv span{text-align:right;color:var(--ink)}
.pill{display:inline-block;font-family:var(--mono);font-size:11px;padding:2px 7px;
  border:1px solid var(--line);border-radius:99px;background:var(--paper);color:var(--graphite);
  margin:0 4px 4px 0}
.pill.off{color:#a5a3a8;text-decoration:line-through;border-style:dashed}
.grp{margin-top:14px}
.grp .sec{margin-bottom:7px}
.fineprint{font-size:12.5px;color:var(--ash);max-width:78ch;margin-top:10px}
.fineprint b{color:var(--graphite);font-weight:500}
"""

BODY = r"""
<header>
<p class="eyebrow">Site capability registry</p>
<h1>What each hospital can<br>actually do.</h1>
<div class="lede">Gate check 9 asks whether a plan can be carried out here, and answers
from this record rather than from a prompt. It is why the same patient gets a test
order at one hospital and a referral at another. Read from the pack, on the
<a href="/">scripted run</a> and on <a href="/clinic">the interactive page</a> alike.</div>
</header>
<main>

<section>
  <p class="sec">Investigations, by site</p>
  <div class="wrap"><table id="labs"></table></div>
  <p class="fineprint"><b>Listed is not the same as delivered.</b> A site can claim a
  service it has not performed, which is the stale-registry failure the capability
  article exists to catch. Where the registry has no recent evidence the cell says so,
  and the gate warns without blocking: the plan may well be right and the records are
  what is doubtful, so denying care over paperwork would be the wrong trade.</p>
</section>

<section>
  <p class="sec">Formulary, by site</p>
  <div class="wrap"><table id="drugs"></table></div>
  <p class="fineprint">A drug the pathway may prescribe but this site does not stock is a
  hard failure of check 9, not a warning. The draft becomes a referral.</p>
</section>

<section>
  <p class="sec">The records themselves</p>
  <div class="cards" id="cards"></div>
</section>

</main>
<script>
const esc = s => String(s ?? "").replace(/[&<>"]/g, c =>
  ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));

const S = DATA.sites;

// Matrix first, cards second. The comparison is the point: one site's lab list is a
// fact, and three side by side is the explanation for a refusal.
function matrix(el, rows, head, cell){
  document.getElementById(el).innerHTML =
    `<tr><th>${head}</th>${S.map(s=>`<th class="c">${esc(s.site_id)}</th>`).join("")}</tr>` +
    rows.map(r => `<tr><td>${r.head}</td>${S.map(s=>`<td class="c">${cell(s,r)}</td>`).join("")}</tr>`).join("");
}

matrix("labs",
  DATA.investigations.map(i => ({code:i.code, head:`${esc(i.label)} <span class="mono">${esc(i.code)}</span>`})),
  "Investigation",
  (s,r) => {
    const l = s.labs.find(x => x.code === r.code);
    if (!l || !l.available) return `<span class="no">not available</span>`;
    if (l.gap) return `<span class="warn">on paper</span><span class="note">${esc(l.gap)}</span>`;
    return `<span class="yes">available</span>`;
  });

matrix("drugs",
  DATA.molecules.map(m => ({m, head:`<span class="mono">${esc(m)}</span>`})),
  "Molecule",
  (s,r) => s.molecules.find(x => x.molecule === r.m)?.stocked
    ? `<span class="yes">stocked</span>` : `<span class="no">not stocked</span>`);

document.getElementById("cards").innerHTML = S.map(s => {
  const labs = s.labs.filter(l => l.available);
  const kv = (k,v) => `<div class="kv"><b>${k}</b><span>${v}</span></div>`;
  return `<div class="card">
    <h2>${esc(s.site_id)}</h2>
    <div class="sub">${esc(s.label)}</div>
    ${kv("Tier", esc(s.tier))}
    ${kv("Service group", `<span class="mono">${esc(s.service_group)}</span>`)}
    ${kv("Open around the clock", s.continuous_24h ? "yes" : "no")}
    ${kv("Record last updated", `<span class="mono">${esc(s.as_of)}</span>`)}
    ${kv("Investigations", `${labs.length} of ${DATA.investigations.length}`)}
    ${kv("Formulary stocked", `${s.molecules.filter(m=>m.stocked).length} of ${s.molecules.length}`)}
    ${kv("Can sign today", (()=>{const ok=s.practitioners.filter(p=>!p.can_sign).length,
      n=s.practitioners.length; return ok===n ? `${ok} of ${n}`
        : `<span class="warn">${ok} of ${n}</span>`;})())}
    <div class="grp"><p class="sec">Diagnoses worked up here</p>
      ${s.diagnoses.map(d=>`<span class="pill">${esc(d)}</span>`).join("") || '<span class="no">none listed</span>'}</div>
    <div class="grp"><p class="sec">Equipment</p>
      ${s.equipment.map(e=>`<span class="pill${e.working?"":" off"}">${esc(e.item)}</span>`).join("")
        || '<span class="no">none listed</span>'}</div>
    <div class="grp"><p class="sec">Practitioners</p>
      ${s.practitioners.map(p=>`<div class="kv"><b><span class="mono">${esc(p.practitioner_id)}</span></b>
        <span>${esc(String(p.role).replace(/_/g," "))}, SIP to ${esc(p.sip_expires)}
        ${p.can_sign ? `<span class="note">cannot sign: ${esc(p.can_sign)}</span>` : ""}</span></div>`).join("")
        || '<span class="no">none listed</span>'}</div>
  </div>`;
}).join("");
</script>
"""


def render_sites(data: dict[str, Any]) -> str:
    """One self-contained page. Same tokens as the other two surfaces."""
    return (
        '<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>AI clinician, site capability</title>"
        f"<style>{STYLE}</style></head><body>"
        f"<script>const DATA = {json.dumps(data)};</script>"
        f"{BODY}</body></html>"
    )
