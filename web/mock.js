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

  // Latest check-in values per astronaut. Like the backend, a check-in's
  // sleep_h / mood_1to5 replace the simulated sleep / mood in later vitals.
  const MANUAL = {};

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
        sleep_h_last_night: MANUAL[this.aid]?.sleep_h_last_night ?? v.sleep_h_last_night,
        mood_1to5: MANUAL[this.aid]?.mood_1to5 ?? v.mood_1to5,
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

  // ---- circadian (mirrors backend/circadian.py; PROVISIONAL in the spec) ----
  // Usual bedtime (UTC h), bedtime jitter (min), usual sleep (h), chance the
  // pre-sleep mode is used. a2 is the irregular one, as in the backend.
  const HABITS = { a1: [22.0, 15, 7.2, 0.9], a2: [23.0, 40, 6.6, 0.4], a3: [22.5, 12, 7.5, 0.85], a4: [22.5, 18, 7.0, 0.95] };
  const CCT_K = { general: 4500, pre_sleep: 2700, phase_shift: 6500, off: 0 };
  const SSLA = { source: "NASA ISS Solid-State Lighting Assembly: pre-sleep mode (2700K, blue-depleted)", url: "https://ntrs.nasa.gov/citations/20160005080" };
  const IMMUNE = { source: "Light at night disrupts biological clocks, calendars, and immune function (2021)", url: "https://pmc.ncbi.nlm.nih.gov/articles/PMC8564795" };
  const lightingOverride = {};

  function seeded(str) { // mulberry32 seeded from a string hash: same history every load
    let h = 1779033703;
    for (const ch of str) h = Math.imul(h ^ ch.charCodeAt(0), 3432918353);
    let a = h >>> 0;
    return () => { a = (a + 0x6D2B79F5) | 0; let t = Math.imul(a ^ (a >>> 15), 1 | a); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
  }
  const gaussR = rnd => Math.sqrt(-2 * Math.log(1 - rnd())) * Math.cos(2 * Math.PI * rnd());

  // Fixed patterns, not random draws, so the mock always tells the backend's
  // story: a2 irregular (bedtime spread ~2 h, bright light on 3 of 7 nights),
  // everyone else nominal. LATE x jitter = minutes late; a night uses the
  // pre-sleep mode when USE[i] < the astronaut's chance of using it.
  const LATE = [-0.4, 1.6, -0.9, 0.2, 1.1, -1.3, 0.5];
  const USE = [0, 0.37, 0.74, 0.11, 0.48, 0.85, 0.22];

  function nightsFor(aid) {
    const [bedH, jitter, sleepH, pPre] = HABITS[aid];
    const rnd = seeded("circadian-" + aid);   // only for small sleep-length noise
    const today = new Date(); today.setUTCHours(0, 0, 0, 0);
    const out = [];
    for (let back = 7; back >= 1; back--) {
      const i = 7 - back;
      const day = new Date(today - back * 864e5);
      const late = LATE[i] * jitter;
      const bed = new Date(day.getTime() + bedH * 36e5 + late * 6e4);
      bed.setUTCSeconds(0, 0);
      const hours = Math.round(Math.min(9, Math.max(4, sleepH + gaussR(rnd) * 0.35 - Math.max(0, late) / 60 * 0.5)) * 10) / 10;
      const pre = USE[i] < pPre ? 55 + (i % 3) * 5 : 5 + i;
      out.push({
        night_of: day.toISOString().slice(0, 10), bedtime: iso(bed), wake_time: iso(new Date(bed.getTime() + hours * 36e5)),
        sleep_h: hours, pre_sleep_lighting_min: pre, bright_light_last_hour: pre < 30,
      });
    }
    return out;
  }
  const iso = d => d.toISOString().replace(/\.\d+Z$/, "Z");

  // Sharing choice survives reloads and is seen by both panes of demo.html.
  function sharedMap() { try { return JSON.parse(localStorage.getItem("ahm-mock-circadian-share") || "{}"); } catch { return {}; } }
  // Shared with ground by default (team decision 2026-11-14); false only after the astronaut opts out.
  function isShared(aid) { return sharedMap()[aid] !== false; }
  function setShared(aid, v) { const m = sharedMap(); m[aid] = v; try { localStorage.setItem("ahm-mock-circadian-share", JSON.stringify(m)); } catch {} }

  function circadian(aid) {
    const nights = nightsFor(aid);
    const mins = nights.map(n => { const d = new Date(n.bedtime); return ((d.getUTCHours() - 18 + 24) % 24) * 60 + d.getUTCMinutes(); });
    const spread = Math.max(...mins) - Math.min(...mins);
    const bright = nights.filter(n => n.bright_light_last_hour).length;
    const irregular = spread > 60, tooBright = bright >= 3;
    let card = null;
    if (irregular || tooBright) {
      const parts = [];
      if (irregular) parts.push(`Your bedtime varied by about ${(spread / 60).toFixed(1)} h over the last ${nights.length} nights.`);
      if (tooBright) parts.push(`On ${bright} of ${nights.length} nights your quarters were still in bright light shortly before sleep.`);
      parts.push("Irregular sleep timing and blue-rich light before bed may shift your body clock, and body-clock disruption has been linked to changes in immune function.");
      card = parts.join(" ");
    }
    let text = "You might consider switching your quarters to pre-sleep lighting about 1 h before bed and setting screens aside.";
    if (irregular) text += " A similar bedtime each night, within about 30 min, may also help.";
    const lighting = lightingOverride[aid] || { mode: "general", cct_k: 4500, since: nights[nights.length - 1].wake_time };
    return {
      astronaut_id: aid, share_with_ground: isShared(aid), lighting, nights,
      summary: { status: card ? "watch" : "nominal", nights: nights.length, bedtime_spread_min: spread, nights_bright_before_sleep: bright },
      card, recommendation: { text, source: SSLA.source, source_url: SSLA.url },
      evidence: { text: "Circadian disruption is associated with immune changes; most evidence is from animal studies.", source: IMMUNE.source, source_url: IMMUNE.url },
    };
  }

  const reject = (path, status) => { const e = new Error(`${path} → HTTP ${status} (mock)`); e.status = status; return Promise.reject(e); };
  const CIRCADIAN_PATH = /^\/astronauts\/([^/]+)\/circadian$/;

  // REST stand-ins, same shapes as the spec. Async, like fetch.
  const ALERTS_PATH = /^\/astronauts\/[^/]+\/alerts$/;
  const CHECKIN_PATH = /^\/astronauts\/[^/]+\/checkin$/;

  function get(path) {
    const p = path.split("?")[0];
    const circ = p.match(CIRCADIAN_PATH);
    if (circ) {
      const aid = circ[1];
      if (!HABITS[aid]) return reject(p, 404);
      const ground = new URLSearchParams(path.split("?")[1] || "").get("view") === "ground";
      if (ground && !isShared(aid)) return reject(p, 403);   // only if the astronaut opted out
      return Promise.resolve(circadian(aid));
    }
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
    if (CHECKIN_PATH.test(path)) {
      const m = (MANUAL[path.split("/")[2]] ||= {});
      if (body.sleep_h != null) m.sleep_h_last_night = body.sleep_h;
      if (body.mood_1to5 != null) m.mood_1to5 = body.mood_1to5;
      return Promise.resolve({ accepted: true });
    }
    return Promise.reject(new Error(`mock: no POST ${path}`));
  }

  function put(path, body) {
    console.info("[mock] PUT", path, body);
    let m = path.match(/^\/astronauts\/([^/]+)\/circadian\/sharing$/);
    if (m) { setShared(m[1], !!body.share_with_ground); return Promise.resolve({ share_with_ground: !!body.share_with_ground }); }
    m = path.match(/^\/astronauts\/([^/]+)\/lighting$/);
    if (m) { lightingOverride[m[1]] = { mode: body.mode, cct_k: CCT_K[body.mode], since: iso(new Date()) }; return Promise.resolve(lightingOverride[m[1]]); }
    return reject(path, 404);
  }

  window.Mock = { EventSource: MockEventSource, get, post, put };
})();
