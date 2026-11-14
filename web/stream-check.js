// Debug page: connect to /astronauts/{id}/stream over SSE and show exactly
// what arrives. Alerts are upserted by id (the backend re-sends an alert with
// the same id once its insight is ready).

(function () {
  const $ = id => document.getElementById(id);
  const { FIELDS, verdict, deltaPct, dur, fmt, esc, profileName } = window.AHM;

  const initial = window.AHM.settings();
  let source = null;
  let mission = null;          // {environment, one_way_delay_s} or null if unknown
  let lastVitalsAt = null;     // Date from the latest vitals.timestamp
  const alerts = new Map();    // id -> alert (Map keeps first-seen order)

  $("base").value = initial.base;
  $("aid").value = initial.aid;
  $("view").value = initial.view;
  $("mock").checked = initial.mock;

  $("controls").addEventListener("submit", e => { e.preventDefault(); connect(); });
  $("clearLog").addEventListener("click", () => { $("log").textContent = ""; });

  async function connect() {
    if (source) source.close();
    alerts.clear();
    lastVitalsAt = null;
    renderAlerts();
    $("vitals").tBodies[0].innerHTML = '<tr><td colspan="4" class="muted">Waiting for a <code>vitals</code> event…</td></tr>';

    const opts = { base: $("base").value.replace(/\/+$/, ""), aid: $("aid").value, view: $("view").value, mock: $("mock").checked };
    $("viewLabel").innerHTML = opts.view === "ground"
      ? "View: <strong>Ground</strong> (delayed by light time)"
      : "View: <strong>Self-check</strong> (live)";
    setConn("connecting…", "pill-wait");

    try {
      mission = await window.AHM.getJSON(opts.base, "/mission", opts.mock);
    } catch (err) {
      mission = null;
      log(`GET /mission failed (${err.message}) — verdicts unavailable`);
    }
    renderMission();

    const s = window.AHM.openStream(opts);
    source = s.source;
    log(`connect ${opts.mock ? "[mock] " : ""}${s.url}`);
    source.onopen = () => setConn(opts.mock ? "connected (mock)" : "connected", "pill-on");
    source.onerror = () => {
      const closed = source.readyState === 2;
      setConn(closed ? "disconnected" : "reconnecting…", closed ? "pill-off" : "pill-wait");
      log("error / connection lost — browser will retry");
    };
    source.addEventListener("vitals", e => onVitals(JSON.parse(e.data)));
    source.addEventListener("alert", e => onAlert(JSON.parse(e.data)));
  }

  function onVitals(v) {
    log(`vitals ${JSON.stringify(v)}`);
    lastVitalsAt = new Date(v.timestamp);
    $("vitals").tBodies[0].innerHTML = FIELDS.map(({ key, label, unit }) => {
      const now = v[key], base = v.baseline ? v.baseline[key] : null;
      const pct = deltaPct(now, base);
      const delta = pct == null ? "" : `${pct >= 0 ? "+" : ""}${pct.toFixed(1)}%`;
      const cls = pct == null ? "" : pct > 5 ? "up" : pct < -5 ? "down" : "";
      return `<tr><td>${label}</td><td class="num">${fmt(now)} <span class="muted">${unit}</span></td>` +
             `<td class="num muted">${fmt(base)}</td><td class="num ${cls}">${delta}</td></tr>`;
    }).join("");
    $("vitalsMeta").textContent = `Source: ${v.source} · measured ${v.timestamp}`;
    renderAge();
  }

  function onAlert(a) {
    log(`alert ${alerts.has(a.id) ? "(update) " : ""}${JSON.stringify(a)}`);
    alerts.set(a.id, a);
    renderAlerts();
  }

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
          <strong>${esc(profileName(a.profile))}</strong>
          <span class="muted small">${esc(a.astronaut_id)} · ${esc(a.body_region)} · ${esc(a.hazard)} · ${esc(a.started_at)}</span></div>
        <div class="verdict">${esc(verdict(a, mission).text)}</div>
        <div>${esc(a.onboard_action)}</div>${window.AHM.nasaRefs(a)}${ins}</li>`;
    }).join("");
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

  connect();
})();
