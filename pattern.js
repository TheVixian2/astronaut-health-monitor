// Written with AI assistance (Claude Code, Anthropic) and reviewed by the team. See README "Use of AI".
// Demo pattern (owner, 2026-11-14). Signed in as the presenter (`demo`), the
// vitals views show NO real-time data: a pattern for the whole mission so far
// is generated here and a period selector picks the stretch to look at.
// Deterministic (seeded by astronaut, vital and time), so every load and every
// page shows the same numbers for the same moment.
//
// Not used inside demo.html (the live, light-delay side-by-side stays live) or
// with ?live in the URL.
//
// The pattern, per astronaut, around their own usual (same usuals as the backend):
//   - a station day: asleep 23:00-07:00 UTC, exercise 15:00-16:00; heart rate,
//     temperature, breathing and HRV follow it; SpO2 dips a little in sleep
//   - sleep last night and mood: one value per night / day
//   - bone density and muscle mass: a weekly X-ray scan from day 10, slowly lower
//   - a2 (Mihai): strain builds through the second half of the mission (less
//     sleep, lower mood and HRV, higher heart rate), as the backend's a2 drift
//   - a4 (Jonas): a hard few days around day 31, then recovery

(function () {
  const session = window.AHMAuth && window.AHMAuth.session();
  const params = new URLSearchParams(location.search);
  const enabled = !!session && session.role === "demo" && window.top === window.self && !params.has("live");

  const HOUR = 3600e3, DAY = 24 * HOUR;
  const DAYS = 42;                                              // mission day "now" (backend default)
  const END = Math.floor(Date.now() / HOUR) * HOUR;             // now, to the hour
  const START = Math.floor(END / DAY) * DAY - (DAYS - 1) * DAY; // mission day 1, 00:00 station time (UTC)

  const USUAL = {
    a1: { heart_rate_bpm: 58, spo2_pct: 98, temp_c: 36.5, resp_rate_bpm: 12, sleep_h_last_night: 7.2, mood_1to5: 4, hrv_sdnn_ms: 55, bone_density_g_cm2: 1.184, muscle_mass_kg: 25.4 },
    a2: { heart_rate_bpm: 74, spo2_pct: 97, temp_c: 36.8, resp_rate_bpm: 15, sleep_h_last_night: 6.8, mood_1to5: 4, hrv_sdnn_ms: 42, bone_density_g_cm2: 1.236, muscle_mass_kg: 27.6 },
    a3: { heart_rate_bpm: 66, spo2_pct: 98, temp_c: 36.6, resp_rate_bpm: 13, sleep_h_last_night: 7.5, mood_1to5: 5, hrv_sdnn_ms: 50, bone_density_g_cm2: 1.152, muscle_mass_kg: 23.8 },
    a4: { heart_rate_bpm: 62, spo2_pct: 98, temp_c: 36.4, resp_rate_bpm: 14, sleep_h_last_night: 7.0, mood_1to5: 4, hrv_sdnn_ms: 47, bone_density_g_cm2: 1.21, muscle_mass_kg: 26.3 },
  };
  const DECIMALS = { temp_c: 1, sleep_h_last_night: 1, bone_density_g_cm2: 3, muscle_mass_kg: 1 };
  const round = (k, x) => { const p = 10 ** (DECIMALS[k] || 0); return Math.round(x * p) / p; };

  // ---- deterministic noise in [-1, 1] -----------------------------------------
  function hash(str) {
    let h = 2166136261;
    for (let i = 0; i < str.length; i++) { h ^= str.charCodeAt(i); h = Math.imul(h, 16777619); }
    h ^= h >>> 15; h = Math.imul(h, 0x2c1b3c6d); h ^= h >>> 12; h = Math.imul(h, 0x297a2d39); h ^= h >>> 15;
    return h >>> 0;
  }
  const rnd = (aid, key, i) => (hash(`${aid}|${key}|${i}`) / 4294967295) * 2 - 1;
  // smooth noise: hourly knots, eased in between
  function smooth(aid, key, t) {
    const u = (t - START) / HOUR, i = Math.floor(u), w = (1 - Math.cos(Math.PI * (u - i))) / 2;
    return rnd(aid, key, i) * (1 - w) + rnd(aid, key, i + 1) * w;
  }

  // ---- storylines: multipliers / offsets by (fractional) mission day ----------
  const ramp = (d, from, to) => Math.max(0, Math.min(1, (d - from) / (to - from)));
  function story(aid, d) {
    if (aid === "a2") { const r = ramp(d, 21, 40); return { hr: 1 + 0.07 * r, hrv: 1 - 0.18 * r, resp: 1 + 0.05 * r, sleep: -1.3 * r, mood: -1.6 * r }; }
    if (aid === "a4") { const r = Math.max(0, 1 - Math.abs(d - 31.5) / 2.5); return { hr: 1 + 0.12 * r, hrv: 1 - 0.3 * r, resp: 1 + 0.12 * r, sleep: -1.0 * r, mood: -1.2 * r }; }
    return { hr: 1, hrv: 1, resp: 1, sleep: 0, mood: 0 };
  }

  // The reading at time t (ms): same shape as GET /vitals, with `baseline`.
  function at(aid, t) {
    const u = USUAL[aid] || USUAL.a1;
    t = Math.max(START, Math.min(END, t));
    const d = (t - START) / DAY + 1;
    const hour = (((t % DAY) + DAY) % DAY) / HOUR;
    const asleep = hour >= 23 || hour < 7, exercise = hour >= 15 && hour < 16;
    const circ = Math.cos((2 * Math.PI * (hour - 16)) / 24);          // +1 at 16:00, -1 at 04:00
    const s = story(aid, d), n = k => smooth(aid, k, t);
    const night = Math.floor((t - START - 7 * HOUR) / DAY);             // the night that ended at the last 07:00
    const day = Math.floor((t - START) / DAY);
    const scanDay = d < 10 ? 10 : 10 + 7 * Math.floor((d - 10) / 7);    // weekly X-ray scan from day 10
    const months = (scanDay - 10) / 30;
    const v = {
      heart_rate_bpm: u.heart_rate_bpm * s.hr + 4 * circ - (asleep ? 6 : 0) + (exercise ? 38 : 0) + 2.5 * n("hr"),
      spo2_pct: Math.min(100, u.spo2_pct - (asleep ? 0.8 : 0) + 0.6 * n("spo2")),
      resp_rate_bpm: u.resp_rate_bpm * s.resp + 0.8 * circ + (exercise ? 7 : 0) - (asleep ? 1 : 0) + 0.7 * n("resp"),
      temp_c: u.temp_c + 0.25 * circ + (exercise ? 0.3 : 0) + 0.08 * n("temp"),
      sleep_h_last_night: u.sleep_h_last_night + story(aid, night + 1).sleep + 0.45 * rnd(aid, "sleep", night),
      mood_1to5: Math.max(1, Math.min(5, u.mood_1to5 + story(aid, day + 1).mood + 0.6 * rnd(aid, "mood", day))),
      hrv_sdnn_ms: u.hrv_sdnn_ms * s.hrv * (asleep ? 1.15 : 1) * (exercise ? 0.6 : 1) + 3 * n("hrv"),
      bone_density_g_cm2: u.bone_density_g_cm2 * (1 - 0.0035 * months) + 0.001 * rnd(aid, "bone", scanDay),
      muscle_mass_kg: u.muscle_mass_kg * (1 - 0.004 * months) + 0.08 * rnd(aid, "muscle", scanDay),
    };
    for (const k in v) v[k] = round(k, v[k]);
    return { ...v, baseline: { ...u }, timestamp: new Date(t).toISOString().replace(/\.\d+Z$/, "Z"), source: "pattern" };
  }

  // n points from `from` to `to`, each the average over its stretch (so a long
  // period shows the trend, not a random sample of hours). The last point is
  // the reading at `to` itself.
  function series(aid, from, to, n) {
    const out = [], step = (to - from) / Math.max(1, n - 1);
    for (let i = 0; i < n; i++) {
      // on whole hours for long periods, so the chart's labels read "D8 01:00"
      const tEnd = i === n - 1 ? to : step > HOUR ? Math.round((from + step * i) / HOUR) * HOUR : from + step * i;
      if (i === n - 1 || step <= HOUR) { out.push({ t: new Date(tEnd), v: at(aid, tEnd) }); continue; }
      const k = Math.min(12, Math.ceil(step / HOUR)), acc = {};
      let last;
      for (let j = 0; j < k; j++) {
        last = at(aid, tEnd - (step * j) / k);
        for (const key in USUAL.a1) acc[key] = (acc[key] || 0) + last[key] / k;
      }
      for (const key in acc) acc[key] = round(key, acc[key]);
      out.push({ t: new Date(tEnd), v: { ...last, ...acc } });
    }
    return out;
  }

  const pad = x => String(x).padStart(2, "0");
  const dayNo = t => Math.floor((t - START) / DAY) + 1;
  const clock = t => { const d = new Date(t); return `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}`; };
  const label = t => `Day ${dayNo(+t)}, ${clock(+t)}`;
  const shortLabel = t => `D${dayNo(+t)} ${clock(+t)}`;

  // ---- the period selector -----------------------------------------------------
  // A span (6 h ... whole mission) and the moment it ends at (slider, hourly).
  // Shared by every page through sessionStorage, so it stays put as you move.
  const SPANS = [["6h", "6 h", 6 * HOUR], ["24h", "24 h", DAY], ["7d", "7 days", 7 * DAY],
                 ["30d", "30 days", 30 * DAY], ["all", "Whole mission", null]];
  const KEY = "ahm-period";
  function loadState() {
    try { const s = JSON.parse(sessionStorage.getItem(KEY) || "null"); if (s && SPANS.some(x => x[0] === s.span)) return s; } catch { /* default */ }
    return { span: "24h", end: END };
  }
  function saveState(s) { try { sessionStorage.setItem(KEY, JSON.stringify(s)); } catch { /* fine without */ } }

  function control(host, onChange) {
    const state = loadState();
    const el = document.createElement("div");
    el.className = "period";
    el.setAttribute("role", "group");
    el.setAttribute("aria-label", "Time period");
    el.innerHTML = `<select aria-label="Period">${SPANS.map(([k, l]) => `<option value="${k}">${l}</option>`).join("")}</select>
      <input type="range" aria-label="Period ends at" step="1">
      <span class="period-label"></span>`;
    host.prepend(el);
    const sel = el.querySelector("select"), slider = el.querySelector("input"), out = el.querySelector(".period-label");
    sel.value = state.span;
    const span = () => SPANS.find(x => x[0] === sel.value)[2];
    let end = Math.min(END, Math.max(START, Number(state.end) || END));   // kept here: a slider clamps before min/max are set
    function apply(save) {
      const len = span();
      const minEnd = len ? Math.min(END, START + len) : END;
      slider.min = String(Math.round(minEnd / HOUR));
      slider.max = String(Math.round(END / HOUR));
      slider.disabled = !len || minEnd >= END;
      end = len ? Math.max(minEnd, Math.min(END, end)) : END;
      slider.value = String(Math.round(end / HOUR));
      const from = len ? Math.max(START, end - len) : START;
      out.textContent = `${label(from)} to ${label(end)}`;
      if (save) saveState({ span: sel.value, end });
      onChange({ from, to: end });
    }
    sel.addEventListener("change", () => apply(true));
    slider.addEventListener("input", () => { end = Number(slider.value) * HOUR; apply(true); });
    apply(false);
  }

  window.AHMPattern = { enabled, START, END, DAYS, at, series, label, shortLabel, control };
})();
