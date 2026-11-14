// Written with AI assistance (Claude Code, Anthropic) and reviewed by the team. See README "Use of AI".
// Astronaut console: a crew member's own data. Live (view=crew).
//
// DATA ONLY, NO WARNINGS (decision, NotKaemy 2026-11-14): crew members see
// their own numbers against their own baseline, never alerts, verdicts,
// advice or "something is wrong" wording. Warnings go to the Commander
// (captain.html), the Crew Medical Officer (doctor.html) and Ground. This code does
// not even subscribe to `alert` events.
//
// Used by three pages, each with an empty <main id="console">:
// - self-check.html: any astronaut, picked with the #aid selector (?aid=).
// - captain.html / doctor.html: the Commander's / Crew Medical Officer's own data,
//   next to their crew tab. data-crew-role names whose data it is (looked up
//   in GET /crew, data-aid is the fallback) and data-poll makes it poll
//   GET /vitals instead of holding an SSE stream (browser limit ~6 per host).

(function () {
  const $ = id => document.getElementById(id);
  const A = window.AHM;
  const { FIELDS, REGION_NAMES, deltaPct, dur, fmt, esc } = A;

  const root = $("console");
  root.innerHTML = consoleMarkup();

  const cfg = A.settings();
  cfg.view = "crew";                 // the console is never the delayed view
  const ownRole = root.dataset.crewRole || null;   // set on captain.html / doctor.html
  if (ownRole) cfg.aid = root.dataset.aid || cfg.aid;
  const POLL = root.hasAttribute("data-poll") && !cfg.mock;
  // Presenter: a pattern for the whole mission and a period selector instead of
  // live data (pattern.js, owner 2026-11-14).
  const PATTERN = !!(window.AHMPattern && window.AHMPattern.enabled);
  const POLL_MS = 3000;

  const MAX_POINTS = 120;            // ~6 min at one vitals event per 3 s
  const STALE_S = 10;

  let mission = null;
  let latest = null;                 // latest vitals snapshot
  let lastVitalsAt = null;
  let region = "whole_body";         // selected body region
  let chartField = "heart_rate_bpm";
  const history = [];                // [{t, v}] vitals snapshots for the chart

  // ---- setup ---------------------------------------------------------------

  if ($("aid")) {                    // astronaut picker: self-check.html only
    $("aid").value = cfg.aid;
    $("aid").addEventListener("change", () => {
      location.href = A.linkWithSettings("self-check.html", { aid: $("aid").value }) + location.hash;
    });
  }

  document.querySelectorAll("#body .region").forEach(g => {
    const pick = () => selectRegion(g.dataset.region);
    g.addEventListener("click", pick);
    g.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pick(); } });
  });

  $("sexSwitch").addEventListener("change", e => {
    if (e.target.name !== "sex") return;
    setSex(e.target.value, true);
    rememberSex(e.target.value);
  });

  $("tiles").addEventListener("click", e => {
    const tile = e.target.closest(".tile");
    if (tile) { chartField = tile.dataset.key; renderTiles(); rebuildChart(); }
  });

  $("checkin").addEventListener("submit", onCheckin);

  init();

  async function init() {
    try {
      const crew = await A.getJSON(cfg.base, "/crew", cfg.mock);
      // Commander / Crew Medical Officer: whoever holds that role on this crew.
      const own = ownRole && crew.find(c => c.role === ownRole);
      if (own) cfg.aid = own.id;
      const me = crew.find(c => c.id === cfg.aid);
      $("name").textContent = me ? me.name : cfg.aid;
      $("role").textContent = me ? `${me.role} (${me.id})` : "";
      setSex(A.sexOf(me || { id: cfg.aid }), false);
    } catch { $("name").textContent = cfg.aid; }

    try { mission = await A.getJSON(cfg.base, "/mission", cfg.mock); } catch { mission = null; }
    renderMission();

    // No "alert" listener or alert polling on purpose: data only.
    if (PATTERN) startPattern();
    else if (POLL) startPolling();
    else {
      const { source } = A.openStream(cfg);
      source.onopen = () => setConn(cfg.mock ? "connected (mock)" : "connected", "pill-on");
      source.onerror = () => setConn(source.readyState === 2 ? "disconnected" : "reconnecting…",
                                     source.readyState === 2 ? "pill-off" : "pill-wait");
      source.addEventListener("vitals", e => onVitals(JSON.parse(e.data)));
    }

    selectRegion(region);
    setInterval(renderAge, 1000);
    loadCircadian();                 // needs cfg.aid, known only now
    setInterval(loadCircadian, CIRC_REFRESH_MS);
  }

  // Derived values for a raw snapshot: the usual shifted for the cycle (when the
  // astronaut has switched that on), stress from HRV, the X-ray scan.
  const derive = raw => A.withScan(A.withStress(A.withCycle(raw, cfg.aid)), cfg.aid);

  let period = null;                 // pattern mode: the period on show
  function showPeriod(p) {
    period = p;
    history.length = 0;
    for (const s of window.AHMPattern.series(cfg.aid, p.from, p.to, MAX_POINTS)) history.push({ t: s.t, raw: s.v, v: derive(s.v) });
    latest = history[history.length - 1].v;
    lastVitalsAt = history[history.length - 1].t;
    renderTiles();
    rebuildChart();
    renderSleep(latest);
    renderAge();
    renderCycleBtn();
  }

  function startPattern() {
    document.body.classList.add("pattern");
    setConn("pattern", "pill-on");
    window.AHMPattern.control(document.querySelector("header.bar .status"), showPeriod);
  }

  function startPolling() {
    let lastTs = null;
    const tick = async () => {
      try {
        const v = await A.getJSON(cfg.base, `/astronauts/${encodeURIComponent(cfg.aid)}/vitals`, false);
        setConn("connected", "pill-on");
        if (v.timestamp !== lastTs) { lastTs = v.timestamp; onVitals(v); }
      } catch { setConn("offline", "pill-off"); }
    };
    tick();
    setInterval(tick, POLL_MS);
  }

  function onVitals(raw) {
    const v = derive(raw);           // cycle-adjusted usual, stress from HRV, simulated X-ray scan
    latest = v;
    lastVitalsAt = new Date(v.timestamp);
    history.push({ t: lastVitalsAt, raw, v });
    if (history.length > MAX_POINTS) history.shift();
    renderTiles();
    pushChart();
    renderAge();
    renderSleep(v);
  }

  // ---- body figure: picks which vitals to focus on -------------------------

  function selectRegion(r) {
    region = r;
    const first = FIELDS.find(f => f.region === r);
    if (first) chartField = first.key;
    document.querySelectorAll("#body .region").forEach(g => {
      g.classList.toggle("selected", g.dataset.region === region);
      g.setAttribute("aria-pressed", String(g.dataset.region === region));
    });
    renderTiles();
    renderRegionInfo();
    rebuildChart();
  }

  // ---- body shape: male or female silhouette ------------------------------
  // Shapes and the choice live in common.js (AHM.BODY_SHAPES, AHM.sexOf), so
  // the crew avatars on the Commander's and Medical Officer's tabs match:
  // the switch here (remembered in this browser per astronaut), else a `sex`
  // field from the backend, else the demo crew's default.
  // The two figures share their point structure, so the paths morph.
  const CAN_MORPH = window.CSS && CSS.supports && CSS.supports("d", 'path("M0 0")');
  function rememberSex(sex) { A.rememberSex(cfg.aid, sex); }
  function setSex(sex, animate) {
    sex = A.normSex(sex) || "male";
    const shapes = A.BODY_SHAPES[sex];
    const morph = animate && CAN_MORPH && !matchMedia("(prefers-reduced-motion: reduce)").matches;
    document.querySelectorAll("#body [data-part]").forEach(el => {
      const from = el.getAttribute("d"), to = shapes[el.dataset.part];
      if (morph && from !== to) {
        el.animate([{ d: `path("${from}")` }, { d: `path("${to}")` }], { duration: 450, easing: "ease-in-out" });
      }
      el.setAttribute("d", to);
    });
    $("body").dataset.sex = sex;
    $(sex === "female" ? "sexF" : "sexM").checked = true;
    renderCycleBtn();
  }
  setSex(A.sexOf({ id: cfg.aid }), false);   // before the first paint (after the consts above)

  // ---- cycle-aware usual (common.js withCycle): opt-in, own console only ------
  // The button shows with the female figure, or whenever the setting is on.
  function renderCycleBtn() {
    const btn = $("cycleBtn");
    if (!btn) return;
    const cy = A.cycleAt(cfg.aid, lastVitalsAt ? +lastVitalsAt : Date.now());
    btn.hidden = !(cy || $("body").dataset.sex === "female");
    btn.textContent = cy ? `Cycle day ${cy.day}` : "Cycle";
    btn.classList.toggle("on", !!cy);
  }
  $("cycleBtn").addEventListener("click", () => {
    const c = A.cycleFor(cfg.aid), f = $("cycleForm");
    f.start.value = c ? new Date(c.start).toISOString().slice(0, 10) : "";
    f.len.value = c ? c.len : 28;
    $("cycleOff").hidden = !c;
    $("cycleDlg").showModal();
  });
  // On the form's submit (fires at once; the dialog's "close" event can wait for
  // the next frame), then the method="dialog" form closes the dialog itself.
  $("cycleForm").addEventListener("submit", e => {
    const how = e.submitter ? e.submitter.value : "save", f = $("cycleForm");
    if (how === "save" && f.start.value) A.setCycle(cfg.aid, { start: Date.parse(f.start.value), len: Number(f.len.value) || 28 });
    else if (how === "off") A.setCycle(cfg.aid, null);
    else return;
    // Re-derive what is on screen (the pattern itself follows the cycle too).
    if (PATTERN && period) showPeriod(period);
    else {
      history.forEach(p => { p.v = derive(p.raw); });
      if (history.length) latest = history[history.length - 1].v;
      renderTiles();
      rebuildChart();
    }
    renderCycleBtn();
  });

  function renderRegionInfo() {
    const fields = FIELDS.filter(f => region === "whole_body" || f.region === region).map(f => f.label);
    const note = region === "head" ? " Sleep and mood (in Check-in) belong here."
      : region === "skin" ? " Temperature is measured on the skin; bone density and muscle mass come from the X-ray scan." : "";
    $("regionInfo").innerHTML = `<h3>${esc(REGION_NAMES[region])}</h3>
      <p class="muted small">${fields.length ? `${esc(fields.join(", "))}.` : "No measurements for this region yet."}${esc(note)}</p>`;
  }

  // ---- vitals tiles + chart ------------------------------------------------

  function renderTiles() {
    if (!latest) return;
    $("tiles").innerHTML = FIELDS.map(f => {
      const now = latest[f.key], base = latest.baseline ? latest.baseline[f.key] : null;
      const inRegion = region === "whole_body" || f.region === region;
      // "Sleep last night" is shown like any other vital (owner's call,
      // 2026-11-14); only the 7-night log and lighting stay behind the gate.
      // Plain numbers: the difference from baseline is shown, never coloured as a warning.
      const p = deltaPct(now, base);
      const delta = p == null ? "" : ` (${p >= 0 ? "+" : "−"}${Math.abs(p).toFixed(f.deltaDp || 0)}%)`;
      // Stress is a 0-100 level, so its band reads better than a percentage.
      const show = x => (typeof x === "number" && f.dp != null ? x.toFixed(f.dp) : fmt(x));
      const reading = f.key === "stress_0to100"
        ? (now == null ? "needs HRV" : `${A.stressBand(now)}, usual ${fmt(base)}`)
        : `${latest.cycle && A.CYCLE_SHIFT[f.key] ? "cycle usual" : "usual"} ${show(base)}<span class="t-delta">${delta}</span>`;
      const cls = ["tile", inRegion ? "" : "dim", f.key === chartField ? "charted" : ""].join(" ");
      return `<button type="button" class="${cls}" data-key="${f.key}" aria-pressed="${f.key === chartField}">
        <span class="t-top"><span class="t-label">${f.label}</span>${A.vitalIcon(f.key)}</span>
        <span class="t-value">${show(now)}<span class="t-unit"> ${f.unit}</span></span>
        <span class="t-base">${reading}</span></button>`;
    }).join("");
  }

  let chart = null;

  function rebuildChart() {
    const field = FIELDS.find(f => f.key === chartField);
    $("chartTitle").textContent = `${field.label} (${field.unit})`;
    $("chartNote").textContent = field.key === "stress_0to100"
      ? "From your HRV vs your usual: lower HRV, higher level. Our scale (Apple Watch has none): 0-25 resting, 26-50 low, 51-75 medium, 76-100 high."
      : field.key === "bone_density_g_cm2" || field.key === "muscle_mass_kg"
        ? `${field.key === "bone_density_g_cm2" ? "Whole-body bone mineral density" : "Lean tissue of your arms and legs"} from the weekly portable X-ray (DXA) scan, so the line only moves between scans.${latest && latest.simulated_scan ? " Simulated scans for now." : ""}`
      : field.key === "hrv_sdnn_ms"
        ? "Heart-rate variability (SDNN), as Apple Watch records it. Dashed line: your usual."
        : PATTERN ? "The period picked above. Dashed line: your usual. Tap a reading to chart it."
        : "Last few minutes. Dashed line: your usual. Tap a reading to chart it.";
    if (!window.Chart) { $("chartFallback").hidden = false; $("chart").hidden = true; return; }
    if (chart) chart.destroy();
    const css = getComputedStyle(document.documentElement);
    const tok = name => css.getPropertyValue(name).trim();   // colours come from style.css tokens
    chart = new window.Chart($("chart"), {
      type: "line",
      data: {
        labels: history.map(p => tlabel(p.t)),
        datasets: [
          { label: field.label, data: history.map(p => p.v[chartField]), borderColor: tok("--accent"),
            pointRadius: 0, borderWidth: 2, tension: 0.3 },
          { label: "Your baseline", data: history.map(p => p.v.baseline?.[chartField]), borderColor: tok("--muted"),
            borderDash: [5, 5], pointRadius: 0, borderWidth: 1.5 },
        ],
      },
      options: {
        animation: false, responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { ticks: { color: tok("--muted"), maxTicksLimit: 6 }, grid: { color: tok("--line") } },
          y: { ticks: { color: tok("--muted") }, grid: { color: tok("--line") }, grace: "10%" },
        },
      },
    });
  }

  function pushChart() {
    if (!chart) { rebuildChart(); return; }
    const p = history[history.length - 1];
    chart.data.labels.push(tlabel(p.t));
    chart.data.datasets[0].data.push(p.v[chartField]);
    chart.data.datasets[1].data.push(p.v.baseline?.[chartField]);
    while (chart.data.labels.length > MAX_POINTS) {
      chart.data.labels.shift();
      chart.data.datasets.forEach(d => d.data.shift());
    }
    chart.update("none");
  }

  // ---- sleep & light: data only --------------------------------------------
  // From GET /astronauts/{id}/circadian (PROVISIONAL): the lighting mode and the
  // 7-night bedtime log. The backend's `card` / `recommendation` / `evidence`
  // texts are warnings and advice, so they are NOT shown here (the Commander
  // sees them). Without the endpoint only last night's hours are shown.

  const CIRC_REFRESH_MS = 60000;
  const CHART_START_H = 20, CHART_SPAN_MIN = 14 * 60;   // 20:00 -> 10:00 station time (UTC)
  let circ = null;

  async function loadCircadian() {
    try {
      circ = await A.getJSON(cfg.base, `/astronauts/${encodeURIComponent(cfg.aid)}/circadian?view=crew`, cfg.mock);
    } catch {
      circ = null;
    }
    renderCircadian();
  }

  function renderCircadian() {
    const live = !!circ;
    $("circLive").hidden = !live;
    $("lightChip").hidden = !live || !sleepRevealed;   // quarters' lighting is personal too
    if (!live) return;

    const L = circ.lighting || {};
    setLight();
    const since = L.since ? `, since ${utcTime(L.since)}` : "";
    $("lightChip").textContent = L.mode === "off" ? `Lights off${since}`
      : `${A.LIGHTING_NAMES[L.mode] || L.mode} light, ${L.cct_k} K${since}`;
    $("lightChip").className = `light-chip lc-${L.mode}`;

    $("nightsChart").innerHTML = (circ.nights || []).map(nightRow).join("") + axisRow();

    $("circShare").checked = !!circ.share_with_ground;
    $("circShareNote").textContent = circ.share_with_ground
      ? "Shared with Mission Control (the default). Untick to keep it on board."
      : "Not shared: Mission Control can't see your sleep and lighting summary. Tick to share again.";
  }

  // Last night's hours next to the astronaut's usual, as plain numbers.
  function renderSleep(v) {
    const h = v.sleep_h_last_night, base = v.baseline?.sleep_h_last_night;
    $("sleepNote").textContent = typeof h !== "number" ? "No sleep data yet."
      : `Last night: ${h} h${typeof base === "number" ? `, usually ${base} h` : ""}`;
  }

  // ---- shared-console privacy ----------------------------------------------
  // The ship console is a shared screen, so the 7-night sleep log and the
  // lighting are hidden until the astronaut taps "Show my sleep data", and
  // hide again on their own. Last night's hours are public (tile + note).

  const REVEAL_S = 120;
  let sleepRevealed = false;
  let hideAt = 0;

  function setRevealed(on) {
    sleepRevealed = on;
    hideAt = on ? Date.now() + REVEAL_S * 1000 : 0;
    $("sleepGate").hidden = on;
    $("sleepPrivate").hidden = !on;
    renderCircadian();
    updateHideIn();
  }

  function updateHideIn() {
    if (!sleepRevealed) return;
    const left = Math.max(0, Math.ceil((hideAt - Date.now()) / 1000));
    $("hideIn").textContent = `${Math.floor(left / 60)}:${String(left % 60).padStart(2, "0")}`;
    if (left === 0) setRevealed(false);
  }

  $("showSleep").addEventListener("click", () => setRevealed(true));
  $("hideSleep").addEventListener("click", () => setRevealed(false));
  // Using the card keeps it open; walking away lets it hide.
  document.querySelector(".sleep-light").addEventListener("pointerdown", () => { if (sleepRevealed) hideAt = Date.now() + REVEAL_S * 1000; });
  setInterval(updateHideIn, 1000);

  // Minutes from 20:00 UTC, so bedtimes either side of midnight line up.
  function chartMin(t) {
    const d = new Date(t);
    return ((d.getUTCHours() - CHART_START_H + 24) % 24) * 60 + d.getUTCMinutes();
  }
  const pct = m => `${Math.max(0, Math.min(100, (m / CHART_SPAN_MIN) * 100)).toFixed(2)}%`;

  function nightRow(n) {
    const start = chartMin(n.bedtime);
    const len = n.sleep_h * 60;
    const day = new Date(n.night_of + "T00:00:00Z").toLocaleDateString([], { weekday: "short", timeZone: "UTC" });
    const bright = n.bright_light_last_hour
      ? `<span class="n-bright" style="left:${pct(start - 60)};width:${pct(60)}" title="Bright light in the last hour before sleep"></span>` : "";
    return `<div class="n-row">
      <span class="n-day small muted">${esc(day)}</span>
      <span class="n-track">${bright}<span class="n-bar" style="left:${pct(start)};width:${pct(len)}"
        title="${esc(utcTime(n.bedtime))} → ${esc(utcTime(n.wake_time))}, ${n.sleep_h} h"></span></span>
      <span class="n-h small">${n.sleep_h} h</span></div>`;
  }

  function axisRow() {
    const ticks = [20, 0, 4, 8].map(h => {
      const m = ((h - CHART_START_H + 24) % 24) * 60;
      return `<span style="left:${pct(m)}">${String(h).padStart(2, "0")}:00</span>`;
    }).join("");
    return `<div class="n-row n-axis"><span class="n-day"></span><span class="n-track small muted">${ticks}</span><span class="n-h small muted">UTC</span></div>`;
  }

  $("circShare").addEventListener("change", async e => {
    const want = e.target.checked;
    e.target.disabled = true;
    try {
      await A.putJSON(cfg.base, `/astronauts/${encodeURIComponent(cfg.aid)}/circadian/sharing`, { share_with_ground: want }, cfg.mock);
      if (circ) circ.share_with_ground = want;
    } catch (err) {
      e.target.checked = !want;
      $("circShareNote").textContent = `Could not change sharing: ${err.message}`;
      e.target.disabled = false;
      return;
    }
    e.target.disabled = false;
    renderCircadian();
  });

  const utcTime = t => new Date(t).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", timeZone: "UTC", hour12: false });

  // ---- check-in ------------------------------------------------------------

  // One question at a time. Steps are the form's .ci-step blocks (the PHQ-2
  // ones are added once GET /checkin/questions answers). Every answer is
  // optional: Next reads "Skip" until the step is answered.
  let ciAt = 0;
  const ciSteps = () => [...$("checkin").querySelectorAll(".ci-step")];
  const ciAnswered = step => [...step.querySelectorAll("input")]
    .some(i => (i.type === "radio" || i.type === "checkbox") ? i.checked : i.value !== "");

  function ciShow(i) {
    const steps = ciSteps();
    ciAt = Math.max(0, Math.min(i, steps.length - 1));
    steps.forEach((s, k) => { s.hidden = k !== ciAt; });
    const last = ciAt === steps.length - 1, step = steps[ciAt];
    $("ciBack").hidden = ciAt === 0;
    $("ciNext").hidden = last;
    $("ciSubmit").hidden = !last;
    $("ciNext").textContent = ciAnswered(step) ? "Next" : step.dataset.step === "symptoms" ? "None of these" : "Skip";
    $("ciProgress").textContent = `Question ${ciAt + 1} of ${steps.length}`;
    $("ciBarFill").style.width = `${((ciAt + 1) / steps.length) * 100}%`;
  }

  $("ciBack").addEventListener("click", () => ciShow(ciAt - 1));
  $("ciNext").addEventListener("click", () => ciShow(ciAt + 1));
  $("checkin").addEventListener("change", () => ciShow(ciAt));
  $("checkin").addEventListener("input", () => ciShow(ciAt));
  // Enter in the hours box moves on instead of submitting early.
  $("checkin").addEventListener("keydown", e => {
    if (e.key === "Enter" && e.target.tagName === "INPUT" && ciAt < ciSteps().length - 1) { e.preventDefault(); ciShow(ciAt + 1); }
  });
  // Sleep +/-: half-hour steps, starting from the astronaut's usual.
  document.querySelectorAll("[data-sleep]").forEach(b => b.addEventListener("click", () => {
    const inp = $("checkin").sleep;
    const usual = Math.round((latest?.baseline?.sleep_h_last_night ?? 7) * 2) / 2;   // nearest half hour
    const start = inp.value !== "" ? Math.round(Number(inp.value) * 2) / 2 : usual - Number(b.dataset.sleep);
    inp.value = Math.max(0, Math.min(16, start + Number(b.dataset.sleep)));
    ciShow(ciAt);
  }));
  $("ciAgain").addEventListener("click", () => {
    $("checkin").reset(); $("checkinResult").textContent = "";
    $("ciDone").hidden = true; $("checkin").hidden = false; ciShow(0);
  });

  // PHQ-2: two more questions, wording from the backend (validated text).
  (async () => {
    let q;
    try { q = await A.getJSON(cfg.base, "/checkin/questions", cfg.mock); } catch { return; }
    if (!q?.phq2?.items) return;
    const nav = $("checkin").querySelector(".ci-nav");
    for (const item of q.phq2.items) {
      const step = document.createElement("div");
      step.className = "ci-step"; step.dataset.step = `phq2_${item.key}`; step.hidden = true;
      step.innerHTML = `<p class="ci-hint muted">${esc(q.phq2.stem)}</p>
        <p class="ci-q">${esc(item.text)}</p>
        <div class="ci-options ci-four" role="radiogroup" aria-label="${esc(item.text)}">
          ${q.phq2.options.map(o => `<label><input type="radio" name="phq2_${esc(item.key)}" value="${o.value}"><span>${esc(o.label)}</span></label>`).join("")}
        </div>
        <p class="ci-source muted small">${esc(q.phq2.source)}</p>`;
      $("checkin").insertBefore(step, nav);
    }
    ciShow(ciAt);
  })();
  ciShow(0);

  async function onCheckin(e) {
    e.preventDefault();
    const f = e.target;
    // Always shared with Mission Control: no box for it (owner's call, 2026-11-14).
    const body = { timestamp: new Date().toISOString().replace(/\.\d+Z$/, "Z"), share_with_ground: true };
    const mood = f.querySelector('input[name="mood"]:checked');
    if (mood) body.mood_1to5 = Number(mood.value);
    if (f.sleep.value !== "" && Number.isFinite(Number(f.sleep.value))) body.sleep_h = Math.max(0, Math.min(16, Number(f.sleep.value)));
    const symptoms = [...f.querySelectorAll('input[name="symptom"]:checked')].map(i => i.value);
    if (symptoms.length) body.symptoms = symptoms;
    // PHQ-2 only when both items are answered (the API needs both).
    const li = f.querySelector('input[name="phq2_little_interest"]:checked');
    const fd = f.querySelector('input[name="phq2_feeling_down"]:checked');
    if (li && fd) body.phq2 = { little_interest: Number(li.value), feeling_down: Number(fd.value) };

    const out = $("checkinResult");
    out.className = "ci-result muted";
    out.textContent = "Sending…";
    try {
      await A.postJSON(cfg.base, `/astronauts/${encodeURIComponent(cfg.aid)}/checkin`, body, cfg.mock);
      out.textContent = "";
      f.hidden = true;
      $("ciDone").hidden = false;
      $("ciProgress").textContent = "Done";
    } catch (err) {
      out.className = "ci-result err";
      out.textContent = `Could not save: ${err.message}`;
    }
  }

  // ---- status --------------------------------------------------------------

  function renderMission() {
    if (!mission) { $("mission").textContent = "Mission unknown"; return; }
    const realS = mission.real_one_way_delay_s ?? mission.one_way_delay_s;
    const demo = realS > mission.one_way_delay_s ? ` <span class="muted">(demo: ${dur(mission.one_way_delay_s)})</span>` : "";
    const where = mission.environment === "mars" ? "Earth" : "Ground";
    $("mission").innerHTML = `${where} is <strong>${dur(realS)}</strong> away${demo}`;
  }

  function renderAge() {
    const el = $("age");
    if (!lastVitalsAt) { el.textContent = "waiting"; el.className = ""; return; }
    if (PATTERN) { el.textContent = window.AHMPattern.label(lastVitalsAt); el.className = ""; return; }
    const s = Math.max(0, Math.round((Date.now() - lastVitalsAt) / 1000));
    el.textContent = `${dur(s)} ago`;
    el.className = s > STALE_S ? "stale" : "";
  }

  // ---- colour scheme ---------------------------------------------------------
  // Always the dark theme (owner, 2026-11-14): the page no longer switches to
  // the warm Pre-sleep palette with the module's lighting (`mode` is ignored;
  // the Sleep & light tab still shows the lighting). ?light=pre_sleep or
  // ?light=off on the URL (set by auth.js) still shows the warm set for a demo.
  // The chart reads colours from CSS, so it is rebuilt when the set changes.
  const forcedLight = new URLSearchParams(location.search).get("light");
  function setLight() {
    const want = forcedLight || "general";
    if ($("lightNote")) $("lightNote").hidden = !(want === "pre_sleep" || want === "off");
    if (document.documentElement.dataset.light === want) return;
    document.documentElement.dataset.light = want;
    if (chart) setTimeout(rebuildChart, 850);   // after the CSS colour fade
  }
  setLight();

  function setConn(text, cls) { const el = $("conn"); el.textContent = text; el.className = `pill ${cls}`; }

  const tlabel = t => (PATTERN ? window.AHMPattern.shortLabel(t) : time(t));

  function time(t) {
    const d = t instanceof Date ? t : new Date(t);
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  }

  // ---- console menu: one tab visible at a time ------------------------------
  // The URL hash is the tab (#health, #checkin, #sleep, plus #crew / #meds on
  // the Commander's / doctor's page), so a tab can be linked to. The tabs are
  // the page's [data-tab-link] menu entries; the first is the default. Kept at
  // the end of the file: it touches `chart`, declared above.
  const TABS = [...document.querySelectorAll("[data-tab-link]")].map(a => a.dataset.tabLink);

  function showTab() {
    const want = location.hash.slice(1);
    const tab = TABS.includes(want) ? want : TABS[0] || "health";
    document.body.dataset.tab = tab;   // style.css: My health stretches to the window's height
    document.querySelectorAll("[data-tab]").forEach(s => { s.hidden = s.dataset.tab !== tab; });
    document.querySelectorAll("[data-tab-link]").forEach(a => {
      if (a.dataset.tabLink === tab) a.setAttribute("aria-current", "page");
      else a.removeAttribute("aria-current");
    });
    if (tab === "health" && chart) chart.resize();   // canvas was hidden; refit it
  }

  window.addEventListener("hashchange", showTab);
  showTab();

  // ---- console markup ------------------------------------------------------

  // One copy for every page that shows a crew member's own data: the astronaut
  // console and the Commander's and Crew Medical Officer's profiles. Injected into
  // #console. A hoisted function, so it can sit at the end of the file.
  function consoleMarkup() {
    return `
    <section class="card body-card" data-tab="health">
      <div class="body-head">
        <h2>Body <span class="muted">tap a region</span></h2>
        <div class="sex-switch" id="sexSwitch" role="radiogroup" aria-label="Body shape">
          <input type="radio" name="sex" id="sexM" value="male" checked><label for="sexM">Male</label>
          <input type="radio" name="sex" id="sexF" value="female"><label for="sexF">Female</label>
          <span class="sex-thumb" aria-hidden="true"></span>
        </div>
        <button type="button" class="cycle-btn" id="cycleBtn" aria-haspopup="dialog" hidden>Cycle</button>
      </div>
      <svg id="body" viewBox="0 0 200 400" role="group" aria-label="Body regions">
        <!-- Front view of a person standing in the anatomical position, palms
             forward, so the astronaut's left is the viewer's right. One solid
             silhouette: head, torso and limbs are separate tap regions filled and
             edged in the same colour, so the seams only show on hover/selection.
             Limbs are drawn first (the deltoids and pelvis overlap their tops), the
             head last (it overlaps the neck). The data-part paths are swapped for
             the male or female figure by setSex() (shapes in common.js BODY_SHAPES).
             "Whole body" outlines the whole figure through the filter below
             (style.css), not the torso piece. -->
        <defs>
          <filter id="bodyOutline" x="-5%" y="-5%" width="110%" height="110%">
            <feMorphology in="SourceAlpha" operator="dilate" radius="1.3" result="grow"/>
            <feFlood/>
            <feComposite in2="grow" operator="in" result="ring"/>
            <feMerge><feMergeNode in="ring"/><feMergeNode in="SourceGraphic"/></feMerge>
          </filter>
        </defs>
        <g class="figure">
        <g class="region" data-region="skin" tabindex="0" role="button" aria-label="Skin">
          <path data-part="armL" d="M59.9 79.2 C57.4 75.3 51.5 80.9 48.8 83.7 C46.1 86.5 44.5 91.5 43.8 95.9 C43 100.4 44 105.6 44.3 110.4 C44.7 115.2 45.9 120 46 124.9 C46.1 129.7 45.6 134.6 44.9 139.3 C44.2 144.1 42.8 149 41.6 153.3 C40.4 157.5 38.9 161.2 37.7 164.9 C36.5 168.6 35.4 172.2 34.3 175.5 C33.3 178.9 32.4 182.6 31.5 185 C30.7 187.4 30.3 188.4 29.3 190 C28.3 191.6 26.6 193 25.4 194.4 C24.2 195.8 22.7 197.1 22.1 198.3 C21.4 199.5 21.3 200.9 21.5 201.7 C21.8 202.4 22.7 203 23.8 202.8 C24.8 202.6 27.3 200.1 27.7 200.6 C28 201 28.4 205.8 28.2 208.3 C28 210.9 26.7 214.1 26.5 216.1 C26.4 218.2 26.6 219.8 27.1 220.6 C27.6 221.3 28.8 221.6 29.3 220.6 C29.9 219.6 30.1 216.5 30.4 214.5 C30.8 212.4 31.4 208.2 31.5 208.3 C31.7 208.5 32.3 214.2 32.7 216.7 C33 219.2 33.2 222.3 33.8 223.4 C34.3 224.5 35.5 224.6 36 223.4 C36.5 222.2 36.4 218.6 36.6 216.1 C36.7 213.7 37 208.9 37.1 208.9 C37.2 208.9 38.2 214.5 38.8 216.7 C39.3 218.9 39.8 221.4 40.5 222.3 C41.1 223.1 42.3 223 42.7 221.7 C43 220.4 42.6 216.7 42.7 214.5 C42.8 212.2 43.1 208.4 43.2 208.3 C43.3 208.3 44.3 212.2 44.9 213.9 C45.5 215.6 45.9 217.8 46.6 218.4 C47.2 218.9 48.5 218.6 48.8 217.3 C49.1 216 48.4 213.2 48.2 210.6 C48.1 208 47.9 205.4 47.7 201.7 C47.5 198 46.5 192.8 47.1 188.3 C47.8 183.9 50.1 179.2 51.6 175 C53.1 170.7 54.7 166.8 56 162.7 C57.3 158.6 58.4 154.7 59.4 150.5 C60.4 146.2 61.3 141.2 62.2 137.1 C63 133 64.1 131 64.4 126 C64.7 121 64.6 114.9 63.8 107.1 C63.1 99.3 62.4 83.1 59.9 79.2 Z"/>
          <path data-part="armR" d="M136.2 107.1 C135.4 114.9 135.3 121 135.6 126 C135.9 131 137 133 137.8 137.1 C138.7 141.2 139.6 146.2 140.6 150.5 C141.6 154.7 142.7 158.6 144 162.7 C145.3 166.8 146.9 170.7 148.4 175 C149.9 179.2 152.2 183.9 152.9 188.3 C153.5 192.8 152.5 198 152.3 201.7 C152.1 205.4 151.9 208 151.8 210.6 C151.6 213.2 150.9 216 151.2 217.3 C151.5 218.6 152.8 218.9 153.4 218.4 C154.1 217.8 154.5 215.6 155.1 213.9 C155.7 212.2 156.7 208.3 156.8 208.3 C156.9 208.4 157.2 212.2 157.3 214.5 C157.4 216.7 157 220.4 157.3 221.7 C157.7 223 158.9 223.1 159.5 222.3 C160.2 221.4 160.7 218.9 161.2 216.7 C161.8 214.5 162.8 208.9 162.9 208.9 C163 208.9 163.3 213.7 163.4 216.1 C163.6 218.6 163.5 222.2 164 223.4 C164.5 224.6 165.7 224.5 166.2 223.4 C166.8 222.3 167 219.2 167.3 216.7 C167.7 214.2 168.3 208.5 168.5 208.3 C168.6 208.2 169.2 212.4 169.6 214.5 C169.9 216.5 170.1 219.6 170.7 220.6 C171.2 221.6 172.4 221.3 172.9 220.6 C173.4 219.8 173.6 218.2 173.5 216.1 C173.3 214.1 172 210.9 171.8 208.3 C171.6 205.8 172 201 172.3 200.6 C172.7 200.1 175.2 202.6 176.2 202.8 C177.3 203 178.2 202.4 178.5 201.7 C178.7 200.9 178.6 199.5 177.9 198.3 C177.3 197.1 175.8 195.8 174.6 194.4 C173.4 193 171.7 191.6 170.7 190 C169.7 188.4 169.3 187.4 168.5 185 C167.6 182.6 166.7 178.9 165.7 175.5 C164.6 172.2 163.5 168.6 162.3 164.9 C161.1 161.2 159.6 157.5 158.4 153.3 C157.2 149 155.8 144.1 155.1 139.3 C154.4 134.6 153.9 129.7 154 124.9 C154.1 120 155.3 115.2 155.7 110.4 C156 105.6 157 100.4 156.2 95.9 C155.5 91.5 153.9 86.5 151.2 83.7 C148.5 80.9 142.6 75.3 140.1 79.2 C137.6 83.1 136.9 99.3 136.2 107.1 Z"/>
          <path data-part="legL" d="M85.5 157.1 C80.5 154 72.6 158.1 69.9 160.5 C67.3 162.9 69.8 167 69.4 171.6 C69 176.3 68.2 181.8 67.7 188.3 C67.3 194.8 66.6 203.5 66.6 210.6 C66.6 217.6 67.2 223.6 67.7 230.6 C68.3 237.7 69.1 245.6 69.9 252.9 C70.8 260.1 71.9 268.3 72.7 274 C73.6 279.8 74.9 283.1 75 287.4 C75 291.6 73.8 295.2 73.3 299.6 C72.7 304.1 71.6 308.9 71.6 314.1 C71.6 319.3 72.4 325.2 73.3 330.8 C74.2 336.3 76 342.7 77.2 347.5 C78.4 352.2 80.4 355.6 80.5 359.2 C80.6 362.7 78.8 365.4 77.7 368.6 C76.7 371.9 75.1 375.7 74.4 378.6 C73.7 381.6 73 384.3 73.3 386.4 C73.6 388.6 74.8 390.8 76.1 391.4 C77.4 392.1 81.7 392 84.4 392 C87.1 392 91 392 92.2 391.4 C93.4 390.9 94.5 389.5 95 387.5 C95.5 385.6 95.2 382.7 95 379.8 C94.8 376.8 94.2 373.3 93.9 369.7 C93.6 366.2 93.5 363.4 93.3 358.6 C93.1 353.8 92.6 346.7 92.8 340.8 C93 334.9 94.1 328.6 94.4 323 C94.8 317.4 95 312.3 95 307.4 C95 302.5 94.5 297.8 94.4 293.5 C94.3 289.2 94.2 287.8 94.4 281.8 C94.7 275.8 95.6 265.1 96.1 257.3 C96.6 249.5 96.8 241.9 97.2 235.1 C97.6 228.2 97.9 220.8 98.3 216.1 C98.8 211.5 99.7 213.4 100 207.2 C100.3 201.1 102.4 187.8 100 179.4 C97.6 171.1 90.5 160.3 85.5 157.1 Z"/>
          <path data-part="legR" d="M100 179.4 C97.6 187.8 99.7 201.1 100 207.2 C100.3 213.4 101.2 211.5 101.7 216.1 C102.1 220.8 102.4 228.2 102.8 235.1 C103.2 241.9 103.4 249.5 103.9 257.3 C104.4 265.1 105.3 275.8 105.6 281.8 C105.8 287.8 105.7 289.2 105.6 293.5 C105.5 297.8 105 302.5 105 307.4 C105 312.3 105.2 317.4 105.6 323 C105.9 328.6 107 334.9 107.2 340.8 C107.4 346.7 106.9 353.8 106.7 358.6 C106.5 363.4 106.4 366.2 106.1 369.7 C105.8 373.3 105.2 376.8 105 379.8 C104.8 382.7 104.5 385.6 105 387.5 C105.5 389.5 106.6 390.9 107.8 391.4 C109 392 112.9 392 115.6 392 C118.3 392 122.6 392.1 123.9 391.4 C125.2 390.8 126.4 388.6 126.7 386.4 C127 384.3 126.3 381.6 125.6 378.6 C124.9 375.7 123.3 371.9 122.3 368.6 C121.2 365.4 119.4 362.7 119.5 359.2 C119.6 355.6 121.6 352.2 122.8 347.5 C124 342.7 125.8 336.3 126.7 330.8 C127.6 325.2 128.4 319.3 128.4 314.1 C128.4 308.9 127.3 304.1 126.7 299.6 C126.2 295.2 125 291.6 125 287.4 C125.1 283.1 126.4 279.8 127.3 274 C128.1 268.3 129.2 260.1 130.1 252.9 C130.9 245.6 131.7 237.7 132.3 230.6 C132.8 223.6 133.4 217.6 133.4 210.6 C133.4 203.5 132.7 194.8 132.3 188.3 C131.8 181.8 131 176.3 130.6 171.6 C130.2 167 132.7 162.9 130.1 160.5 C127.4 158.1 119.5 154 114.5 157.1 C109.5 160.3 102.4 171.1 100 179.4 Z"/>
        </g>
        <g class="region" data-region="whole_body" tabindex="0" role="button" aria-label="Whole body">
          <path data-part="torso" d="M87.8 42.5 C83.6 44.4 87.6 50.7 87.2 53.6 C86.8 56.6 86.8 58.9 85.5 60.3 C84.3 61.7 80.7 63 77.7 64.2 C74.8 65.4 71.2 66.3 67.7 67.5 C64.2 68.8 59.8 69.7 56.6 71.4 C53.3 73.2 50.4 75.2 48.2 78.1 C46.1 81.1 44.6 85.2 43.8 89.3 C43 93.3 42.4 98.4 43.2 102.6 C44.1 106.8 46.4 111.3 48.8 114.3 C51.2 117.3 55 118.7 57.7 120.4 C60.4 122.2 63.5 121.3 64.9 124.9 C66.4 128.4 66.1 136 66.6 141.6 C67.2 147.1 67.8 153.3 68.3 158.3 C68.7 163.3 68.7 167 69.4 171.6 C70 176.3 70.6 181.8 72.2 186.1 C73.8 190.4 75.9 194.4 78.9 197.2 C81.8 200 86.5 201.3 90 202.8 C93.5 204.3 96.7 206.1 100 206.1 C103.3 206.1 106.5 204.3 110 202.8 C113.5 201.3 118.2 200 121.1 197.2 C124.1 194.4 126.2 190.4 127.8 186.1 C129.4 181.8 130 176.3 130.6 171.6 C131.3 167 131.3 163.3 131.7 158.3 C132.2 153.3 132.8 147.1 133.4 141.6 C133.9 136 133.6 128.4 135.1 124.9 C136.5 121.3 139.6 122.2 142.3 120.4 C145 118.7 148.8 117.3 151.2 114.3 C153.6 111.3 155.9 106.8 156.8 102.6 C157.6 98.4 157 93.3 156.2 89.3 C155.4 85.2 153.9 81.1 151.8 78.1 C149.6 75.2 146.7 73.2 143.4 71.4 C140.2 69.7 135.8 68.8 132.3 67.5 C128.8 66.3 125.2 65.4 122.3 64.2 C119.3 63 115.7 61.7 114.5 60.3 C113.2 58.9 113.2 56.6 112.8 53.6 C112.4 50.7 116.4 44.4 112.2 42.5 C108.1 40.6 91.9 40.6 87.8 42.5 Z"/>
        </g>
        <!-- Heart is drawn BEFORE the lungs so the lungs overlap it, as in a
             real front view: it shows between the lungs and in the cardiac
             notch. Flat anatomical icon, not a valentine: ventricles tapering to
             the apex (down, astronaut's left, resting on the diaphragm), the
             superior vena cava on the astronaut's right, the aortic arch with
             its three branches. -->
        <g class="region" data-region="heart" tabindex="0" role="button" aria-label="Heart">
          ${A.BODY_ORGANS.heart}
        </g>
        <!-- Lungs: narrow rounded apex just above the collarbone, broad base curving
             over the diaphragm dome, straight inner (medial) border. The
             astronaut's left lung (viewer's right) is narrower and has the
             cardiac notch where the heart shows through. -->
        <g class="region" data-region="lungs" tabindex="0" role="button" aria-label="Lungs">
          ${A.BODY_ORGANS.lungs}
        </g>
        <g class="region" data-region="head" tabindex="0" role="button" aria-label="Head">
          <path data-part="earL" d="M81.6 32.5 C81 30.1 79 30.6 78.3 31.4 C77.6 32.1 77.1 34.9 77.2 36.9 C77.3 39 78 42.1 78.9 43.6 C79.7 45.1 81.7 47.7 82.2 45.8 C82.7 44 82.3 34.9 81.6 32.5 Z"/>
          <path data-part="earR" d="M117.8 45.8 C118.3 47.7 120.3 45.1 121.1 43.6 C122 42.1 122.7 39 122.8 36.9 C122.9 34.9 122.4 32.1 121.7 31.4 C121 30.6 119 30.1 118.4 32.5 C117.7 34.9 117.3 44 117.8 45.8 Z"/>
          <path data-part="head" d="M100 8 C96.7 8 92.8 8.6 90 10.2 C87.2 11.9 84.8 14.9 83.3 18 C81.8 21.2 81.3 25.4 81.1 29.1 C80.9 32.9 81.4 37.1 82.2 40.3 C82.9 43.4 83.9 45.8 85.5 48.1 C87.2 50.3 89.8 52.3 92.2 53.6 C94.6 54.9 97.4 55.9 100 55.9 C102.6 55.9 105.4 54.9 107.8 53.6 C110.2 52.3 112.8 50.3 114.5 48.1 C116.1 45.8 117.1 43.4 117.8 40.3 C118.6 37.1 119.1 32.9 118.9 29.1 C118.7 25.4 118.2 21.2 116.7 18 C115.2 14.9 112.8 11.9 110 10.2 C107.2 8.6 103.3 8 100 8 Z"/>
        </g>
        </g>
      </svg>
      <div id="regionInfo" class="region-info"></div>
      <dialog id="cycleDlg" class="cycle-dlg" aria-labelledby="cycleTitle">
        <form method="dialog" id="cycleForm">
          <h2 id="cycleTitle">Cycle-aware usual</h2>
          <p class="small">Temperature, resting heart rate and HRV change over the menstrual cycle. With this on
            they are compared with your usual for the same phase, so a normal monthly rise is not flagged and a
            real fever still is.</p>
          <label>First day of your last period <input type="date" name="start" required></label>
          <label>Usual cycle length <span class="cycle-len"><input type="number" name="len" min="21" max="40" value="28" required> days</span></label>
          <p class="muted small">Private: only your own console shows the cycle. Other views compare your readings
            with the adjusted usual and never show the cycle itself. Saved in this browser.</p>
          <div class="dlg-actions">
            <button value="save">Turn on</button>
            <button value="off" id="cycleOff" class="link" formnovalidate>Turn off</button>
            <button value="cancel" class="link" formnovalidate>Cancel</button>
          </div>
        </form>
      </dialog>
    </section>

    <section class="card vitals-card" data-tab="health">
      <h2>Your vitals <span class="muted">vs. your own baseline</span></h2>
      <div id="tiles" class="tiles"><p class="muted">Waiting for data…</p></div>
      <div class="chart-wrap">
        <div class="chart-head"><strong id="chartTitle">Heart rate</strong> <span class="muted small" id="chartNote">Last few minutes. Dashed line: your usual. Tap a reading to chart it.</span></div>
        <!-- The chart fills whatever height the card has left (style.css). -->
        <div class="chart-box"><canvas id="chart"></canvas></div>
        <p id="chartFallback" class="muted small" hidden>Chart unavailable (Chart.js did not load — offline?).</p>
      </div>
    </section>

    <!-- Check-in: one question at a time with Back / Next (owner's call,
         2026-11-14). Every answer is optional. No "share with ground" box:
         check-ins are always shared with Mission Control (owner's call). The
         PHQ-2 steps are added from GET /checkin/questions (exact wording). -->
    <section class="card checkin-card solo" data-tab="checkin">
      <div class="ci-head"><h2>Check-in</h2><span id="ciProgress" class="muted"></span></div>
      <div class="ci-bar" aria-hidden="true"><div id="ciBarFill"></div></div>
      <!-- novalidate: a field on a hidden step can't show the browser's bubble,
           so it would block Submit silently; values are clamped in onCheckin. -->
      <form id="checkin" class="checkin ci-wizard" autocomplete="off" novalidate>
        <div class="ci-step" data-step="mood">
          <p class="ci-q">How is your mood today?</p>
          <div class="ci-options ci-five" role="radiogroup" aria-label="Mood, 1 to 5">
            <label><input type="radio" name="mood" value="1"><span class="ci-num">1</span><span class="ci-cap">Very low</span></label>
            <label><input type="radio" name="mood" value="2"><span class="ci-num">2</span><span class="ci-cap">Low</span></label>
            <label><input type="radio" name="mood" value="3"><span class="ci-num">3</span><span class="ci-cap">OK</span></label>
            <label><input type="radio" name="mood" value="4"><span class="ci-num">4</span><span class="ci-cap">Good</span></label>
            <label><input type="radio" name="mood" value="5"><span class="ci-num">5</span><span class="ci-cap">Very good</span></label>
          </div>
        </div>

        <div class="ci-step" data-step="sleep" hidden>
          <p class="ci-q">How many hours did you sleep last night?</p>
          <div class="ci-number">
            <button type="button" class="ci-step-btn" data-sleep="-0.5" aria-label="Half an hour less">−</button>
            <input type="number" name="sleep" min="0" max="16" step="0.5" inputmode="decimal" placeholder="—" aria-label="Hours of sleep">
            <span class="ci-unit">h</span>
            <button type="button" class="ci-step-btn" data-sleep="0.5" aria-label="Half an hour more">+</button>
          </div>
        </div>

        <div class="ci-step" data-step="symptoms" hidden>
          <p class="ci-q">Any of these today?</p>
          <p class="ci-hint muted">Tick all that apply.</p>
          <div class="ci-options ci-chips">
            <label><input type="checkbox" name="symptom" value="headache"><span>Headache</span></label>
            <label><input type="checkbox" name="symptom" value="blurred_vision"><span>Blurred vision</span></label>
            <label><input type="checkbox" name="symptom" value="dizziness"><span>Dizziness</span></label>
            <label><input type="checkbox" name="symptom" value="nausea"><span>Nausea</span></label>
            <label><input type="checkbox" name="symptom" value="congestion"><span>Congestion</span></label>
            <label><input type="checkbox" name="symptom" value="fatigue"><span>Fatigue</span></label>
          </div>
        </div>

        <div class="ci-nav">
          <button type="button" id="ciBack" class="ci-secondary">Back</button>
          <button type="button" id="ciNext">Next</button>
          <button type="submit" id="ciSubmit" hidden>Submit check-in</button>
        </div>
        <p id="checkinResult" class="ci-result" aria-live="polite"></p>
      </form>

      <div id="ciDone" class="ci-done" hidden>
        <p class="ci-q">Check-in saved. Thank you.</p>
        <button type="button" id="ciAgain">New check-in</button>
      </div>
    </section>

    <!-- Light & sleep: suggestion from our mentor/judge (events/2026-11-14-mentor-judges.md).
         Live data from GET /astronauts/{id}/circadian (PROVISIONAL in the spec);
         if that endpoint is missing, only the static guidance below is shown. -->
    <section class="card sleep-light solo" data-tab="sleep">
      <h2>Light &amp; sleep <span id="lightChip" class="light-chip" hidden></span></h2>

      <!-- Last night's hours are public; the 7-night log and lighting are
           hidden on this shared screen until the astronaut asks, and re-hide. -->
      <p id="sleepNote" class="sleep-note muted">Waiting for data…</p>

      <div id="sleepGate" class="sleep-gate">
        <p class="muted">Your 7-night sleep log and lighting are hidden on this shared console.</p>
        <button type="button" id="showSleep">Show my sleep data</button>
      </div>

      <div id="sleepPrivate" hidden>
      <div class="private-bar small muted">
        <span>Visible to anyone near this console. Hides again in <span id="hideIn">2:00</span>.</span>
        <button type="button" id="hideSleep" class="link">Hide now</button>
      </div>

      <div id="circLive" hidden>
        <div class="nights-head small muted">Last 7 nights. Bars show when you slept; <span class="lg-bright">■</span> marks bright light in the hour before.</div>
        <div id="nightsChart" class="nights"></div>
        <label class="row share">
          <input type="checkbox" id="circShare"> Share sleep &amp; lighting with ground
        </label>
        <p id="circShareNote" class="muted small">Mission Control sees this by default. Untick to keep it on board.</p>
      </div>
      </div>

      <details id="tipsBox">
        <summary>How the station's lighting modes work</summary>
      <ul class="tips">
        <li><strong>1 h before sleep:</strong> switch your module lights to
          <em>Pre-sleep</em> mode (about 2700 K, blue-depleted). Blue light around
          460 nm is what suppresses melatonin most.</li>
        <li><strong>In that hour:</strong> keep screens dim or off.</li>
        <li><strong>Working day:</strong> <em>General</em> mode (about 4500 K).
          If a schedule shift is coming, <em>Phase-shift</em> mode (about 6500 K,
          blue-enriched) helps move your body clock.</li>
        <li><strong>Why it matters up here:</strong> the station sees about 16
          sunrises a day, so its lights are your clock. A disrupted clock is
          associated with weaker immune defence.</li>
      </ul>
      </details>
      <p id="staticEvidence" class="muted small">Evidence on light, sleep timing and immunity is still
        emerging, much of it from animal studies. Suggestions, not a diagnosis.</p>
      <div class="nasa-ref small">
        Sources: <a href="https://ntrs.nasa.gov/citations/20160005080" target="_blank" rel="noopener">NASA ISS Solid-State Lighting Assembly (NTRS)</a>
        and NASA risk <a href="https://www.nasa.gov/reference/risk-from-inadequate-sleep-and-irregular-schedules/" target="_blank" rel="noopener">Risk of Inadequate Sleep and Irregular Schedules</a>
      </div>
    </section>
`;
  }
})();
