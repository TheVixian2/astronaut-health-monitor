// Phase 2 placeholder: connect to /astronauts/{id}/stream over SSE and show
// what arrives. Field names follow docs/api-spec.md; behaviour follows the
// backend mock (alerts are re-sent with the same id once insight is ready).

(function () {
  const $ = id => document.getElementById(id);

  const FIELDS = [
    ["heart_rate_bpm", "Heart rate", "bpm"],
    ["systolic_mmhg", "Systolic BP", "mmHg"],
    ["diastolic_mmhg", "Diastolic BP", "mmHg"],
    ["spo2_pct", "SpO₂", "%"],
    ["temp_c", "Temperature", "°C"],
    ["resp_rate_bpm", "Resp. rate", "/min"],
    ["sleep_h_last_night", "Sleep last night", "h"],
    ["mood_1to5", "Mood", "/5"],
  ];

  const params = new URLSearchParams(location.search);
  let source = null;
  let mission = null;          // {environment, one_way_delay_s} or null if unknown
  let lastVitalsAt = null;     // Date from the latest vitals.timestamp
  const alerts = new Map();    // id -> alert (Map keeps first-seen order)

  // ---- controls ------------------------------------------------------------

  if (params.has("base")) $("base").value = params.get("base");
  if (params.has("aid")) $("aid").value = params.get("aid");
  if (params.has("view")) $("view").value = params.get("view");
  $("mock").checked = params.has("mock");

  $("controls").addEventListener("submit", e => { e.preventDefault(); connect(); });
  $("clearLog").addEventListener("click", () => { $("log").textContent = ""; });

  // ---- connection ----------------------------------------------------------

  async function connect() {
    if (source) source.close();
    alerts.clear();
    lastVitalsAt = null;
    renderAlerts();
    $("vitals").tBodies[0].innerHTML = '<tr><td colspan="4" class="muted">Waiting for a <code>vitals</code> event…</td></tr>';

    const base = $("base").value.replace(/\/+$/, "");
    const aid = $("aid").value;
    const view = $("view").value;
    const useMock = $("mock").checked;
    const url = `${base}/astronauts/${encodeURIComponent(aid)}/stream?view=${view}`;

    $("viewLabel").innerHTML = view === "ground"
      ? "View: <strong>Ground</strong> (delayed by light time)"
      : "View: <strong>Self-check</strong> (live)";
    setConn("connecting…", "pill-wait");
    log(`connect ${useMock ? "[mock] " : ""}${url}`);

    mission = useMock ? window.Mock.mission() : await fetchMission(base);
    renderMission();

    source = useMock ? new window.Mock.EventSource(url) : new EventSource(url);
    source.onopen = () => setConn(useMock ? "connected (mock)" : "connected", "pill-on");
    source.onerror = () => {
      // EventSource retries on its own; just reflect the state.
      setConn(source.readyState === 2 ? "disconnected" : "reconnecting…", source.readyState === 2 ? "pill-off" : "pill-wait");
      log("error / connection lost — browser will retry");
    };
    source.addEventListener("vitals", e => onVitals(JSON.parse(e.data)));
    source.addEventListener("alert", e => onAlert(JSON.parse(e.data)));
  }

  async function fetchMission(base) {
    try {
      const r = await fetch(`${base}/mission`);
      if (!r.ok) throw new Error(r.status);
      return await r.json();
    } catch (err) {
      log(`GET /mission failed (${err.message}) — verdicts unavailable`);
      return null;
    }
  }

  // ---- events --------------------------------------------------------------

  function onVitals(v) {
    log(`vitals ${JSON.stringify(v)}`);
    lastVitalsAt = new Date(v.timestamp);
    const rows = FIELDS.map(([key, label, unit]) => {
      const now = v[key], base = v.baseline ? v.baseline[key] : null;
      let delta = "", cls = "";
      if (typeof now === "number" && typeof base === "number" && base !== 0) {
        const pct = ((now - base) / base) * 100;
        delta = `${pct >= 0 ? "+" : ""}${pct.toFixed(1)}%`;
        cls = pct > 5 ? "up" : pct < -5 ? "down" : "";
      }
      return `<tr><td>${label}</td><td class="num">${fmt(now)} <span class="muted">${unit}</span></td>` +
             `<td class="num muted">${fmt(base)}</td><td class="num ${cls}">${delta}</td></tr>`;
    });
    $("vitals").tBodies[0].innerHTML = rows.join("");
    $("vitalsMeta").textContent = `Source: ${v.source} · measured ${v.timestamp}`;
    renderAge();
  }

  function onAlert(a) {
    const seen = alerts.has(a.id);
    log(`alert ${seen ? "(update) " : ""}${JSON.stringify(a)}`);
    alerts.set(a.id, a); // same id = same alert, now with insight filled in
    renderAlerts();
  }

  // ---- rendering -----------------------------------------------------------

  function renderAlerts() {
    const ul = $("alerts");
    if (!alerts.size) { ul.innerHTML = '<li class="muted">No alerts yet.</li>'; return; }
    ul.innerHTML = [...alerts.values()].reverse().map(a => {
      const ins = a.insight
        ? `<dl><dt>Why</dt><dd>${esc(a.insight.why)}</dd><dt>Trend</dt><dd>${esc(a.insight.trend)}</dd>` +
          `<dt>Suggested</dt><dd>${esc(a.insight.recommended_action)}</dd></dl>`
        : '<p class="muted small">Explanation pending…</p>';
      return `<li class="alert sev-${esc(a.severity)}">
        <div class="head"><span class="sev">${esc(a.severity)}</span>
          <strong>${esc(a.profile)}</strong>
          <span class="muted small">${esc(a.astronaut_id)} · ${esc(a.body_region)} · ${esc(a.hazard)} · ${esc(a.started_at)}</span></div>
        <div class="verdict">${esc(verdict(a))}</div>
        <div>${esc(a.onboard_action)}</div>${ins}</li>`;
    }).join("");
  }

  // CLAUDE.md: round trip > act_within_s -> "Act on board now", else "Ground will see this in X".
  function verdict(a) {
    if (!mission) return `Act within ${dur(a.act_within_s)}`;
    const roundTrip = 2 * mission.one_way_delay_s;
    return roundTrip > a.act_within_s
      ? `Act on board now — ${dur(a.act_within_s)} window`
      : `Ground will see this in ${dur(a.ground_eta_s ?? mission.one_way_delay_s)}`;
  }

  function renderMission() {
    $("mission").innerHTML = mission
      ? `Mission: <strong>${esc(mission.environment)}</strong> · one-way delay <strong>${dur(mission.one_way_delay_s)}</strong>`
      : "Mission: <strong>unknown</strong>";
  }

  function renderAge() {
    const el = $("age");
    if (!lastVitalsAt) { el.textContent = "—"; el.className = ""; return; }
    const s = Math.max(0, Math.round((Date.now() - lastVitalsAt) / 1000));
    el.textContent = `${dur(s)} old`;
    el.className = s > 10 ? "stale" : "";
  }
  setInterval(renderAge, 1000);

  function setConn(text, cls) { const el = $("conn"); el.textContent = text; el.className = `pill ${cls}`; }

  function log(line) {
    const el = $("log");
    el.textContent = `${new Date().toLocaleTimeString()}  ${line}\n` + el.textContent;
    if (el.textContent.length > 50000) el.textContent = el.textContent.slice(0, 40000);
  }

  // ---- helpers -------------------------------------------------------------

  function dur(s) {
    if (s == null) return "?";
    if (s < 60) return `${s} s`;
    if (s < 3600) return `${Math.round(s / 60)} min`;
    if (s < 86400) return `${Math.round(s / 3600)} h`;
    return `${Math.round(s / 86400)} d`;
  }
  const fmt = x => (x == null ? "—" : String(x));
  const esc = x => String(x ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  connect();
})();
