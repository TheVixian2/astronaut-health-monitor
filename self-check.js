// Self-check view: the astronaut's own tablet. Live (view=crew), never delayed.
// Vitals vs. personal baseline, a clickable body figure, a trend chart,
// the check-in form and this session's alerts.

(function () {
  const $ = id => document.getElementById(id);
  const A = window.AHM;
  const { FIELDS, REGION_NAMES, SEVERITY_RANK, verdict, deltaPct, dur, fmt, esc, profileName } = A;

  const cfg = A.settings();
  cfg.view = "crew";                 // Self-check is never the delayed view

  const MAX_POINTS = 120;            // ~6 min at one vitals event per 3 s
  const STALE_S = 10;

  let mission = null;
  let latest = null;                 // latest vitals snapshot
  let lastVitalsAt = null;
  let region = "whole_body";         // selected body region
  let chartField = "heart_rate_bpm";
  const history = [];                // [{t, v}] vitals snapshots for the chart
  const alerts = new Map();          // id -> alert, first-seen order
  const acknowledged = new Set();    // alert ids hidden from the banner

  // ---- setup ---------------------------------------------------------------

  $("aid").value = cfg.aid;
  $("aid").addEventListener("change", () => {
    location.href = A.linkWithSettings("self-check.html", { aid: $("aid").value });
  });

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
      const me = crew.find(c => c.id === cfg.aid);
      $("name").textContent = me ? me.name : cfg.aid;
      $("role").textContent = me ? `${me.role} · ${me.id}` : "";
    } catch { $("name").textContent = cfg.aid; }

    try { mission = await A.getJSON(cfg.base, "/mission", cfg.mock); } catch { mission = null; }
    renderMission();

    const { source } = A.openStream(cfg);
    source.onopen = () => setConn(cfg.mock ? "connected (mock)" : "connected", "pill-on");
    source.onerror = () => setConn(source.readyState === 2 ? "disconnected" : "reconnecting…",
                                   source.readyState === 2 ? "pill-off" : "pill-wait");
    source.addEventListener("vitals", e => onVitals(JSON.parse(e.data)));
    source.addEventListener("alert", e => onAlert(JSON.parse(e.data)));

    selectRegion(region);
    setInterval(renderAge, 1000);
  }

  // ---- events --------------------------------------------------------------

  function onVitals(v) {
    latest = v;
    lastVitalsAt = new Date(v.timestamp);
    history.push({ t: lastVitalsAt, v });
    if (history.length > MAX_POINTS) history.shift();
    renderTiles();
    pushChart();
    renderAge();
  }

  function onAlert(a) {
    alerts.set(a.id, a);  // same id = same alert, now with insight filled in
    renderBanner();
    renderHistory();
    renderBody();
    renderRegionInfo();
  }

  // ---- body figure ---------------------------------------------------------

  function selectRegion(r) {
    region = r;
    const first = FIELDS.find(f => f.region === r);
    if (first) chartField = first.key;
    renderBody();
    renderTiles();
    renderRegionInfo();
    rebuildChart();
  }

  // Highest severity among this session's alerts, per body region.
  function regionSeverity() {
    const out = {};
    for (const a of alerts.values()) {
      if (!out[a.body_region] || SEVERITY_RANK[a.severity] > SEVERITY_RANK[out[a.body_region]]) out[a.body_region] = a.severity;
    }
    return out;
  }

  function renderBody() {
    const sev = regionSeverity();
    document.querySelectorAll("#body .region").forEach(g => {
      const r = g.dataset.region;
      g.classList.toggle("selected", r === region);
      g.classList.remove("sev-watch", "sev-alert", "sev-critical");
      if (sev[r]) g.classList.add(`sev-${sev[r]}`);
      g.setAttribute("aria-pressed", String(r === region));
    });
  }

  function renderRegionInfo() {
    const list = [...alerts.values()].filter(a => region === "whole_body" || a.body_region === region);
    const hint = region === "head"
      ? '<p class="muted small">Eyes and sleep live here. Use the vision check in the check-in form.</p>' : "";
    $("regionInfo").innerHTML = `<h3>${esc(REGION_NAMES[region])}</h3>${hint}` + (list.length
      ? `<ul class="mini">${list.slice().reverse().map(a =>
          `<li class="sev-${esc(a.severity)}"><span class="dot"></span>${esc(profileName(a.profile))}
           <span class="muted small">${esc(time(a.started_at))}</span></li>`).join("")}</ul>`
      : '<p class="muted small">Nothing flagged here this session.</p>');
  }

  // ---- vitals tiles + chart ------------------------------------------------

  function renderTiles() {
    if (!latest) return;
    $("tiles").innerHTML = FIELDS.map(f => {
      const now = latest[f.key], base = latest.baseline ? latest.baseline[f.key] : null;
      const pct = deltaPct(now, base);
      const off = pct != null && Math.abs(pct) >= 10;
      const inRegion = region === "whole_body" || f.region === region;
      const cls = ["tile", inRegion ? "" : "dim", off ? "off" : "", f.key === chartField ? "charted" : ""].join(" ");
      const delta = pct == null ? "" : `${pct >= 0 ? "+" : ""}${pct.toFixed(0)}%`;
      return `<button type="button" class="${cls}" data-key="${f.key}" aria-pressed="${f.key === chartField}">
        <span class="t-label">${f.label}</span>
        <span class="t-value">${fmt(now)}<span class="t-unit"> ${f.unit}</span></span>
        <span class="t-base muted">yours: ${fmt(base)} <span class="t-delta">${delta}</span></span></button>`;
    }).join("");
  }

  let chart = null;

  function rebuildChart() {
    const field = FIELDS.find(f => f.key === chartField);
    $("chartTitle").textContent = `${field.label} (${field.unit})`;
    if (!window.Chart) { $("chartFallback").hidden = false; $("chart").hidden = true; return; }
    if (chart) chart.destroy();
    const css = getComputedStyle(document.documentElement);
    chart = new window.Chart($("chart"), {
      type: "line",
      data: {
        labels: history.map(p => time(p.t)),
        datasets: [
          { label: field.label, data: history.map(p => p.v[chartField]), borderColor: css.getPropertyValue("--accent").trim(),
            pointRadius: 0, borderWidth: 2, tension: 0.3 },
          { label: "Your baseline", data: history.map(p => p.v.baseline?.[chartField]), borderColor: css.getPropertyValue("--muted").trim(),
            borderDash: [5, 5], pointRadius: 0, borderWidth: 1.5 },
        ],
      },
      options: {
        animation: false, responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { ticks: { color: "#8b95ab", maxTicksLimit: 6 }, grid: { color: "#263049" } },
          y: { ticks: { color: "#8b95ab" }, grid: { color: "#263049" }, grace: "10%" },
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

  // ---- alerts --------------------------------------------------------------

  function renderBanner() {
    const open = [...alerts.values()].filter(a => !acknowledged.has(a.id));
    const el = $("banner");
    if (!open.length) { el.hidden = true; return; }
    const a = open[open.length - 1];
    const v = verdict(a, mission);
    el.className = `banner sev-${a.severity}`;
    el.innerHTML = `
      <div class="b-main">
        <div class="b-top"><span class="sev">${esc(a.severity)}</span>
          <strong class="b-name">${esc(profileName(a.profile))}</strong>
          <span class="muted small">${esc(REGION_NAMES[a.body_region] || a.body_region)} · ${esc(time(a.started_at))}</span></div>
        <div class="b-verdict ${v.onboard ? "onboard" : ""}">${esc(v.text)}</div>
        <div class="b-action">${esc(a.onboard_action)}</div>
        ${insightBlock(a)}
      </div>
      <button type="button" class="ack" data-id="${esc(a.id)}">Got it</button>`;
    el.querySelector(".ack").addEventListener("click", () => { acknowledged.add(a.id); renderBanner(); });
    el.hidden = false;
  }

  function insightBlock(a) {
    if (!a.insight) return '<p class="muted small">Working out an explanation…</p>';
    return `<details><summary>Why was this flagged?</summary><dl>
      <dt>Why</dt><dd>${esc(a.insight.why)}</dd>
      <dt>Trend</dt><dd>${esc(a.insight.trend)}</dd>
      <dt>Suggested</dt><dd>${esc(a.insight.recommended_action)}</dd></dl></details>`;
  }

  function renderHistory() {
    const ul = $("history");
    if (!alerts.size) { ul.innerHTML = '<li class="muted">No alerts this session.</li>'; return; }
    ul.innerHTML = [...alerts.values()].reverse().map(a => `
      <li class="alert sev-${esc(a.severity)}">
        <div class="head"><span class="sev">${esc(a.severity)}</span>
          <strong>${esc(profileName(a.profile))}</strong>
          <span class="muted small">${esc(time(a.started_at))}</span></div>
        <div class="verdict">${esc(verdict(a, mission).text)}</div>
        <div>${esc(a.onboard_action)}</div>
        ${insightBlock(a)}
      </li>`).join("");
  }

  // ---- check-in ------------------------------------------------------------

  async function onCheckin(e) {
    e.preventDefault();
    const f = e.target;
    const body = { timestamp: new Date().toISOString().replace(/\.\d+Z$/, "Z"), share_with_ground: f.share.checked };
    const mood = f.querySelector('input[name="mood"]:checked');
    if (mood) body.mood_1to5 = Number(mood.value);
    if (f.sleep.value !== "") body.sleep_h = Number(f.sleep.value);
    const symptoms = [...f.querySelectorAll('input[name="symptom"]:checked')].map(i => i.value);
    if (symptoms.length) body.symptoms = symptoms;
    if (f.amsler.checked || f.acuity.value !== "") {
      body.vision = { amsler_distortion: f.amsler.checked };
      if (f.acuity.value !== "") body.vision.acuity_line = Number(f.acuity.value);
    }

    const out = $("checkinResult");
    out.className = "small muted";
    out.textContent = "Sending…";
    try {
      await A.postJSON(cfg.base, `/astronauts/${encodeURIComponent(cfg.aid)}/checkin`, body, cfg.mock);
      out.className = "small ok";
      out.textContent = body.share_with_ground
        ? `Saved. Shared with ground — they'll receive it in about ${mission ? dur(mission.one_way_delay_s) : "?"}.`
        : "Saved on board. Not shared with ground.";
      f.reset();
    } catch (err) {
      out.className = "small err";
      out.textContent = `Could not save: ${err.message}`;
    }
  }

  // ---- status --------------------------------------------------------------

  function renderMission() {
    $("mission").innerHTML = mission
      ? `${esc(A.ENV_NAMES[mission.environment] || mission.environment)} · ground is <strong>${dur(mission.one_way_delay_s)}</strong> away`
      : "Mission: unknown";
  }

  function renderAge() {
    const el = $("age");
    if (!lastVitalsAt) { el.textContent = "—"; el.className = ""; return; }
    const s = Math.max(0, Math.round((Date.now() - lastVitalsAt) / 1000));
    el.textContent = `${dur(s)} old`;
    el.className = s > STALE_S ? "stale" : "";
  }

  function setConn(text, cls) { const el = $("conn"); el.textContent = text; el.className = `pill ${cls}`; }

  function time(t) {
    const d = t instanceof Date ? t : new Date(t);
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  }
})();
