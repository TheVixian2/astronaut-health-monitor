// In-page stand-in for the backend's SSE stream, for working without a backend.
// Mirrors backend/main.py (mock) on the `backend` branch:
//   - `vitals` every 3 s: mean-reverting random walk around a per-astronaut baseline
//   - `alert` every ~60 s on a1 (MOCK_ALERT_EVERY_S below), sent with insight: null,
//     then re-sent ~2 s later with the SAME id and insight filled in
//   - view=ground holds every event back by the mission's one_way_delay_s
// Exposes the same surface app.js uses on EventSource: addEventListener,
// onopen, onerror, readyState, close().

(function () {
  const TICK_S = 3;
  const MOCK_ALERT_EVERY_S = 30; // a bit faster than the backend's 60 s, for dev
  const INSIGHT_DELAY_S = 2;

  const MISSION = { environment: "mars", one_way_delay_s: 20, real_one_way_delay_s: 1320 };

  const CREW = [
    { id: "a1", name: "Cmdr. Elena Ionescu", role: "Commander", status: "nominal" },
    { id: "a2", name: "Mihai Popa", role: "Flight Engineer", status: "nominal" },
    { id: "a3", name: "Dr. Sara Okafor", role: "Crew Medical Officer", status: "nominal" },
    { id: "a4", name: "Jonas Berg", role: "Mission Specialist", status: "nominal" },
  ];

  // While an alert is active, vitals drift towards baseline x factor so the
  // numbers and the chart agree with the alert.
  const SHIFTS = { orthostatic: { heart_rate_bpm: 1.32, systolic_mmhg: 0.8 } };
  const SHIFT_S = 45;

  // Every alert any mock stream on this page has raised, recorded at the moment
  // it is raised (before any ground delay). Backs GET /astronauts/{id}/alerts.
  const ALERT_LOG = [];

  const BASELINES = {
    a1: { heart_rate_bpm: 58, systolic_mmhg: 112, diastolic_mmhg: 72, spo2_pct: 98, temp_c: 36.5, resp_rate_bpm: 12, sleep_h_last_night: 7.2, mood_1to5: 4 },
    a2: { heart_rate_bpm: 74, systolic_mmhg: 124, diastolic_mmhg: 80, spo2_pct: 97, temp_c: 36.8, resp_rate_bpm: 15, sleep_h_last_night: 6.8, mood_1to5: 4 },
    a3: { heart_rate_bpm: 66, systolic_mmhg: 118, diastolic_mmhg: 76, spo2_pct: 98, temp_c: 36.6, resp_rate_bpm: 13, sleep_h_last_night: 7.5, mood_1to5: 5 },
    a4: { heart_rate_bpm: 62, systolic_mmhg: 116, diastolic_mmhg: 74, spo2_pct: 98, temp_c: 36.4, resp_rate_bpm: 14, sleep_h_last_night: 7.0, mood_1to5: 4 },
  };

  const STEP = { heart_rate_bpm: 1.0, systolic_mmhg: 1.0, diastolic_mmhg: 0.7, spo2_pct: 0.2, temp_c: 0.02, resp_rate_bpm: 0.3 };

  const PROFILES = [
    { profile: "orthostatic", severity: "alert", hazard: "gravity", body_region: "heart", act_within_s: 600,
      onboard_action: "Lie flat, legs raised. Drink 500 ml with salt tablets, re-measure in 10 min.",
      insight: { why: "Heart rate is well above your own baseline while systolic pressure is below it.",
                 trend: "Heart rate up ~30% and systolic down ~18% versus your baseline.",
                 recommended_action: "Lie down with legs raised, take fluids with salt, re-check in 10 minutes." } },
    { profile: "sans", severity: "watch", hazard: "gravity", body_region: "head", act_within_s: 86400,
      onboard_action: "Do an Amsler grid and acuity check today; log any headache.",
      insight: { why: "Your SANS risk score is rising. This is a risk score, not a diagnosis.",
                 trend: "Risk score up over the last mission days.",
                 recommended_action: "Repeat the vision check and consider asking for an OCT scan." } },
  ];

  function gauss() {
    // Box-Muller
    const u = 1 - Math.random(), v = Math.random();
    return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
  }

  const nowIso = () => new Date().toISOString().replace(/\.\d+Z$/, "Z");

  class MockEventSource {
    constructor(url) {
      const u = new URL(url, location.href);
      const m = u.pathname.match(/\/astronauts\/([^/]+)\/stream/);
      this.aid = m ? m[1] : "a1";
      this.view = u.searchParams.get("view") || "crew";
      this.url = url;
      this.readyState = 0;
      this.listeners = {};
      this.timers = [];
      this.baseline = BASELINES[this.aid] || BASELINES.a1;
      this.values = { ...this.baseline };
      this.alertIndex = 0;
      this.shift = {};

      this.later(() => {
        this.readyState = 1;
        if (this.onopen) this.onopen(new Event("open"));
        if (this.view === "crew") this.emit("vitals", this.snapshot());
      }, 0.2, false);

      this.every(() => { this.walk(); this.emit("vitals", this.snapshot()); }, TICK_S);
      if (this.aid === "a1") this.every(() => this.fireAlert(), MOCK_ALERT_EVERY_S);
    }

    addEventListener(type, fn) { (this.listeners[type] ||= []).push(fn); }
    removeEventListener(type, fn) { this.listeners[type] = (this.listeners[type] || []).filter(f => f !== fn); }

    close() {
      this.readyState = 2;
      this.timers.forEach(t => { clearTimeout(t); clearInterval(t); });
      this.timers = [];
    }

    later(fn, seconds, delayed = true) {
      const extra = delayed && this.view === "ground" ? MISSION.one_way_delay_s : 0;
      this.timers.push(setTimeout(fn, (seconds + extra) * 1000));
    }

    every(fn, seconds) { this.timers.push(setInterval(fn, seconds * 1000)); }

    // Build the payload now, deliver it after the light-time delay on ground view.
    emit(type, payload) {
      const data = JSON.stringify(payload);
      const deliver = () => {
        if (this.readyState !== 1) return;
        (this.listeners[type] || []).forEach(fn => fn(new MessageEvent(type, { data })));
      };
      if (this.view === "ground") this.later(deliver, 0);
      else deliver();
    }

    walk() {
      for (const [k, step] of Object.entries(STEP)) {
        const v = this.values[k];
        const target = this.baseline[k] * (this.shift[k] || 1);
        this.values[k] = v + gauss() * step + (target - v) * 0.2;
      }
      this.values.spo2_pct = Math.min(this.values.spo2_pct, 100);
    }

    snapshot() {
      const v = this.values;
      return {
        timestamp: nowIso(), source: "simulated", baseline: this.baseline,
        heart_rate_bpm: Math.round(v.heart_rate_bpm), systolic_mmhg: Math.round(v.systolic_mmhg),
        diastolic_mmhg: Math.round(v.diastolic_mmhg), spo2_pct: Math.round(v.spo2_pct),
        temp_c: Math.round(v.temp_c * 10) / 10, resp_rate_bpm: Math.round(v.resp_rate_bpm),
        sleep_h_last_night: v.sleep_h_last_night, mood_1to5: v.mood_1to5,
      };
    }

    fireAlert() {
      const p = PROFILES[this.alertIndex++ % PROFILES.length];
      this.shift = SHIFTS[p.profile] || {};
      this.timers.push(setTimeout(() => { this.shift = {}; }, SHIFT_S * 1000));
      const alert = {
        id: "al-" + Math.random().toString(16).slice(2, 10), astronaut_id: this.aid,
        profile: p.profile, severity: p.severity, hazard: p.hazard, body_region: p.body_region,
        started_at: nowIso(), onboard_action: p.onboard_action, act_within_s: p.act_within_s,
        ground_eta_s: MISSION.one_way_delay_s, insight: null,
      };
      ALERT_LOG.push(alert);
      this.emit("alert", alert);
      this.timers.push(setTimeout(() => {
        alert.insight = p.insight;
        this.emit("alert", { ...alert });
      }, INSIGHT_DELAY_S * 1000));
    }
  }

  // REST stand-ins, same shapes as the spec. Async, like fetch.
  const ALERTS_PATH = /^\/astronauts\/[^/]+\/alerts$/;
  const CHECKIN_PATH = /^\/astronauts\/[^/]+\/checkin$/;

  function get(path) {
    const p = path.split("?")[0];
    if (p === "/mission") return Promise.resolve({ ...MISSION });
    if (p === "/crew") return Promise.resolve(CREW.map(c => ({ ...c })));
    if (ALERTS_PATH.test(p)) {
      // Like the backend: undelayed, newest first.
      const aid = p.split("/")[2];
      return Promise.resolve(ALERT_LOG.filter(a => a.astronaut_id === aid).reverse().map(a => ({ ...a })));
    }
    return Promise.reject(new Error(`mock: no GET ${p}`));
  }

  function post(path, body) {
    console.info("[mock] POST", path, body);
    if (CHECKIN_PATH.test(path)) return Promise.resolve({ accepted: true });
    return Promise.reject(new Error(`mock: no POST ${path}`));
  }

  window.Mock = { EventSource: MockEventSource, get, post };
})();
