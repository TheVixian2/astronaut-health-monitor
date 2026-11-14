// Written with AI assistance (Claude Code, Anthropic) and reviewed by the team. See README "Use of AI".
// Ground view: Mission Control. Whole crew at once, every stream opened with
// view=ground, so everything arrives one light-time late (the backend delays it).
//
// The "signals in transit" strip is a DEMO OVERLAY: it polls the undelayed
// GET /astronauts/{id}/alerts to show alerts that were raised on board but
// have not reached ground yet, with a countdown. A real ground station cannot
// know this. It is polled rather than streamed so the page holds only one SSE
// connection per astronaut (browsers allow ~6 per host over HTTP/1.1).

(function () {
  const $ = id => document.getElementById(id);
  const A = window.AHM;
  const { SEVERITY_RANK, ENV_NAMES, REGION_NAMES, verdict, deltaPct, dur, fmt, esc, profileName } = A;

  const cfg = A.settings();
  const TRANSIT_POLL_MS = 2000;
  const SPARK_POINTS = 40;          // ~2 min of HR per card
  const CIRC_POLL_MS = 30000;

  // Real one-way light time per environment, shown permanently in the header
  // so the stakes stay visible even when the demo runs compressed.
  const REAL_DELAY = {
    iss: { label: "~0 s", min_s: 0 },
    moon: { label: "~1.3 s", min_s: 1 },
    mars: { label: "3–22 min", min_s: 180 },
  };

  let mission = null;
  const crew = new Map();           // aid -> {info, latest, at, hr: [], baseHr, alerts: Map}
  const received = new Map();       // alert id -> alert, as delivered to ground
  const transit = new Map();        // alert id -> alert, raised on board, not yet received
  const sources = [];

  // Test feed (test-feed.js): the `test` account, or ?test, shows one scripted
  // test subject (new data every 10 s, no light delay) instead of the crew.
  const TEST = !!(window.AHMTestFeed && window.AHMTestFeed.enabled);

  init();

  async function init() {
    try { mission = await A.getJSON(cfg.base, "/mission", cfg.mock); } catch { mission = null; }
    renderMission();
    if (TEST) {
      document.body.classList.add("test-feed");
      $("pageSub").textContent = `Test feed: a scripted test subject, new data every ${window.AHMTestFeed.STEP_S} s`;
      $("delayBanner").querySelector("strong").textContent = "Test feed.";
      $("delayText").textContent = "Not delayed. Each step sends one vital wrong, then good, through every vital in turn.";
    }

    let list;
    try { list = TEST ? window.AHMTestFeed.crew : await A.getJSON(cfg.base, "/crew", cfg.mock); }
    catch (err) {
      $("crew").innerHTML = `<p class="err">Could not load crew: ${esc(err.message)}. Is the backend running? (Add ?mock to use fake data.)</p>`;
      setConn("disconnected", "pill-off");
      return;
    }

    for (const info of list) crew.set(info.id, { info, latest: null, at: null, hr: [], baseHr: null, alerts: new Map(), circ: null });
    renderCrew();

    let open = 0;
    for (const aid of crew.keys()) {
      const source = TEST ? new window.AHMTestFeed.EventSource() : A.openStream({ ...cfg, aid, view: "ground" }).source;
      sources.push(source);
      source.onopen = () => { open++; updateConn(); };
      source.onerror = () => updateConn();
      source.addEventListener("vitals", e => onVitals(aid, JSON.parse(e.data)));
      source.addEventListener("alert", e => onAlert(JSON.parse(e.data)));
    }

    function updateConn() {
      const live = sources.filter(s => s.readyState === 1).length;
      if (live === sources.length) setConn(cfg.mock ? "connected (mock)" : "connected", "pill-on");
      else if (live === 0 && open === 0) setConn("connecting…", "pill-wait");
      else setConn(`${live}/${sources.length} streams`, "pill-wait");
    }

    if (TEST) { setInterval(tick, 1000); return; }   // no circadian or transit for the test subject
    pollCircadian();
    setInterval(pollCircadian, CIRC_POLL_MS);

    $("showTransit").addEventListener("change", renderTransit);
    pollTransit();
    setInterval(pollTransit, TRANSIT_POLL_MS);
    setInterval(tick, 1000);
  }

  // ---- delayed data --------------------------------------------------------

  function onVitals(aid, v) {
    const c = crew.get(aid);
    if (!c) return;
    v = A.withScan(A.withStress(v), aid);   // stress from HRV; simulated X-ray scan until the backend sends one
    c.latest = v;
    c.at = new Date(v.timestamp);
    c.baseHr = v.baseline ? v.baseline.heart_rate_bpm : null;
    c.hr.push(v.heart_rate_bpm);
    if (c.hr.length > SPARK_POINTS) c.hr.shift();
    renderCard(aid);
  }

  function onAlert(a) {
    received.set(a.id, a);           // upsert: the insight re-send has the same id
    transit.delete(a.id);
    const c = crew.get(a.astronaut_id);
    if (c) { c.alerts.set(a.id, a); renderCard(a.astronaut_id); }
    renderAlerts();
    renderTransit();
  }

  // ---- circadian (PROVISIONAL): only what each astronaut chose to share ------
  // view=ground answers 403 until the astronaut shares. A summary, not a live
  // signal, so a slow poll is enough.

  async function pollCircadian() {
    await Promise.all([...crew.keys()].map(async aid => {
      const c = crew.get(aid);
      try {
        c.circ = { state: "shared", data: await A.getJSON(cfg.base, `/astronauts/${encodeURIComponent(aid)}/circadian?view=ground`, cfg.mock) };
      } catch (err) {
        c.circ = err.status === 403 ? { state: "private" } : null;   // 404 / offline: no line at all
      }
      renderCard(aid);
    }));
  }

  function circLine(c) {
    if (!c.circ) return "";
    if (c.circ.state === "private") return '<div class="small muted cc-circ">Sleep &amp; light: not shared by the astronaut</div>';
    const d = c.circ.data, s = d.summary || {}, L = d.lighting || {};
    const light = L.mode ? `, lighting ${esc(A.LIGHTING_NAMES[L.mode] || L.mode)}${L.cct_k ? ` ${L.cct_k} K` : ""}` : "";
    if (s.status === "watch") {
      return `<div class="small cc-circ watch">Sleep &amp; light: bedtime varied ${hoursLikePython(s.bedtime_spread_min)} h, ` +
             `bright light before sleep ${s.nights_bright_before_sleep}/${s.nights} nights${light}</div>`;
    }
    return `<div class="small muted cc-circ">Sleep &amp; light: nothing stands out${light}</div>`;
  }

  // Minutes -> hours to one decimal, rounding halves to even like the
  // backend's f"{x:.1f}", so Ground and the Self-check card (backend text)
  // show the same number: 135 min -> "2.2", not JS toFixed's "2.3".
  function hoursLikePython(min) {
    const tenths = min / 6;
    let r = Math.round(tenths);
    if (Math.abs(tenths % 1) === 0.5 && r % 2 !== 0) r -= 1;
    return (r / 10).toFixed(1);
  }

  // ---- demo overlay: in transit --------------------------------------------

  async function pollTransit() {
    if (!mission) return;
    const now = Date.now();
    const delayMs = mission.one_way_delay_s * 1000;
    await Promise.all([...crew.keys()].map(async aid => {
      let list;
      try { list = await A.getJSON(cfg.base, `/astronauts/${encodeURIComponent(aid)}/alerts`, cfg.mock); }
      catch { return; }
      for (const a of list) {
        const arrives = Date.parse(a.started_at) + delayMs;
        if (!received.has(a.id) && arrives > now - 2000) transit.set(a.id, a);
      }
    }));
    renderTransit();
  }

  function renderTransit() {
    // Drop entries well past their arrival time. Normally the delayed stream
    // delivers them first; this catches alerts that reached ground before this
    // page connected, which the stream will never replay.
    const delayMsNow = mission ? mission.one_way_delay_s * 1000 : 0;
    for (const [id, a] of transit) {
      if (Date.now() > Date.parse(a.started_at) + delayMsNow + 5000) transit.delete(id);
    }
    const show = $("showTransit").checked && transit.size > 0;
    $("transit").hidden = !show;
    if (!show) return;
    const delayMs = mission ? mission.one_way_delay_s * 1000 : 0;
    $("transitList").innerHTML = [...transit.values()].map(a => {
      const left = Math.max(0, (Date.parse(a.started_at) + delayMs - Date.now()) / 1000);
      const name = crew.get(a.astronaut_id)?.info.name || a.astronaut_id;
      return `<li class="sev-${esc(a.severity)}">
        <span class="count">arrives in ${clock(left)}</span>
        <span class="sev">${esc(a.severity)}</span>
        <strong>${esc(profileName(a.profile))}</strong>
        <span class="muted">${esc(name)}, raised on board ${esc(time(a.started_at))}</span></li>`;
    }).join("");
  }

  // ---- rendering -----------------------------------------------------------

  function crewStatus(c) {
    let best = null;
    for (const a of c.alerts.values()) if (!best || SEVERITY_RANK[a.severity] > SEVERITY_RANK[best]) best = a.severity;
    return best || "nominal";
  }

  function renderCrew() {
    $("crew").innerHTML = [...crew.keys()].map(aid => `<article class="card crew-card" id="card-${esc(aid)}"></article>`).join("");
    for (const aid of crew.keys()) renderCard(aid);
  }

  // Every vital with its green-to-red threshold scale (owner, 2026-11-14):
  // green near the astronaut's own usual, then yellow / orange / red at the
  // watch / alert / critical steps in AHM.thresholdLevel (placeholders).
  const LEVEL_NAMES = { ok: "near usual", watch: "watch", alert: "alert", critical: "critical" };
  function thresholdRow(f, v) {
    const now = v ? v[f.key] : null, base = v?.baseline?.[f.key];
    const t = A.thresholdLevel(f.key, now, base);
    const show = x => (typeof x === "number" && f.dp != null ? x.toFixed(f.dp) : fmt(x));
    const pc = x => `${(x * 100).toFixed(1)}%`;
    let change = "";
    if (t) {
      const sign = t.signed > 0 ? "+" : t.signed < 0 ? "−" : "±";
      change = t.by === "score" ? A.stressBand(now)
        : t.by === "pct" ? `${sign}${Math.abs(t.signed).toFixed(f.deltaDp || 0)}%`
        : `${sign}${Math.abs(t.signed).toFixed(f.key === "temp_c" ? 1 : 0)}`;
    }
    const scale = t
      ? `<span class="th-scale" style="--b1:${pc(t.steps[0])};--b2:${pc(t.steps[1])};--b3:${pc(t.steps[2])}"
           role="img" aria-label="${esc(f.label)}: ${LEVEL_NAMES[t.level]}"><span class="th-mark" style="left:${pc(t.pos)}"></span></span>`
      : '<span class="th-scale th-empty" aria-hidden="true"></span>';
    return `<div class="th-row th-${t ? t.level : "none"}" title="${esc(f.label)}: ${t ? LEVEL_NAMES[t.level] : "no reading"}${base != null ? `, usual ${esc(show(base))} ${esc(f.unit)}` : ""}">
      <span class="th-label">${esc(f.label)}</span>
      <span class="th-val">${show(now)}<span class="t-unit"> ${esc(f.unit)}</span></span>
      ${scale}
      <span class="th-dev">${esc(change)}</span></div>`;
  }

  function renderCard(aid) {
    const c = crew.get(aid);
    const el = $(`card-${aid}`);
    if (!c || !el) return;
    const status = crewStatus(c);
    const v = c.latest;
    const rows = A.FIELDS.map(f => thresholdRow(f, v)).join("");
    const testStep = TEST && v && v.test_step
      ? `<div class="small cc-test">Test step: <strong>${esc(v.test_step.label)}</strong>, ${v.test_step.wrong ? "wrong reading" : "good reading"}</div>` : "";
    const latestAlert = [...c.alerts.values()].pop();
    el.className = `card crew-card st-${status}`;
    el.innerHTML = `
      <div class="cc-head">
        <div><strong>${esc(c.info.name)}</strong><div class="muted small">${esc(c.info.role)} (${esc(aid)})</div></div>
        <span class="st-pill">${esc(status)}</span>
      </div>
      ${testStep}
      <div class="th-list">${rows}</div>
      ${spark(c.hr, c.baseHr)}
      <div class="small cc-age" data-aid="${esc(aid)}">${ageText(c)}</div>
      ${latestAlert ? `<div class="small cc-alert sev-${esc(latestAlert.severity)}"><span class="dot"></span>${esc(profileName(latestAlert.profile))}, ${esc(REGION_NAMES[latestAlert.body_region] || latestAlert.body_region)}</div>` : ""}
      ${circLine(c)}`;
  }

  // Tiny inline SVG sparkline of heart rate, baseline dashed.
  function spark(values, base) {
    if (values.length < 2) return '<div class="spark muted small">HR trend appears after a few readings…</div>';
    const W = 220, H = 40, all = base != null ? values.concat(base) : values;
    const lo = Math.min(...all) - 2, hi = Math.max(...all) + 2;
    const x = i => (i / (SPARK_POINTS - 1)) * W;
    const y = val => H - ((val - lo) / (hi - lo)) * H;
    const off = SPARK_POINTS - values.length;
    const pts = values.map((val, i) => `${x(i + off).toFixed(1)},${y(val).toFixed(1)}`).join(" ");
    const baseLine = base != null ? `<line x1="0" x2="${W}" y1="${y(base).toFixed(1)}" y2="${y(base).toFixed(1)}" class="sp-base"/>` : "";
    return `<svg class="spark" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" aria-label="Heart rate trend">${baseLine}<polyline points="${pts}" class="sp-line"/></svg>`;
  }

  function ageText(c) {
    if (!c.at) return '<span class="muted">No data received yet</span>';
    const s = Math.max(0, Math.round((Date.now() - c.at) / 1000));
    const limit = (mission ? mission.one_way_delay_s : 0) + 10;
    return `<span class="${s > limit ? "stale" : "muted"}">As of ${esc(time(c.at))}, <strong>${dur(s)} old</strong></span>`;
  }

  function renderAlerts() {
    const ul = $("alerts");
    if (!received.size) { ul.innerHTML = '<li class="muted">Nothing received yet.</li>'; return; }
    const delay = mission ? mission.one_way_delay_s : null;
    ul.innerHTML = [...received.values()].reverse().map(a => {
      const v = verdict(a, mission);
      const name = crew.get(a.astronaut_id)?.info.name || a.astronaut_id;
      const crewSaw = v.onboard === true ? "Crew was told: act on board now"
        : v.onboard === false ? "Crew was told: ground will advise" : `Act within ${dur(a.act_within_s)}`;
      const ins = a.insight
        ? `<details><summary>Insight · ${a.insight.source === "claude" ? "AI-generated (Claude)" : "On board"}</summary><dl><dt>Why</dt><dd>${esc(a.insight.why)}</dd>
           <dt>Trend</dt><dd>${esc(a.insight.trend)}</dd><dt>Suggested</dt><dd>${esc(a.insight.recommended_action)}</dd></dl></details>`
        : '<p class="muted small">Insight not received yet.</p>';
      return `<li class="alert sev-${esc(a.severity)}">
        <div class="head"><span class="sev">${esc(a.severity)}</span>
          <strong>${esc(profileName(a.profile))}</strong>
          <span class="muted small">${esc(name)}, ${esc(REGION_NAMES[a.body_region] || a.body_region)}</span></div>
        <div class="verdict">${esc(crewSaw)}</div>
        <div class="small muted">Raised on board ${esc(time(a.started_at))}${delay != null ? `, reached ground ${dur(delay)} later` : ""}. Act within ${dur(a.act_within_s)}</div>
        <div>On-board action: ${esc(a.onboard_action)}</div>${A.nasaRefs(a)}${ins}</li>`;
    }).join("");
  }

  function renderMission() {
    if (!mission) {
      $("missionReal").textContent = "Mission: unknown";
      $("delayText").textContent = "Delay unknown: the mission settings did not load. Is the backend running?";
      return;
    }
    const env = ENV_NAMES[mission.environment] || mission.environment;
    // real_one_way_delay_s (GET /mission) is the true light time; fall back to
    // the environment's typical range if the backend doesn't send it.
    const realS = mission.real_one_way_delay_s;
    const realLabel = realS != null ? dur(realS) : REAL_DELAY[mission.environment]?.label;
    const compressed = realS != null ? realS > mission.one_way_delay_s
      : mission.one_way_delay_s < (REAL_DELAY[mission.environment]?.min_s ?? 0);
    $("missionReal").innerHTML = `<strong>${esc(env)}</strong>, ${esc(realLabel || dur(mission.one_way_delay_s))} one way` +
      (compressed ? ` <span class="muted">(demo: ${dur(mission.one_way_delay_s)})</span>` : "");
    $("delayText").textContent = `Everything here left the spacecraft at least ${dur(mission.one_way_delay_s)} ago` +
      (compressed ? `. On a real ${env} mission that is ${realLabel}.` : ".");
  }

  function tick() {
    for (const [aid, c] of crew) {
      const el = document.querySelector(`.cc-age[data-aid="${CSS.escape(aid)}"]`);
      if (el) el.innerHTML = ageText(c);
    }
    renderTransit();
  }

  function setConn(text, cls) { const el = $("conn"); el.textContent = text; el.className = `pill ${cls}`; }

  function clock(s) {
    s = Math.ceil(s);
    return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
  }

  function time(t) {
    const d = t instanceof Date ? t : new Date(t);
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  }
})();
