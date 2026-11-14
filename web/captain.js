// Written with AI assistance (Claude Code, Anthropic) and reviewed by the team. See README "Use of AI".
// Commander, "Crew wellbeing" tab: every crew member's physical and
// psychological warnings, each with advice on how the Commander can help. On
// board, so not delayed. The page's other tabs are the Commander's own data
// (self-check.js).
//
// Crew members never see warnings on their own console (data only; decision,
// NotKaemy 2026-11-14), so whether and how to raise anything is the
// Commander's call. Advice is pre-written decision support, never a diagnosis.

(function () {
  const $ = id => document.getElementById(id);
  const A = window.AHM;
  const { SEVERITY_RANK, REGION_NAMES, esc, profileName } = A;
  const cfg = A.settings();

  const CIRC_REFRESH_MS = 60000;
  const crew = new Map();   // aid -> { info, latest, alerts: Map(id -> alert), circ }

  // ---- advice for the Commander ---------------------------------------------
  // {n} is replaced with the crew member's first name.
  const ADVICE = {
    orthostatic: "Make sure {n} can lie down with legs raised and isn't given standing, exercise or EVA tasks until re-checked in 10 minutes. Ask the Crew Medical Officer to look at them.",
    fever: "Lighten {n}'s workload and keep close-contact tasks to a minimum. Ask the Crew Medical Officer to examine them, and decide who covers their duties today.",
    co2: "Have {n} move to a better-ventilated module and check the CO2 scrubber reading there. If others report headaches too, treat it as a cabin problem, not a personal one.",
    sans: "Give {n} time today for the vision check, and agree with the Crew Medical Officer whether an OCT scan should be scheduled.",
    physical: "Check in with {n} and the Crew Medical Officer about this alert.",
    sleep_debt: "Protect {n}'s next sleep period: no late tasks, quarters in pre-sleep lighting an hour before bed. If you raise it, do it in private and ask how the workload feels.",
    circadian: "Help {n} keep a regular schedule: a similar bedtime each night, pre-sleep lighting in the evening, nothing scheduled late. Raise it privately, as a routine thing.",
    mood: "Find a private, unhurried moment with {n}. Ask open questions and listen rather than fix. Consider a lighter or more meaningful task, extra time for a private call home, and offer a private conference with Mission Control.",
    sleep: "Ask {n} how they slept and whether anything is keeping them up. Avoid scheduling them for demanding or late tasks today.",
  };
  const advise = (kind, name) => (ADVICE[kind] || ADVICE.physical).replaceAll("{n}", name);

  // The Commander is crew too, and sees their own warnings here (the Commander
  // sees everything; decision, NotKaemy 2026-11-14). Advice for "Talk to
  // yourself" makes no sense, so their own panel says who to go to instead.
  const SELF_ADVICE = {
    physical: "This one is about you. Ask the Crew Medical Officer to check on you, and hand over anything that can't wait.",
    psych: "This one is about you. Protect your own next sleep period, and consider a private talk with the Crew Medical Officer or Mission Control.",
  };
  const OWN_ROLE = "Commander";
  let ownAid = null;

  // Placeholder thresholds, from the crew member's own baseline.
  const LOW_MOOD = 2;              // mood_1to5 at or below this
  const SHORT_SLEEP_H = 6;         // or under 85% of their usual
  const SHORT_SLEEP_RATIO = 0.85;

  // ---- data ----------------------------------------------------------------

  init();

  async function init() {
    let list;
    try {
      list = await A.watchCrew(cfg, {
        onVitals: (aid, v) => { const c = crew.get(aid); if (c) { c.latest = v; render(); } },
        onAlert: a => { const c = crew.get(a.astronaut_id); if (c) { c.alerts.set(a.id, a); render(); } },
        onConn: (text, cls) => { $("crewConn").textContent = text; $("crewConn").className = `pill ${cls}`; },
      });
      ownAid = (list.find(c => c.role === OWN_ROLE) || {}).id || null;
    } catch (err) {
      $("crewPanels").innerHTML = `<p class="err">Could not load crew: ${esc(err.message)}. Is the backend running? (Add ?mock to use fake data.)</p>`;
      return;
    }
    // watchCrew starts streaming before it returns, so fill the map first.
    for (const info of list) if (!crew.has(info.id)) crew.set(info.id, { info, latest: null, alerts: new Map(), circ: null });
    render();
    loadCircadian();
    setInterval(loadCircadian, CIRC_REFRESH_MS);
  }

  async function loadCircadian() {
    await Promise.all([...crew.keys()].map(async aid => {
      try { crew.get(aid).circ = await A.getJSON(cfg.base, `/astronauts/${encodeURIComponent(aid)}/circadian?view=crew`, cfg.mock); }
      catch { crew.get(aid).circ = null; }
    }));
    // Wellbeing level + affected areas for every crew member (commander first:
    // the Commander always sees these, never the questionnaire answers).
    try {
      const wb = await A.getJSON(cfg.base, `/crew/wellbeing?viewer=${encodeURIComponent(ownAid || "a1")}`, cfg.mock);
      for (const m of wb.members) { const c = crew.get(m.astronaut_id); if (c) c.wb = m; }
    } catch { /* mock mode or backend down: panels show without the level */ }
    render();
  }

  // ---- warnings per crew member ---------------------------------------------

  // Newest alert per profile from the last hour: the backend's alert list holds
  // everything since it started and may repeat a profile; show each once.
  const RECENT_MIN = 60;
  function latestPerProfile(alerts) {
    const m = new Map();
    for (const a of alerts.values()) {
      if (Date.now() - Date.parse(a.started_at) > RECENT_MIN * 60000) continue;
      const prev = m.get(a.profile);
      if (!prev || Date.parse(a.started_at) >= Date.parse(prev.started_at)) m.set(a.profile, a);
    }
    return [...m.values()].sort((x, y) => Date.parse(y.started_at) - Date.parse(x.started_at));
  }

  function warningsFor(aid, c) {
    const name = c.info.name.replace(/^(Cmdr\.|Dr\.)\s*/, "").split(" ")[0];
    const self = aid === ownAid;
    const phys = kind => (self ? SELF_ADVICE.physical : advise(kind, name));
    const mind = kind => (self ? SELF_ADVICE.psych : advise(kind, name));
    const physical = [], psych = [];
    for (const a of latestPerProfile(c.alerts)) {
      const w = { severity: a.severity, title: profileName(a.profile), when: a.started_at, region: a.body_region,
                  detail: `${REGION_NAMES[a.body_region] || a.body_region}: ${a.onboard_action}` };
      if (A.isPsychological(a)) psych.push({ ...w, advice: mind(a.profile) });
      else physical.push({ ...w, advice: phys(ADVICE[a.profile] ? a.profile : "physical") });
    }

    const v = c.latest, base = v?.baseline || {};
    if (v && typeof v.mood_1to5 === "number" && v.mood_1to5 <= LOW_MOOD) {
      psych.push({ severity: v.mood_1to5 <= 1 ? "alert" : "watch", title: "Low mood", region: "head",
                   detail: `Mood ${v.mood_1to5}/5 (usual ${base.mood_1to5 ?? "?"}/5)`, advice: mind("mood") });
    }
    if (v && typeof v.sleep_h_last_night === "number"
        && (v.sleep_h_last_night < SHORT_SLEEP_H || (base.sleep_h_last_night && v.sleep_h_last_night < base.sleep_h_last_night * SHORT_SLEEP_RATIO))) {
      psych.push({ severity: "watch", title: "Short sleep", region: "head",
                   detail: `${v.sleep_h_last_night} h last night (usual ${base.sleep_h_last_night ?? "?"} h)`, advice: mind("sleep") });
    }
    const card = c.circ && A.circadianCardText(c.circ.card);
    if (card) {
      psych.push({ severity: "watch", title: "Irregular sleep timing", region: "head", detail: card, advice: mind("circadian") });
    }
    return { name, self, physical, psych };
  }

  // ---- rendering -------------------------------------------------------------

  function render() {
    if (!crew.size) return;
    let total = 0;
    $("crewPanels").innerHTML = [...crew.entries()].map(([aid, c]) => {
      const w = warningsFor(aid, c);
      total += w.physical.length + w.psych.length;
      return panel(aid, c, w);
    }).join("");
    // Count on the menu tab, so the Commander notices from their own tabs too.
    $("crewCount").textContent = total;
    $("crewCount").hidden = !total;
  }

  const WB_CLASS = { steady: "nominal", watch: "watch", concern: "alert", urgent: "critical" };
  // Level and areas only, never their answers. The general rule is a tooltip;
  // that the astronaut hasn't been told yet stays visible.
  function wellbeingLine(wb) {
    if (!wb || !wb.level) return "";
    const areas = wb.areas && wb.areas.length ? `<span class="cp-areas">${esc(wb.areas.join(", "))}</span>` : "";
    return `<p class="cp-wb" title="Level and areas only, never their answers">Wellbeing check
        <span class="st-${WB_CLASS[wb.level] || "nominal"}"><span class="st-pill">${esc(wb.level)}</span></span>${areas}</p>
      ${wb.visible_because === "commander_first" ? '<p class="cp-note">They haven\'t been told you can see this.</p>' : ""}`;
  }

  // One card per crew member, 2 x 2 (owner, 2026-11-14: "make these feel
  // better"): head, a stats strip, then a Physical and a Psychological row.
  function panel(aid, c, { name, self, physical, psych }) {
    const all = physical.concat(psych);
    const worst = all.reduce((w, x) => (!w || SEVERITY_RANK[x.severity] > SEVERITY_RANK[w] ? x.severity : w), null);
    const v = c.latest;
    const stat = (label, val, unit) =>
      `<div class="cp-stat"><span class="muted small">${label}</span><span class="cp-val">${esc(val ?? "—")}<span class="t-unit"> ${unit}</span></span></div>`;
    const stats = v
      ? stat("Heart rate", v.heart_rate_bpm, "bpm") + stat("Mood", v.mood_1to5, "/5") + stat("Sleep last night", v.sleep_h_last_night, "h")
      : '<p class="muted small cp-stat">No data yet</p>';
    const none = '<p class="cp-none">Nothing to act on</p>';
    const list = ws => `<ul class="warns">${ws.map(w => item(w, name)).join("")}</ul>`;
    // Whole-body avatar: every warning lights up its body part (psychological
    // ones and the wellbeing check: the head).
    const hits = {};
    for (const w of all) A.addHit(hits, w.region || "whole_body", w.severity);
    if (c.wb && WB_CLASS[c.wb.level] && WB_CLASS[c.wb.level] !== "nominal") A.addHit(hits, "head", WB_CLASS[c.wb.level]);
    return `<article class="card cap-panel st-${worst || "nominal"}">
      <div class="cp-layout">
        <div class="cp-fig">${A.bodyFigure(c.info, hits)}</div>
        <div class="cp-main">
          <div class="cc-head">
            <div><strong>${esc(c.info.name)}</strong>${self ? ' <span class="you-tag">you</span>' : ""}<div class="muted small">${esc(c.info.role)} (${esc(aid)})</div></div>
            <span class="st-pill">${esc(worst || "nominal")}</span>
          </div>
          <div class="cp-stats">${stats}</div>
          <div class="cp-sec"><h3>Physical</h3><div>${physical.length ? list(physical) : none}</div></div>
          <div class="cp-sec"><h3>Psychological <span>confidential</span></h3>
            <div>${wellbeingLine(c.wb)}${psych.length ? list(psych) : none}</div></div>
        </div>
      </div>
    </article>`;
  }

  function item(w, name) {
    return `<li class="warn sev-${esc(w.severity)}">
      <div class="head"><span class="sev">${esc(w.severity)}</span> <strong>${esc(w.title)}</strong>
        ${w.when ? `<span class="muted small">${esc(time(w.when))}</span>` : ""}</div>
      <div class="small muted">${esc(w.detail)}</div>
      <div class="advice"><span class="advice-label">How you can help:</span> ${esc(w.advice)}</div>
    </li>`;
  }

  function time(t) {
    return new Date(t).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }
})();
