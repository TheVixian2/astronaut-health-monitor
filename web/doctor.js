// Written with AI assistance (Claude Code, Anthropic) and reviewed by the team. See README "Use of AI".
// Crew Medical Officer, "Medications" tab: medication warnings for the whole crew.
// The page's other tabs are the doctor's own data (self-check.js).
// - Scheduled doses from the SAMPLE plan in meds.js: due now, overdue, upcoming.
// - Alert-linked suggestions: when a live alert arrives (view=crew, on board),
//   meds.js `onAlert` says what the CMO might consider.
// "Given" / "dismissed" marks are kept in localStorage (this browser only).

(function () {
  const $ = id => document.getElementById(id);
  const A = window.AHM;
  const { esc, profileName } = A;
  const cfg = A.settings();
  const PLAN = window.AHM_MEDS || { schedule: [], onAlert: {} };

  const DUE_BEFORE_MIN = 15;     // "due now" from 15 min before the dose time...
  const DUE_AFTER_MIN = 30;      // ...until 30 min after; later than that is overdue
  const STORE = "ahm-meds-marks";

  const names = new Map();       // aid -> crew name
  const members = new Map();     // aid -> crew member (for the avatar)
  const suggestions = new Map(); // "aid|profile" -> { alert, med } (newest alert only)

  // ---- marks (given / dismissed) ------------------------------------------
  function marks() { try { return JSON.parse(localStorage.getItem(STORE) || "{}"); } catch { return {}; } }
  function mark(key, what) {
    const m = marks();
    m[key] = { what, at: Date.now() };
    try { localStorage.setItem(STORE, JSON.stringify(m)); } catch { /* demo only */ }
    render();
  }
  window.addEventListener("storage", e => { if (e.key === STORE) render(); });

  // ---- data ----------------------------------------------------------------
  init();

  const RECENT_MIN = 60;   // only alerts from the last hour suggest a medication

  async function init() {
    render();   // the schedule needs no network: show it at once
    try {
      const list = await A.watchCrew(cfg, {
        // Newest alert per crew member and condition, from the last hour; the
        // backend's alert list holds everything since it started.
        onAlert: a => {
          const med = PLAN.onAlert[a.profile];
          if (!med || Date.now() - Date.parse(a.started_at) > RECENT_MIN * 60000) return;
          const k = `${a.astronaut_id}|${a.profile}`;
          const prev = suggestions.get(k);
          if (prev && Date.parse(prev.alert.started_at) >= Date.parse(a.started_at)) return;
          suggestions.set(k, { alert: a, med });
          render();
        },
        onConn: (text, cls) => { $("medsConn").textContent = text; $("medsConn").className = `pill ${cls}`; },
      });
      for (const c of list) { names.set(c.id, c.name); members.set(c.id, c); }
    } catch (err) {
      $("medsConn").textContent = "offline";
      $("medsConn").className = "pill pill-off";
    }
    render();
    setInterval(render, 30000);   // statuses move with the clock
  }

  // Today's dose instances, in station time (UTC).
  function doses(now) {
    const day = now.toISOString().slice(0, 10);
    const out = [];
    for (const m of PLAN.schedule) {
      for (const t of m.times) {
        const at = new Date(`${day}T${t}:00Z`);
        const key = `${day}|${m.aid}|${m.drug}|${t}`;
        const mk = marks()[key];
        const mins = (now - at) / 60000;   // positive = past the dose time
        let status = "upcoming";
        if (mk) status = "given";
        else if (mins > DUE_AFTER_MIN) status = "overdue";
        else if (mins >= -DUE_BEFORE_MIN) status = "due";
        out.push({ ...m, time: t, at, key, status, mins, givenAt: mk?.at });
      }
    }
    return out.sort((x, y) => x.at - y.at);
  }

  // ---- rendering -------------------------------------------------------------
  function render() {
    const now = new Date();
    $("clock").textContent = now.toISOString().slice(11, 16);
    const list = doses(now);
    const who = aid => names.get(aid) || aid;
    const person = aid => `<strong>${esc(who(aid))}</strong>`;

    // Needs attention: overdue first, then due now, then alert-linked suggestions.
    const attn = [
      ...list.filter(d => d.status === "overdue").map(d => ({ sev: "alert", d })),
      ...list.filter(d => d.status === "due").map(d => ({ sev: "watch", d })),
    ];
    const sugg = [...suggestions.values()].filter(s => !marks()[`prn|${s.alert.id}`]);
    const n = attn.length + sugg.length;
    // Same count on the menu tab, so it shows from the doctor's own tabs too.
    for (const id of ["attnCount", "medsCount"]) { $(id).textContent = n; $(id).hidden = !n; }

    const doseItem = ({ sev, d }) => `<li class="warn sev-${sev}">
      <div class="head head-person"><span class="sev">${d.status === "overdue" ? "overdue" : "due now"}</span>${person(d.aid)}</div>
      <div class="med-line"><strong>${esc(d.drug)}</strong> ${esc(d.dose)}
        <span class="muted small">${esc(d.time)}, ${esc(d.route)}</span></div>
      <div class="small muted">${esc(d.purpose)}${d.status === "overdue" ? `, ${esc(late(d.mins))} late` : ""}</div>
      <div class="actions"><button type="button" data-give="${esc(d.key)}">Mark given</button></div></li>`;
    const suggItem = ({ alert: a, med }) => `<li class="warn sev-${esc(a.severity)}">
      <div class="head head-person"><span class="sev">${esc(a.severity)}</span>${person(a.astronaut_id)}
        <span class="muted small">${esc(clock(a.started_at))}</span></div>
      <div class="med-line">${esc(profileName(a.profile))}. Consider: <strong>${esc(med.drug)}</strong> ${esc(med.dose)}</div>
      <div class="small muted">${esc(med.note)} Your decision.</div>
      <div class="actions"><button type="button" data-prn="${esc(a.id)}" data-what="given">Mark given</button>
        <button type="button" class="link" data-prn="${esc(a.id)}" data-what="dismissed">Not needed</button></div></li>`;

    renderCrew(list, sugg);
    $("attention").innerHTML = n
      ? attn.map(doseItem).join("") + sugg.map(suggItem).join("")
      : '<li class="muted">Nothing due right now.</li>';

    $("schedule").tBodies[0].innerHTML = list.map(d => `<tr class="st-${d.status}">
      <td class="num">${esc(d.time)}</td><td>${person(d.aid)}</td><td>${esc(d.drug)}</td>
      <td>${esc(d.dose)} <span class="muted small">${esc(d.route)}</span></td><td class="small">${esc(d.purpose)}</td>
      <td><span class="dose-status ds-${d.status}">${statusText(d)}</span></td>
      <td>${d.status === "given" ? "" : `<button type="button" class="link" data-give="${esc(d.key)}">Mark given</button>`}</td></tr>`).join("");

    document.querySelectorAll("[data-give]").forEach(b => b.addEventListener("click", () => mark(b.dataset.give, "given")));
    document.querySelectorAll("[data-prn]").forEach(b => b.addEventListener("click", () => mark(`prn|${b.dataset.prn}`, b.dataset.what)));
  }

  // ---- the crew, whole body (owner, 2026-11-14) ---------------------------------
  // One whole-body avatar per crew member, the body parts their medicines are
  // for lit up: overdue orange, due now yellow, later today blue; given today
  // goes back to normal. Alert suggestions light their alert's body part.
  // (Lookups inside the function: init() renders before the file has run to here.)
  function renderCrew(list, sugg) {
    const DOSE_LEVEL = { overdue: "alert", due: "watch", upcoming: "info" };
    const DOSE_RANK = { overdue: 3, due: 2, upcoming: 1, given: 0 };
    const aids = members.size ? [...members.keys()] : [...new Set(PLAN.schedule.map(m => m.aid))];
    $("medCrew").innerHTML = aids.map(aid => {
      const m = members.get(aid) || { id: aid };
      // Per medicine: its most urgent dose today.
      const meds = new Map();
      for (const d of list.filter(x => x.aid === aid)) {
        const cur = meds.get(d.drug);
        if (!cur || DOSE_RANK[d.status] > DOSE_RANK[cur.status]) meds.set(d.drug, d);
      }
      const hits = {}, rows = [];
      for (const d of meds.values()) {
        A.addHit(hits, d.region, DOSE_LEVEL[d.status]);
        const when = d.status === "overdue" ? "overdue" : d.status === "due" ? "due now"
          : d.status === "given" ? "given" : `next ${d.time}`;
        rows.push(`<li class="lv-${DOSE_LEVEL[d.status] || "none"}"><span class="dot"></span>${esc(d.area || "")}: ${esc(d.drug)}, ${esc(when)}</li>`);
      }
      for (const { alert: a, med } of sugg.filter(s => s.alert.astronaut_id === aid)) {
        A.addHit(hits, a.body_region || "whole_body", a.severity);
        rows.push(`<li class="lv-${esc(a.severity)}"><span class="dot"></span>${esc(A.REGION_NAMES[a.body_region] || "Whole body")}: consider ${esc(med.drug)}</li>`);
      }
      return `<article class="mc-card">
        ${A.bodyFigure(m, hits)}
        <div class="mc-text"><strong>${esc(m.name || aid)}</strong><div class="muted small">${esc(m.role || "")}</div>
          <ul class="mc-list">${rows.join("") || '<li class="muted">No medicines today</li>'}</ul></div>
      </article>`;
    }).join("");
  }

  function statusText(d) {
    if (d.status === "given") return `given ${clock(d.givenAt)}`;
    if (d.status === "overdue") return `overdue by ${late(d.mins)}`;
    if (d.status === "due") return "due now";
    return `in ${late(-d.mins)}`;
  }
  function late(mins) {
    const m = Math.round(mins);
    return m < 60 ? `${m} min` : `${Math.floor(m / 60)} h ${m % 60} min`;
  }
  function clock(t) {
    return new Date(t).toISOString().slice(11, 16);   // station time
  }
})();
