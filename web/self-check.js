// Astronaut console: a crew member's own data. Live (view=crew).
//
// DATA ONLY, NO WARNINGS (decision, NotKaemy 2026-11-14): crew members see
// their own numbers against their own baseline, never alerts, verdicts,
// advice or "something is wrong" wording. Warnings go to the Commander
// (captain.html), the ship's doctor (doctor.html) and Ground. This code does
// not even subscribe to `alert` events.
//
// Used by three pages, each with an empty <main id="console">:
// - self-check.html: any astronaut, picked with the #aid selector (?aid=).
// - captain.html / doctor.html: the Commander's / ship's doctor's own data,
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

  $("tiles").addEventListener("click", e => {
    const tile = e.target.closest(".tile");
    if (tile) { chartField = tile.dataset.key; renderTiles(); rebuildChart(); }
  });

  $("checkin").addEventListener("submit", onCheckin);

  init();

  async function init() {
    try {
      const crew = await A.getJSON(cfg.base, "/crew", cfg.mock);
      // Commander / ship's doctor: whoever holds that role on this crew.
      const own = ownRole && crew.find(c => c.role === ownRole);
      if (own) cfg.aid = own.id;
      const me = crew.find(c => c.id === cfg.aid);
      $("name").textContent = me ? me.name : cfg.aid;
      $("role").textContent = me ? `${me.role} (${me.id})` : "";
    } catch { $("name").textContent = cfg.aid; }

    try { mission = await A.getJSON(cfg.base, "/mission", cfg.mock); } catch { mission = null; }
    renderMission();

    // No "alert" listener or alert polling on purpose: data only.
    if (POLL) startPolling();
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

  function onVitals(v) {
    latest = v;
    lastVitalsAt = new Date(v.timestamp);
    history.push({ t: lastVitalsAt, v });
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

  function renderRegionInfo() {
    const fields = FIELDS.filter(f => region === "whole_body" || f.region === region).map(f => f.label);
    const note = region === "head" ? " Sleep and mood (in Check-in) belong here."
      : region === "skin" ? " Temperature is measured here." : "";
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
      const delta = p == null ? "" : ` (${p >= 0 ? "+" : "−"}${Math.abs(p).toFixed(0)}%)`;
      const cls = ["tile", inRegion ? "" : "dim", f.key === chartField ? "charted" : ""].join(" ");
      return `<button type="button" class="${cls}" data-key="${f.key}" aria-pressed="${f.key === chartField}">
        <span class="t-top"><span class="t-label">${f.label}</span>${A.vitalIcon(f.key)}</span>
        <span class="t-value">${fmt(now)}<span class="t-unit"> ${f.unit}</span></span>
        <span class="t-base">usual ${fmt(base)}<span class="t-delta">${delta}</span></span></button>`;
    }).join("");
  }

  let chart = null;

  function rebuildChart() {
    const field = FIELDS.find(f => f.key === chartField);
    $("chartTitle").textContent = `${field.label} (${field.unit})`;
    if (!window.Chart) { $("chartFallback").hidden = false; $("chart").hidden = true; return; }
    if (chart) chart.destroy();
    const css = getComputedStyle(document.documentElement);
    const tok = name => css.getPropertyValue(name).trim();   // colours come from style.css tokens
    chart = new window.Chart($("chart"), {
      type: "line",
      data: {
        labels: history.map(p => time(p.t)),
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
    chart.data.labels.push(time(p.t));
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
    setLight(L.mode);
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
    const s = Math.max(0, Math.round((Date.now() - lastVitalsAt) / 1000));
    el.textContent = `${dur(s)} ago`;
    el.className = s > STALE_S ? "stale" : "";
  }

  // ---- the console follows the module's lighting -----------------------------
  // Pre-sleep (2700 K) or lights off: html[data-light] switches style.css to the
  // dark, warm, blue-free set, as the Sleep & light tab advises. ?light=… (set
  // by auth.js) overrides it for a demo. The chart reads colours from CSS, so
  // it is rebuilt when the light changes.
  const forcedLight = new URLSearchParams(location.search).get("light");
  function setLight(mode) {
    const want = forcedLight || mode || "general";
    if ($("lightNote")) $("lightNote").hidden = !(want === "pre_sleep" || want === "off");
    if (document.documentElement.dataset.light === want) return;
    document.documentElement.dataset.light = want;
    try { sessionStorage.setItem("ahm-light", want); } catch { /* fine without */ }
    if (chart) setTimeout(rebuildChart, 850);   // after the CSS colour fade
  }
  setLight(document.documentElement.dataset.light);   // note for a mode restored by auth.js

  function setConn(text, cls) { const el = $("conn"); el.textContent = text; el.className = `pill ${cls}`; }

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
  // console and the Commander's and ship's doctor's profiles. Injected into
  // #console. A hoisted function, so it can sit at the end of the file.
  function consoleMarkup() {
    return `
    <section class="card body-card" data-tab="health">
      <h2>Body <span class="muted">tap a region</span></h2>
      <svg id="body" viewBox="0 0 200 400" role="group" aria-label="Body regions">
        <g class="region" data-region="skin" tabindex="0" role="button" aria-label="Skin">
          <rect x="30" y="92" width="22" height="125" rx="11"/>
          <rect x="148" y="92" width="22" height="125" rx="11"/>
          <rect x="66" y="222" width="30" height="160" rx="13"/>
          <rect x="104" y="222" width="30" height="160" rx="13"/>
        </g>
        <g class="region" data-region="whole_body" tabindex="0" role="button" aria-label="Whole body">
          <rect x="88" y="72" width="24" height="18" rx="4"/>
          <rect x="58" y="86" width="84" height="142" rx="22"/>
        </g>
        <!-- Front view, so the astronaut's left is the viewer's right.
             Heart is drawn BEFORE the lungs so the lungs overlap it, as in a
             real front view: it shows between the lungs and in the cardiac
             notch. Flat anatomical icon, not a valentine: ventricles tapering to
             the apex (down, astronaut's left, resting on the diaphragm), the
             superior vena cava on the astronaut's right, the aortic arch with
             its three branches. -->
        <g class="region" data-region="heart" tabindex="0" role="button" aria-label="Heart">
          <!-- superior vena cava -->
          <rect x="95.5" y="121" width="4.5" height="21" rx="2"/>
          <!-- aortic arch branches: brachiocephalic, left common carotid, left subclavian -->
          <rect x="101.6" y="114" width="2.4" height="9" rx="1.2"/>
          <rect x="105" y="112" width="2.4" height="10" rx="1.2"/>
          <rect x="108.6" y="114" width="2.4" height="8" rx="1.2"/>
          <!-- ascending aorta and arch, descending behind the left lung -->
          <path d="M100.5 141 L100.5 129 C100.5 119 114 119 114 128 L114 136 L109.5 136 L109.5 128.5
                   C109.5 124 105 124 105 129 L105 141 Z"/>
          <!-- atria + ventricles, apex down and to the astronaut's left -->
          <path d="M95 139 C91 146 91 156 96 163 C102 169 114 170 124 167 C128 165 128 161 127 157
                   C125 150 121 142 115 138 C109 135 101 136 95 139 Z"/>
        </g>
        <!-- Lungs: narrow rounded apex under the collarbone, broad base curving
             over the diaphragm dome (~y 168), straight inner (medial) border.
             The astronaut's left lung (viewer's right) is narrower and has the
             cardiac notch where the heart shows through. -->
        <g class="region" data-region="lungs" tabindex="0" role="button" aria-label="Lungs">
          <!-- right lung (viewer's left): larger -->
          <path d="M84 96 C74 100 66 120 65 145 C64 158 65 166 68 170 Q81 158 94 166
                   C96 150 95 120 93 104 C91 98 88 95 84 96 Z"/>
          <!-- left lung (viewer's right): narrower, with the cardiac notch -->
          <path d="M116 96 C126 100 134 120 135 145 C136 158 135 166 132 170 Q126 162 121 168
                   C125 160 127 147 119 139 C112 133 107 124 107 104 C109 98 112 95 116 96 Z"/>
        </g>
        <g class="region" data-region="head" tabindex="0" role="button" aria-label="Head">
          <circle cx="100" cy="42" r="30"/>
        </g>
      </svg>
      <div id="regionInfo" class="region-info"></div>
    </section>

    <section class="card vitals-card" data-tab="health">
      <h2>Your vitals <span class="muted">vs. your own baseline</span></h2>
      <div id="tiles" class="tiles"><p class="muted">Waiting for data…</p></div>
      <div class="chart-wrap">
        <div class="chart-head"><strong id="chartTitle">Heart rate</strong> <span class="muted small">Last few minutes. Dashed line: your usual. Tap a reading to chart it.</span></div>
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
