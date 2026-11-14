// Health history: hour-by-hour average, high and low for each vital, plus
// sleep, alerts and the Mission Control report. Data: GET /astronauts/{id}/history
// (avg + low + high per bucket), /vitals (baseline), /circadian, /alerts, /report.
(function () {
  const A = window.AHM;
  const cfg = A.settings();
  const who = window.AHMAuth && window.AHMAuth.session();
  const role = who ? who.role : "demo";
  const $ = id => document.getElementById(id);
  // Chart colours come from style.css tokens, so the charts follow the light theme.
  const tok = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  const alpha = (hex, a) => { let h = hex.replace("#", ""); if (h.length === 3) h = [...h].map(c => c + c).join(""); const n = parseInt(h, 16); return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`; };

  const FIELDS = [
    { key: "heart_rate_bpm", label: "Heart rate", unit: "bpm", dp: 0 },
    { key: "spo2_pct", label: "SpO₂", unit: "%", dp: 0 },
    { key: "temp_c", label: "Temperature", unit: "°C", dp: 1 },
    { key: "resp_rate_bpm", label: "Breathing", unit: "/min", dp: 0 },
  ];
  const RANGES = {
    day:   { label: "24 h",    hours: 24,  bucket: 3600,  note: "Last 24 hours, hour by hour" },
    week:  { label: "7 days",  hours: 168, bucket: 21600, note: "Last 7 days, every 6 hours" },
    month: { label: "30 days", hours: 720, bucket: 86400, note: "Last 30 days, day by day" },
  };
  // Crew members see only themselves; warnings and reports are for the
  // Commander, the Crew Medical Officer and Mission Control (commander first).
  const crewOnly = role === "crew";
  const state = { aid: cfg.aid, range: "day", field: FIELDS[0], rows: [], baseline: null, crew: [] };
  let chart, sleepChart;

  const back = { crew: "self-check.html", captain: "captain.html", doctor: "doctor.html", ground: "ground.html" }[role] || "index.html";
  $("back").href = A.linkWithSettings(back);

  function timeLabel(iso) {
    const d = new Date(iso);
    if (state.range === "month") return d.toLocaleDateString([], { day: "numeric", month: "short" });
    const hm = d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    return state.range === "week" ? `${d.toLocaleDateString([], { weekday: "short" })} ${hm}` : hm;
  }
  const num = (v, dp) => (v == null ? "—" : v.toFixed(dp));

  function buttons(el, items, isOn, onPick) {
    el.innerHTML = items.map(([id, label]) =>
      `<button type="button" data-id="${A.esc(id)}" aria-pressed="${isOn(id)}">${A.esc(label)}</button>`).join("");
    el.onclick = e => { const b = e.target.closest("button"); if (b) onPick(b.dataset.id); };
  }

  function renderControls() {
    buttons($("ranges"), Object.entries(RANGES).map(([k, r]) => [k, r.label]), k => k === state.range,
      k => { state.range = k; loadHistory(); });
    buttons($("fields"), FIELDS.map(f => [f.key, f.label]), k => k === state.field.key,
      k => { state.field = FIELDS.find(f => f.key === k); renderControls(); draw(); });
    $("rangeLabel").textContent = RANGES[state.range].note;
  }

  function draw() {
    const f = state.field, rows = state.rows;
    const labels = rows.map(r => timeLabel(r.ts));
    const avg = rows.map(r => r[f.key]);
    const lo = rows.map(r => (r.low || {})[f.key] ?? null);
    const hi = rows.map(r => (r.high || {})[f.key] ?? null);
    const base = state.baseline ? state.baseline[f.key] : null;
    const data = {
      labels,
      datasets: [
        { label: "High", data: hi, borderWidth: 0, pointRadius: 0, backgroundColor: alpha(tok("--accent"), 0.18), fill: "+1" },
        { label: "Low", data: lo, borderWidth: 0, pointRadius: 0, fill: false },
        { label: "Average", data: avg, borderColor: tok("--accent"), borderWidth: 2, pointRadius: rows.length > 60 ? 0 : 2, tension: 0.3, fill: false },
        { label: "Your normal", data: rows.map(() => base), borderColor: tok("--muted"), borderDash: [5, 5], borderWidth: 1, pointRadius: 0, fill: false },
      ],
    };
    const options = {
      responsive: true, maintainAspectRatio: false, animation: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { labels: { filter: i => i.text !== "Low", color: tok("--text") } },
        tooltip: { callbacks: { label: c => `${c.dataset.label}: ${num(c.parsed.y, f.dp)} ${f.unit}` } },
      },
      scales: { x: { ticks: { color: tok("--muted"), maxTicksLimit: 12 } }, y: { ticks: { color: tok("--muted") } } },
    };
    if (window.Chart) {
      if (chart) chart.destroy();
      chart = new Chart($("chart"), { type: "line", data, options });
    }

    const head = `<tr><th>${state.range === "month" ? "Day" : "Hour"}</th><th>Average</th><th>High</th><th>Low</th><th>vs your normal</th></tr>`;
    const body = rows.slice().reverse().map(r => {
      const d = A.deltaPct(r[f.key], base);
      const cls = d == null || Math.abs(d) < 5 ? "" : d > 0 ? "dev-up" : "dev-down";
      return `<tr><td>${A.esc(timeLabel(r.ts))}</td><td>${num(r[f.key], f.dp)}</td>` +
        `<td>${num((r.high || {})[f.key], f.dp)}</td><td>${num((r.low || {})[f.key], f.dp)}</td>` +
        `<td class="${cls}">${d == null ? "—" : (d > 0 ? "+" : "") + d.toFixed(0) + "%"}</td></tr>`;
    }).join("");
    $("table").innerHTML = `<thead>${head.replace(/<th>/g, '<th scope="col">')}</thead><tbody>${body ||
      '<tr><td colspan="5" class="muted">No stored readings for this period yet.</td></tr>'}</tbody>`;
  }

  async function loadHistory() {
    renderControls();
    const r = RANGES[state.range];
    try {
      state.rows = await A.getJSON(cfg.base,
        `/astronauts/${encodeURIComponent(state.aid)}/history?hours=${r.hours}&bucket_s=${r.bucket}`, cfg.mock);
    } catch { state.rows = []; }
    draw();
  }

  async function loadSleep() {
    const view = role === "ground" ? "ground" : "crew";
    try {
      const c = await A.getJSON(cfg.base, `/astronauts/${encodeURIComponent(state.aid)}/circadian?view=${view}`, cfg.mock);
      const usual = state.baseline ? state.baseline.sleep_h_last_night : null;
      const nights = c.nights || [];
      $("sleepNote").textContent = usual ? `Dashed line: usual ${usual.toFixed(1)} h.` : "";
      if (window.Chart) {
        if (sleepChart) sleepChart.destroy();
        sleepChart = new Chart($("sleepChart"), {
          data: {
            labels: nights.map(n => new Date(n.night_of + "T12:00:00Z").toLocaleDateString([], { weekday: "short", day: "numeric" })),
            datasets: [
              { type: "bar", label: "Sleep (h)", data: nights.map(n => n.sleep_h), backgroundColor: tok("--ic-sleep") },
              { type: "line", label: "Usual", data: nights.map(() => usual), borderColor: tok("--muted"), borderDash: [5, 5], pointRadius: 0 },
            ],
          },
          options: { responsive: true, maintainAspectRatio: false, animation: false,
            plugins: { legend: { display: false } },
            scales: { x: { ticks: { color: tok("--muted") } }, y: { beginAtZero: true, ticks: { color: tok("--muted") } } } },
        });
      }
    } catch (e) {
      $("sleepNote").textContent = e && e.status === 403 ? "Kept private by the astronaut." : "Sleep log unavailable.";
    }
  }

  async function loadAlertsAndReport() {
    if (crewOnly) return;
    $("alertsCard").hidden = false;
    $("reportCard").hidden = false;
    try {
      const alerts = await A.getJSON(cfg.base, `/astronauts/${encodeURIComponent(state.aid)}/alerts`, cfg.mock);
      $("alerts").innerHTML = alerts.length ? alerts.slice().reverse().map(a =>
        `<div class="sev-${A.esc(a.severity)}"><strong>${A.esc(A.profileName(a.profile))}</strong> · ` +
        `${A.esc(new Date(a.started_at).toLocaleString([], { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }))}` +
        ` <span class="muted">${A.esc(a.onboard_action || "")}</span></div>`).join("")
        : '<p class="muted">No alerts in the stored history.</p>';
    } catch { $("alerts").textContent = "Alerts unavailable."; }
    try {
      const view = role === "ground" ? "ground" : "crew";
      const rep = await A.getJSON(cfg.base, `/astronauts/${encodeURIComponent(state.aid)}/report?days=7&view=${view}`, cfg.mock);
      $("report").textContent = `${rep.text}\n\n${rep.delivery}`;
    } catch { $("report").textContent = "Report unavailable."; }
  }

  async function loadAll() {
    const c = state.crew.find(m => m.id === state.aid);
    $("name").textContent = c ? c.name : state.aid;
    $("role").textContent = c ? c.role : "";
    try {
      const v = await A.getJSON(cfg.base, `/astronauts/${encodeURIComponent(state.aid)}/vitals`, cfg.mock);
      state.baseline = v.baseline;
    } catch { state.baseline = null; }
    await Promise.all([loadHistory(), loadSleep(), loadAlertsAndReport()]);
  }

  (async function init() {
    try { state.crew = await A.getJSON(cfg.base, "/crew", cfg.mock); } catch { state.crew = []; }
    if (crewOnly) {
      $("pickWrap").hidden = true;
    } else {
      $("pick").innerHTML = state.crew.map(m =>
        `<option value="${A.esc(m.id)}"${m.id === state.aid ? " selected" : ""}>${A.esc(m.name)}</option>`).join("");
      $("pick").onchange = e => { state.aid = e.target.value; loadAll(); };
    }
    loadAll();
  })();
})();
