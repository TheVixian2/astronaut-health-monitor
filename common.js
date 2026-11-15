// Written with AI assistance (Claude Code, Anthropic) and reviewed by the team. See README "Use of AI".
// Shared helpers for every web view. Field names follow docs/api-spec.md.
// Exposes window.AHM.

(function () {
  const FIELDS = [
    { key: "heart_rate_bpm", label: "Heart rate", unit: "bpm", region: "heart" },
    { key: "spo2_pct", label: "SpO₂", unit: "%", region: "lungs" },
    { key: "resp_rate_bpm", label: "Resp. rate", unit: "/min", region: "lungs" },
    { key: "temp_c", label: "Temperature", unit: "°C", region: "skin", dp: 1 },
    { key: "sleep_h_last_night", label: "Sleep last night", unit: "h", region: "head" },
    // `axis`: a fixed chart scale for vitals with set bounds (owner, 2026-11-15):
    // mood reads 5 4 3 2 1, stress never goes below 0 (steps at its bands).
    { key: "mood_1to5", label: "Mood", unit: "/5", region: "head", axis: { min: 1, max: 5, step: 1 } },
    // Heart-rate variability as Apple Watch records it (SDNN, ms). From the
    // watch for a1, simulated for the others (backend).
    { key: "hrv_sdnn_ms", label: "HRV", unit: "ms", region: "heart" },
    // The backend's wellbeing score (GET /astronauts/{id}/wellbeing), added by withStress below.
    { key: "stress_0to100", label: "Stress", unit: "/100", region: "head", derived: true, axis: { min: 0, max: 100, step: 25 } },
    // From the weekly portable X-ray (DXA) scan (owner, 2026-11-14): whole-body
    // bone mineral density, and lean tissue of the arms and legs (the scan's
    // stand-in for skeletal muscle). Both change slowly, so their change shows
    // 1 decimal; `dp` is how many decimals the value itself shows.
    { key: "bone_density_g_cm2", label: "Bone density", unit: "g/cm²", region: "skin", dp: 3, deltaDp: 1 },
    { key: "muscle_mass_kg", label: "Muscle mass", unit: "kg", region: "skin", dp: 1, deltaDp: 1 },
  ];

  // ---- X-ray (DXA) scan: simulated until the backend sends it -----------------
  // PROVISIONAL bridge: the backend does not send bone_density_g_cm2 or
  // muscle_mass_kg yet (asked in STATUS.md). Until it does, the console fills
  // in a simulated weekly scan and says so on screen. Usual = the scan from
  // mission days 7-14; the latest scan is lower since:
  //   bone density ~0.35 %/month, the whole-body loss measured after
  //     long-duration flights (LeBlanc et al. 2000);
  //   muscle mass ~0.4 %/month, a PLACEHOLDER rate, not a published figure.
  // A field the backend does send is used as is and its row here is ignored.
  const SIM_SCAN = {            // field -> astronaut -> [usual, latest scan]
    bone_density_g_cm2: { a1: [1.184, 1.18], a2: [1.236, 1.232], a3: [1.152, 1.148], a4: [1.21, 1.206] },
    muscle_mass_kg:     { a1: [25.4, 25.3], a2: [27.6, 27.5], a3: [23.8, 23.7], a4: [26.3, 26.2] },
  };
  // ---- menstrual cycle: an opt-in, private adjustment of "usual" ---------------
  // (owner, 2026-11-14). Every reading is judged against the astronaut's own
  // usual, which already covers differences between bodies, but not a monthly
  // rhythm: in the second (luteal) half of the cycle temperature rises about
  // 0.3-0.5 °C, resting heart rate a few beats and HRV dips a little. With one
  // fixed usual that would be flagged every month. So an astronaut can switch
  // this on from their own console: the usual for temperature, heart rate and
  // HRV then follows their cycle. Only their own console shows the cycle; every
  // other view just compares readings with the adjusted usual.
  // Saved in this browser per astronaut ("ahm-cycle"); a real system would keep
  // it with the astronaut's private data on the backend.
  // Simplified model: the usual is the first-half (follicular) value; luteal
  // shifts +0.35 °C, +4 % heart rate, -8 % HRV; ovulation 14 days before the
  // next period, a 2-day rise after it, half back on the last day.
  const CYCLE_KEY = "ahm-cycle";
  const CYCLE_SHIFT = { temp_c: ["abs", 0.35], heart_rate_bpm: ["pct", 4], hrv_sdnn_ms: ["pct", -8] };
  function cycleSettings() { try { return JSON.parse(localStorage.getItem(CYCLE_KEY) || "{}"); } catch { return {}; } }
  function cycleFor(aid) { const c = cycleSettings()[aid]; return c && c.start && c.len ? c : null; }
  function setCycle(aid, c) {
    try {
      const all = cycleSettings();
      if (c) all[aid] = c; else delete all[aid];
      localStorage.setItem(CYCLE_KEY, JSON.stringify(all));
    } catch { /* private window: not remembered */ }
  }
  // -> { day (1..len), len, luteal (0-1: how far into the second-half shift) } or null
  function cycleAt(aid, t) {
    const c = cycleFor(aid);
    if (!c) return null;
    const L = Math.max(21, Math.min(40, Math.round(c.len)));
    const day = ((Math.floor((t - c.start) / 864e5) % L) + L) % L + 1;
    const ov = L - 14;
    const luteal = day <= ov ? 0 : day === L ? 0.5 : Math.min(1, (day - ov) / 2);
    return { day, len: L, luteal };
  }
  // A vitals snapshot with its usual shifted for the cycle phase (and `cycle`).
  function withCycle(v, aid) {
    if (!v || !v.baseline) return v;
    const cy = cycleAt(aid, v.timestamp ? Date.parse(v.timestamp) : Date.now());
    if (!cy) return v;
    const b = { ...v.baseline };
    for (const [k, [how, x]] of Object.entries(CYCLE_SHIFT)) {
      if (typeof b[k] !== "number") continue;
      b[k] = how === "abs" ? Math.round((b[k] + x * cy.luteal) * 10) / 10 : Math.round(b[k] * (1 + (x / 100) * cy.luteal));
    }
    return { ...v, baseline: b, cycle: cy };
  }

  // ---- thresholds: how far a reading is from the astronaut's OWN usual -------
  // For the green-to-red scales on Mission Control (owner, 2026-11-14). Never a
  // population range: every vital is judged against that astronaut's usual.
  // `steps` = where watch (yellow), alert (orange) and critical (red) start.
  // PLACEHOLDER values, to be tuned like the condition profiles.
  //   by "pct": % away from usual   "abs": units away   "score": the value itself
  //   dir: which way is bad ("down", "up" or "both")
  const THRESHOLDS = {
    heart_rate_bpm:     { by: "pct",   dir: "both", steps: [10, 20, 30] },
    spo2_pct:           { by: "abs",   dir: "down", steps: [2, 4, 6] },
    resp_rate_bpm:      { by: "pct",   dir: "both", steps: [15, 25, 40] },
    temp_c:             { by: "abs",   dir: "both", steps: [0.4, 0.8, 1.2] },
    sleep_h_last_night: { by: "pct",   dir: "down", steps: [15, 25, 35] },
    mood_1to5:          { by: "abs",   dir: "down", steps: [1, 2, 3] },
    hrv_sdnn_ms:        { by: "pct",   dir: "down", steps: [10, 20, 30] },
    stress_0to100:      { by: "score", dir: "up",   steps: [44, 58, 72] },   // backend levels watch, concern, urgent on the usual-30 scale
    bone_density_g_cm2: { by: "pct",   dir: "down", steps: [1, 2, 3] },
    muscle_mass_kg:     { by: "pct",   dir: "down", steps: [1.5, 3, 5] },
  };
  const LEVELS = ["ok", "watch", "alert", "critical"];
  // -> { level, pos (0-1 along the scale), steps (0-1 positions of the three
  //    boundaries), signed (signed change from usual, in the field's terms), by }
  //    or null when there is no reading / no usual to compare with.
  // For stress, pass the backend's level (v.stress_level): its safety rules (a
  // positive PHQ screen) can set a level above what the score alone gives.
  const STRESS_TO_THRESHOLD = { steady: "ok", watch: "watch", concern: "alert", urgent: "critical" };
  function thresholdLevel(key, now, base, backendLevel) {
    const t = THRESHOLDS[key];
    if (!t || typeof now !== "number") return null;
    let dev, signed;
    if (t.by === "score") { dev = signed = now; }
    else {
      if (typeof base !== "number" || (t.by === "pct" && base === 0)) return null;
      signed = t.by === "pct" ? ((now - base) / base) * 100 : now - base;
      dev = t.dir === "down" ? Math.max(0, -signed) : t.dir === "up" ? Math.max(0, signed) : Math.abs(signed);
    }
    const level = STRESS_TO_THRESHOLD[backendLevel] || LEVELS[t.steps.filter(s => dev >= s - 1e-9).length];
    const end = t.steps[2] * 1.25;              // the scale runs a bit past "critical"
    return { level, pos: Math.min(1, dev / end), steps: t.steps.map(s => s / end), signed, by: t.by };
  }

  function withScan(v, aid) {
    if (!v) return v;
    let out = v;
    for (const [key, byAid] of Object.entries(SIM_SCAN)) {
      if (typeof v[key] === "number" || !byAid[aid]) continue;
      const [usual, latest] = byAid[aid];
      out = { ...out, [key]: latest, simulated_scan: true,
              baseline: out.baseline ? { ...out.baseline, [key]: usual } : out.baseline };
    }
    return out;
  }

  // ---- instant start ----------------------------------------------------------
  // Pages fill from the backend's stored history before the first live event
  // (owner, 2026-11-15: no waiting on the stream in the demo). Rows of
  // GET /history (3 s buckets) turned into vitals snapshots, oldest first, with
  // the current baseline from GET /vitals. `upTo` (ms) cuts the newest rows off,
  // for the delayed Mission Control view.
  async function recentVitals(cfg, aid, seconds, upTo = Date.now()) {
    const id = encodeURIComponent(aid);
    if (cfg.mock) {                  // public demo: the recorded 24 h, hour by hour (mock-snapshot.js)
      try {
        const [snap, rows] = await Promise.all([getJSON(cfg.base, `/astronauts/${id}/vitals`, true),
          getJSON(cfg.base, `/astronauts/${id}/history?hours=24&bucket_s=3600`, true)]);
        const shift = Date.now() - Date.parse(rows[rows.length - 1].ts) - 3600e3;   // end just before "now"
        return rows.map(({ ts, low, high, ...vals }) => ({ ...vals, timestamp: new Date(Date.parse(ts) + shift).toISOString(), baseline: snap.baseline }))
          .filter(r => Date.parse(r.timestamp) <= upTo);
      } catch { return []; }
    }
    try {
      const [snap, recent] = await Promise.all([
        getJSON(cfg.base, `/astronauts/${id}/vitals`, false),
        getJSON(cfg.base, `/astronauts/${id}/history?hours=${(seconds / 3600).toFixed(4)}&bucket_s=3`, false)]);
      let rows = recent;
      // Just after a reset there are only a few live rows: use the seeded
      // history instead (one point per 10 min over the last 6 h), then the live ones.
      if (recent.length < 20) {
        const older = await getJSON(cfg.base, `/astronauts/${id}/history?hours=6&bucket_s=600`, false);
        const first = recent.length ? Date.parse(recent[0].ts) : Infinity;
        rows = older.filter(r => Date.parse(r.ts) < first).concat(recent);
      }
      return rows.filter(r => Date.parse(r.ts) <= upTo)
        .map(({ ts, low, high, ...vals }) => ({ ...vals, timestamp: ts, baseline: snap.baseline }));
    } catch { return []; }
  }

  // ---- stress level -----------------------------------------------------------
  // The station computer's wellbeing score (backend/behavioral.py), so every page
  // shows the backend's number (owner, 2026-11-15: the backend is the single
  // source). 0-100, higher = further from the astronaut's own normal: sleep, HRV,
  // activity, resting heart rate, time with crewmates and body clock carry 70 %,
  // check-ins 30 %, each against their own mission days 7-14. Bands = the
  // backend's levels. Commander first: while a flag waits for the commander, the
  // astronaut's own view has no score (withheld) and the tile shows none.
  // Fallback ONLY where the backend scores nothing (the presenter's simulated
  // whole-mission pattern, the scripted test feed): an estimate from HRV alone.
  //
  // Shown on a wearable-style stress scale whose USUAL IS 30, not 0 (owner,
  // 2026-11-15: "it cannot be 0"). Apple Watch has no stress score of its own
  // (it records HRV; apps such as Athlytic score 0-100 from it). The largest
  // published data for an HRV-based 0-100 stress score is Garmin's (Firstbeat
  // engine): the 2024 Garmin Connect data report gives a global average daily
  // stress of 30, "categorized as low" (countries 28-33, weekdays 29-32).
  //   shown = 30 + backend score x 0.7: their normal reads 30, the worst 100.
  // The backend's levels keep their exact cut-offs, moved onto this scale
  // (score 20 / 40 / 60 -> 44 / 58 / 72).
  const STRESS_USUAL = 30;
  const stressShown = score => (score == null ? null : Math.round(STRESS_USUAL + score * (100 - STRESS_USUAL) / 100));
  const STRESS_BANDS = [[43, "Steady"], [57, "Watch"], [71, "Concern"], [100, "Urgent"]];
  const stressCache = {};            // aid -> { score, withheld }, filled by loadStress()
  async function loadStress(cfg, aid, viewer) {
    try {
      const w = await getJSON(cfg.base, `/astronauts/${encodeURIComponent(aid)}/wellbeing?viewer=${encodeURIComponent(viewer)}`, cfg.mock);
      stressCache[aid] = { score: w.withheld ? null : w.score, level: w.withheld ? null : w.level, withheld: !!w.withheld };
    } catch { /* keep the last value */ }
    return stressCache[aid];
  }
  function stressFromHrv(hrv, usual) {   // fallback: 30 at their usual HRV, +16 per 10 % below it (lower above it)
    if (typeof hrv !== "number" || typeof usual !== "number" || usual <= 0) return null;
    return Math.max(0, Math.min(100, Math.round(STRESS_USUAL + (1 - hrv / usual) * 160)));
  }
  function stressBand(score, backendLevel) {
    if (backendLevel) return backendLevel[0].toUpperCase() + backendLevel.slice(1);
    return score == null ? "" : STRESS_BANDS.find(([max]) => score <= max)[1];
  }
  // A vitals snapshot with stress_0to100 added (its usual is STRESS_USUAL, 30).
  function withStress(v, aid) {
    if (!v) return v;
    const b = aid != null ? stressCache[aid] : undefined;
    let score, level = null, withheld = false;
    if (b) { score = stressShown(b.score); level = b.level; withheld = b.withheld; }
    else if (typeof v.hrv_sdnn_ms === "number") score = stressFromHrv(v.hrv_sdnn_ms, v.baseline ? v.baseline.hrv_sdnn_ms : null);
    else return v;
    return { ...v, stress_0to100: score, stress_level: level, stress_withheld: withheld,
             baseline: v.baseline ? { ...v.baseline, stress_0to100: STRESS_USUAL } : v.baseline };
  }

  // Flat icon per vital (24 x 24, filled shapes). Colour comes from CSS:
  // .vi-<name> sets `color` (tokens --ic-*), .d paths are the darker detail
  // tone, .m the thermometer's mercury. Use AHM.vitalIcon(key) for the HTML.
  const VITAL_ICONS = {
    heart_rate_bpm: ["heart", `<path d="M12 20.6c-.3 0-.5-.1-.7-.3C7.4 17 3 13.4 3 9.2 3 6.3 5.2 4 8 4c1.6 0 3.1.8 4 2 .9-1.2 2.4-2 4-2 2.8 0 5 2.3 5 5.2 0 4.2-4.4 7.8-8.3 11.1-.2.2-.4.3-.7.3z"/>
      <path class="ds" d="M4.5 11.3h3.6l1.5-2.6 2.4 5.2 1.9-3.9 1.1 1.3h4.5"/>`],
    spo2_pct: ["spo2", `<path d="M12 2.6c-.3 0-.5.1-.7.4C9.6 5.5 5.5 11 5.5 14.6a6.5 6.5 0 0 0 13 0C18.5 11 14.4 5.5 12.7 3c-.2-.3-.4-.4-.7-.4z"/>
      <circle class="d" cx="10" cy="15.6" r="1.9"/><circle class="d" cx="14.3" cy="13" r="1.2"/><circle class="d" cx="13.6" cy="17.6" r=".9"/>`],
    resp_rate_bpm: ["resp", `<rect x="11.1" y="2.5" width="1.8" height="8.5" rx=".9"/>
      <path d="M10.4 8.6V18c0 1.5-1.1 2.6-2.6 2.6-2.4 0-4.4-1.3-4.4-4.1 0-4 1.6-8.6 4-9.7 1.6-.7 3 .2 3 1.8z"/>
      <path d="M13.6 8.6V18c0 1.5 1.1 2.6 2.6 2.6 2.4 0 4.4-1.3 4.4-4.1 0-4-1.6-8.6-4-9.7-1.6-.7-3 .2-3 1.8z"/>
      <path class="ds" d="M7.5 12.5l1.6 1.4M7 16.2l2-.6M16.5 12.5l-1.6 1.4M17 16.2l-2-.6"/>`],
    temp_c: ["temp", `<rect x="9.4" y="2.4" width="5.2" height="13" rx="2.6"/><circle cx="12" cy="17.6" r="4.1"/>
      <rect class="m" x="11.1" y="7" width="1.8" height="9" rx=".9"/><circle class="m" cx="12" cy="17.6" r="2.4"/>
      <path class="ds-light" d="M16.3 5h2M16.3 8h1.4M16.3 11h2"/>`],
    sleep_h_last_night: ["sleep", `<path d="M20.2 14.6A8.4 8.4 0 1 1 9.4 3.8a6.8 6.8 0 0 0 10.8 10.8z"/>
      <path d="M16.6 3.2l.6 1.4 1.4.6-1.4.6-.6 1.4-.6-1.4-1.4-.6 1.4-.6z"/><path d="M20.4 7.6l.4.9.9.4-.9.4-.4.9-.4-.9-.9-.4.9-.4z"/>`],
    mood_1to5: ["mood", `<circle cx="12" cy="12" r="9.2"/>
      <circle class="d" cx="9" cy="10" r="1.3"/><circle class="d" cx="15" cy="10" r="1.3"/>
      <path class="ds" d="M8.3 14.2c.9 1.6 2.2 2.4 3.7 2.4s2.8-.8 3.7-2.4"/>`],
    // a pulse trace with uneven beat spacing: the variability between beats
    hrv_sdnn_ms: ["hrv", `<rect x="2.4" y="4.4" width="19.2" height="15.2" rx="3.6"/>
      <path class="ds" d="M4.4 13.2h2.4l1.2-4.6 1.8 8.2 1.4-3.6h1.9l.9-3.1 1.5 6.2 1-2.7h3.1"/>`],
    // a gauge with the needle towards the high end
    // a bone
    bone_density_g_cm2: ["bone", `<g transform="rotate(-45 12 12)"><rect x="6.5" y="10" width="11" height="4" rx="1.2"/>
      <circle cx="6.3" cy="9.7" r="2.7"/><circle cx="6.3" cy="14.3" r="2.7"/>
      <circle cx="17.7" cy="9.7" r="2.7"/><circle cx="17.7" cy="14.3" r="2.7"/></g>`],
    // a flexed arm
    muscle_mass_kg: ["muscle", `<path d="M3.4 20.2c-.2-3 .5-6 2.1-8.5l2.6-4c.3-.5.5-1 .5-1.6V4.6c0-.9.7-1.6 1.6-1.6h2.4c.9 0 1.6.7 1.6 1.6 0 .8-.6 1.5-1.4 1.6l-1.3.2v3.3c1.3-1 2.9-1.5 4.6-1.5 3.3 0 6 2.6 6 5.9v1.4c0 3.1-2.5 5.6-5.6 5.6H4.7c-.7 0-1.3-.5-1.3-1.2z"/>
      <path class="ds" d="M11.2 14.6c1.2-1.6 3-2.4 5-2.3"/>`],
    stress_0to100: ["stress", `<path d="M12 4.6a9.5 9.5 0 0 0-8.4 13.9c.3.6.9.9 1.5.9h13.8c.6 0 1.2-.3 1.5-.9A9.5 9.5 0 0 0 12 4.6z"/>
      <path class="ds" d="M6.1 14.4h1.5M8 9.1l1 1M12 7.3v1.4M16 9.1l-1 1M16.4 14.4h1.5M12 15.2l3.7-4.6"/>
      <circle class="d" cx="12" cy="15.2" r="1.7"/>`],
  };
  // The vital's icon colour (its --ic-* token), so a chart line matches the icon; --accent otherwise.
  function vitalColor(key) {
    const css = getComputedStyle(document.documentElement);
    const ic = VITAL_ICONS[key];
    return (ic && css.getPropertyValue(`--ic-${ic[0]}`).trim()) || css.getPropertyValue("--accent").trim();
  }
  function vitalIcon(key) {
    const ic = VITAL_ICONS[key];
    return ic ? `<span class="vi vi-${ic[0]}" aria-hidden="true"><svg viewBox="0 0 24 24">${ic[1]}</svg></span>` : "";
  }

  // Display names for condition profiles. Unknown ids fall back to the raw id,
  // so post-pivot profiles still render before they are added here.
  const PROFILE_NAMES = {
    orthostatic: "Cardiovascular deconditioning",
    sans: "SANS risk (eyes)",
    co2: "CO₂ exposure",
    fever: "Fever / possible infection",
    sleep_debt: "Sleep debt / strain",
    spe: "Solar particle event",
    wellbeing_concern: "Wellbeing concern",
    wellbeing_urgent: "Wellbeing: urgent",
  };

  // NASA Human Research Program references, shown with every alert
  // (docs/resources.md: official challenge resources). Titles are copied
  // verbatim from https://www.nasa.gov/hrp/hazards and
  // https://www.nasa.gov/hrp/risks (read 2026-11-14) — don't paraphrase them.
  const HAZARDS = {
    radiation: { name: "Space Radiation", url: "https://www.nasa.gov/hrp/hazard-space-radiation/" },
    isolation: { name: "Isolation and Confinement", url: "https://www.nasa.gov/hrp/hazard-isolation-and-confinement/" },
    distance: { name: "Distance from Earth", url: "https://www.nasa.gov/hrp/hazard-distance-from-earth/" },
    gravity: { name: "Gravity Fields", url: "https://www.nasa.gov/hrp/hazard-gravity-fields/" },
    environment: { name: "Hostile/Closed Environments", url: "https://www.nasa.gov/hrp/hazard-hostile-closed-environments/" },
  };
  const HAZARDS_INDEX = "https://www.nasa.gov/hrp/hazards/";

  const REF = "https://www.nasa.gov/reference/";
  // Condition profile -> official HRP risk. `co2` has no matching risk on the
  // NASA list, so it deliberately shows its hazard only.
  const HRP_RISKS = {
    orthostatic: { title: "Risk of Cardiovascular Adaptations", url: REF + "risk-of-cardiovascular-adaptations/" },
    sans: { title: "Risk of Spaceflight Associated Neuro-ocular Syndrome (SANS)", url: REF + "risk-of-spaceflight-associated-neuro-ocular-syndrome-sans/" },
    fever: { title: "Risk of Altered Immune System Responses", url: REF + "risk-of-altered-immune-system-responses/" },
    sleep_debt: { title: "Risk of Inadequate Sleep and Irregular Schedules", url: REF + "risk-from-inadequate-sleep-and-irregular-schedules/" },
    spe: { title: "Risk of Radiation-Induced Cancers", url: REF + "risk-of-radiation-induced-cancers/" },
  };

  // "NASA hazard: Gravity Fields ↗ · NASA risk: Risk of … ↗" as HTML.
  function nasaRefs(alert) {
    const link = (url, text) => `<a href="${esc(url)}" target="_blank" rel="noopener">${esc(text)}</a>`;
    const parts = [];
    const h = HAZARDS[alert.hazard];
    if (h) parts.push(`NASA hazard: ${link(h.url, h.name)}`);
    else if (alert.hazard) parts.push(`Hazard: ${link(HAZARDS_INDEX, alert.hazard)}`);
    const r = HRP_RISKS[alert.profile];
    if (r) parts.push(`NASA risk: ${link(r.url, r.title)}`);
    return parts.length ? `<div class="nasa-ref small">${parts.join(" · ")}</div>` : "";
  }

  const REGION_NAMES ={ heart: "Heart", head: "Head", lungs: "Lungs", skin: "Skin", whole_body: "Whole body" };
  const SEVERITY_RANK = { watch: 1, alert: 2, critical: 3 };
  const ENV_NAMES = { iss: "ISS", moon: "Moon", mars: "Mars" };

  // ?base=...&aid=...&view=...&mock  — shared across pages.
  function settings() {
    const p = new URLSearchParams(location.search);
    return {
      base: (p.get("base") || "http://localhost:8000").replace(/\/+$/, ""),
      aid: p.get("aid") || "a1",
      view: p.get("view") || "crew",
      mock: p.has("mock") || location.hostname.endsWith("github.io"),   // Pages has no backend
    };
  }

  // Carry the current settings onto links to other pages.
  function linkWithSettings(href, overrides = {}) {
    const s = { ...settings(), ...overrides };
    const p = new URLSearchParams();
    if (s.base !== "http://localhost:8000") p.set("base", s.base);
    if (s.aid !== "a1") p.set("aid", s.aid);
    if (s.mock) p.set("mock", "");
    const q = p.toString().replace(/=(&|$)/g, "$1");
    return q ? `${href}?${q}` : href;
  }

  function openStream({ base, aid, view, mock }) {
    const url = `${base}/astronauts/${encodeURIComponent(aid)}/stream?view=${view}`;
    return { url, source: mock ? new window.Mock.EventSource(url) : new PausingEventSource(url) };
  }

  // Browsers allow only 6 open connections to one server, shared by EVERY tab,
  // and each live stream holds one for as long as it is open (Mission Control
  // holds 4, one per astronaut). A couple of forgotten tabs then use them all
  // and every new page sits on "connecting…" with no data (seen 2026-11-14:
  // a Mission Control tab + a demo tab starve a new console). So a stream
  // closes once its tab has been hidden for HIDDEN_GRACE_MS and reopens when
  // the tab is shown again. The grace period keeps quick window switches
  // live (a window covered by another counts as hidden too, and a reopened
  // Mission Control stream waits out the light delay again).
  // Same interface as EventSource for what the pages use: addEventListener,
  // onopen / onerror / onmessage, readyState, close().
  const HIDDEN_GRACE_MS = 15000;
  class PausingEventSource {
    constructor(url) {
      this.url = url;
      this.listeners = [];
      this.es = null;
      this.closed = false;
      this.pauseTimer = null;
      this.onopen = this.onerror = this.onmessage = null;
      this.onVisibility = () => {
        clearTimeout(this.pauseTimer);
        if (document.hidden) this.pauseTimer = setTimeout(() => this.pause(), HIDDEN_GRACE_MS);
        else this.resume();
      };
      document.addEventListener("visibilitychange", this.onVisibility);
      this.resume();
      if (document.hidden) this.onVisibility();   // opened in the background: same grace
    }
    get readyState() { return this.closed ? 2 : this.es ? this.es.readyState : 0; }   // paused = connecting
    addEventListener(type, fn, opts) {
      this.listeners.push([type, fn, opts]);
      if (this.es) this.es.addEventListener(type, fn, opts);
    }
    removeEventListener(type, fn) {
      this.listeners = this.listeners.filter(([t, f]) => !(t === type && f === fn));
      if (this.es) this.es.removeEventListener(type, fn);
    }
    resume() {
      if (this.es || this.closed) return;
      const es = this.es = new EventSource(this.url);
      es.onopen = e => this.onopen && this.onopen(e);
      es.onerror = e => this.onerror && this.onerror(e);
      es.onmessage = e => this.onmessage && this.onmessage(e);
      this.listeners.forEach(([t, fn, o]) => es.addEventListener(t, fn, o));
    }
    pause() {
      if (!this.es) return;
      this.es.close();
      this.es = null;
    }
    close() {
      clearTimeout(this.pauseTimer);
      this.pause();
      this.closed = true;
      document.removeEventListener("visibilitychange", this.onVisibility);
    }
  }

  // Errors carry .status so callers can tell 403 (private) from 404 (missing).
  function httpError(path, status) {
    const err = new Error(`${path} → HTTP ${status}`);
    err.status = status;
    return err;
  }

  async function getJSON(base, path, mock) {
    if (mock) return window.Mock.get(path);
    const r = await fetch(base + path);
    if (!r.ok) throw httpError(path, r.status);
    return r.json();
  }

  async function putJSON(base, path, body, mock) {
    if (mock) return window.Mock.put(path, body);
    const r = await fetch(base + path, {
      method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    if (!r.ok) throw httpError(path, r.status);
    return r.json().catch(() => ({}));
  }

  async function postJSON(base, path, body, mock) {
    if (mock) return window.Mock.post(path, body);
    const r = await fetch(base + path, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    if (!r.ok) throw httpError(path, r.status);
    return r.json().catch(() => ({}));
  }

  // SSLA lighting modes (GET /astronauts/{id}/circadian -> lighting.mode).
  const LIGHTING_NAMES = { general: "General", pre_sleep: "Pre-sleep", phase_shift: "Phase-shift", off: "Lights off" };

  // Spec shows `card` as an object, backend/circadian.py returns a string or
  // null. Accept both until the shape settles.
  function circadianCardText(card) {
    if (card == null) return null;
    if (typeof card === "string") return card;
    return card.text || card.message || null;
  }

  // CLAUDE.md: round trip > act_within_s -> "Act on board now", else "Ground will see this in X".
  // Round trip uses the REAL light time; one_way_delay_s is only the demo-compressed delivery delay.
  // Returns {onboard: bool|null, text}.
  function verdict(alert, mission) {
    if (!mission) return { onboard: null, text: `Act within ${dur(alert.act_within_s)}` };
    const roundTrip = 2 * (mission.real_one_way_delay_s ?? mission.one_way_delay_s);
    return roundTrip > alert.act_within_s
      ? { onboard: true, text: `Act on board now — ${dur(alert.act_within_s)} window` }
      : { onboard: false, text: `Ground will see this in ${dur(alert.ground_eta_s ?? mission.one_way_delay_s)}` };
  }

  function deltaPct(now, base) {
    if (typeof now !== "number" || typeof base !== "number" || base === 0) return null;
    return ((now - base) / base) * 100;
  }

  function dur(s) {
    if (s == null) return "?";
    s = Math.round(s);
    if (s < 60) return `${s} s`;
    if (s < 3600) return `${Math.round(s / 60)} min`;
    if (s < 86400) return `${Math.round(s / 3600)} h`;
    return `${Math.round(s / 86400)} d`;
  }

  const fmt = x => (x == null ? "—" : String(x));
  const esc = x => String(x ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const profileName = id => PROFILE_NAMES[id] || id;

  // ---- health: how close readings are to the person's own usual -------------
  // 0-100 %: each reading scores 100 in its usual range, 67 at watch, 33 at
  // alert, 0 at critical (the scales Mission Control colours by, THRESHOLDS),
  // then the average. Our own summary, not a clinical score. `v` is a derived
  // reading (withCycle / withStress / withScan applied).
  const HEALTH_POINTS = { ok: 100, watch: 67, alert: 33, critical: 0 };
  function healthScore(v) {
    if (!v) return null;
    const levels = FIELDS.map(f => thresholdLevel(f.key, v[f.key], v.baseline ? v.baseline[f.key] : null,
                                                  f.key === "stress_0to100" ? v.stress_level : null))
      .filter(Boolean).map(x => x.level);
    if (!levels.length) return null;
    const pct = Math.round(levels.reduce((s, l) => s + HEALTH_POINTS[l], 0) / levels.length);
    return { pct, level: pct >= 85 ? "ok" : pct >= 60 ? "watch" : pct >= 35 ? "alert" : "critical",
             inRange: levels.filter(l => l === "ok").length, total: levels.length };
  }

  // ---- what the Commander or the Crew Medical Officer sent (owner, 2026-11-15) --
  // A crew member's health bar and "From your commander" box change only when
  // the Commander or the CMO presses "Send to <name>":
  // { at, by, by_role, health: healthScore(), warnings: [{severity, title, detail, alertId}] | null }.
  // Stored by the backend (PUT/GET /astronauts/{id}/shared-check), so every device
  // shows it; this browser keeps a copy (localStorage) so the page draws at once,
  // and mock mode (the public site) keeps it here only.
  const SENT_KEY = "ahm-sent-to-crew";
  function sentTo(aid) {
    try { return JSON.parse(localStorage.getItem(SENT_KEY) || "{}")[aid] || null; } catch { return null; }
  }
  function keepSent(aid, data) {
    try {
      const all = JSON.parse(localStorage.getItem(SENT_KEY) || "{}");
      if (data) all[aid] = data; else delete all[aid];
      localStorage.setItem(SENT_KEY, JSON.stringify(all));
    } catch { /* private window: not kept */ }
  }
  async function setSentTo(aid, data, cfg, viewer) {
    keepSent(aid, data);
    if (cfg && !cfg.mock) {
      await putJSON(cfg.base, `/astronauts/${encodeURIComponent(aid)}/shared-check?viewer=${encodeURIComponent(viewer)}`, data, false);
    }
  }
  async function loadSentTo(cfg, aid, viewer) {
    if (cfg.mock) return sentTo(aid);
    try {
      const d = await getJSON(cfg.base, `/astronauts/${encodeURIComponent(aid)}/shared-check?viewer=${encodeURIComponent(viewer)}`, false);
      keepSent(aid, d || null);
    } catch { /* offline: keep the last copy */ }
    return sentTo(aid);
  }

  // ---- body silhouettes and crew avatars -----------------------------------
  // Male and female front-view silhouettes (viewBox 0 0 200 400) for the body
  // card on My health. Generated: the two figures have the same points per
  // part, so the paths morph (self-check.js setSex).
  const BODY_SHAPES = {
    male: {
      armL: "M59.9 79.2 C57.4 75.3 51.5 80.9 48.8 83.7 C46.1 86.5 44.5 91.5 43.8 95.9 C43 100.4 44 105.6 44.3 110.4 C44.7 115.2 45.9 120 46 124.9 C46.1 129.7 45.6 134.6 44.9 139.3 C44.2 144.1 42.8 149 41.6 153.3 C40.4 157.5 38.9 161.2 37.7 164.9 C36.5 168.6 35.4 172.2 34.3 175.5 C33.3 178.9 32.4 182.6 31.5 185 C30.7 187.4 30.3 188.4 29.3 190 C28.3 191.6 26.6 193 25.4 194.4 C24.2 195.8 22.7 197.1 22.1 198.3 C21.4 199.5 21.3 200.9 21.5 201.7 C21.8 202.4 22.7 203 23.8 202.8 C24.8 202.6 27.3 200.1 27.7 200.6 C28 201 28.4 205.8 28.2 208.3 C28 210.9 26.7 214.1 26.5 216.1 C26.4 218.2 26.6 219.8 27.1 220.6 C27.6 221.3 28.8 221.6 29.3 220.6 C29.9 219.6 30.1 216.5 30.4 214.5 C30.8 212.4 31.4 208.2 31.5 208.3 C31.7 208.5 32.3 214.2 32.7 216.7 C33 219.2 33.2 222.3 33.8 223.4 C34.3 224.5 35.5 224.6 36 223.4 C36.5 222.2 36.4 218.6 36.6 216.1 C36.7 213.7 37 208.9 37.1 208.9 C37.2 208.9 38.2 214.5 38.8 216.7 C39.3 218.9 39.8 221.4 40.5 222.3 C41.1 223.1 42.3 223 42.7 221.7 C43 220.4 42.6 216.7 42.7 214.5 C42.8 212.2 43.1 208.4 43.2 208.3 C43.3 208.3 44.3 212.2 44.9 213.9 C45.5 215.6 45.9 217.8 46.6 218.4 C47.2 218.9 48.5 218.6 48.8 217.3 C49.1 216 48.4 213.2 48.2 210.6 C48.1 208 47.9 205.4 47.7 201.7 C47.5 198 46.5 192.8 47.1 188.3 C47.8 183.9 50.1 179.2 51.6 175 C53.1 170.7 54.7 166.8 56 162.7 C57.3 158.6 58.4 154.7 59.4 150.5 C60.4 146.2 61.3 141.2 62.2 137.1 C63 133 64.1 131 64.4 126 C64.7 121 64.6 114.9 63.8 107.1 C63.1 99.3 62.4 83.1 59.9 79.2 Z",
      armR: "M136.2 107.1 C135.4 114.9 135.3 121 135.6 126 C135.9 131 137 133 137.8 137.1 C138.7 141.2 139.6 146.2 140.6 150.5 C141.6 154.7 142.7 158.6 144 162.7 C145.3 166.8 146.9 170.7 148.4 175 C149.9 179.2 152.2 183.9 152.9 188.3 C153.5 192.8 152.5 198 152.3 201.7 C152.1 205.4 151.9 208 151.8 210.6 C151.6 213.2 150.9 216 151.2 217.3 C151.5 218.6 152.8 218.9 153.4 218.4 C154.1 217.8 154.5 215.6 155.1 213.9 C155.7 212.2 156.7 208.3 156.8 208.3 C156.9 208.4 157.2 212.2 157.3 214.5 C157.4 216.7 157 220.4 157.3 221.7 C157.7 223 158.9 223.1 159.5 222.3 C160.2 221.4 160.7 218.9 161.2 216.7 C161.8 214.5 162.8 208.9 162.9 208.9 C163 208.9 163.3 213.7 163.4 216.1 C163.6 218.6 163.5 222.2 164 223.4 C164.5 224.6 165.7 224.5 166.2 223.4 C166.8 222.3 167 219.2 167.3 216.7 C167.7 214.2 168.3 208.5 168.5 208.3 C168.6 208.2 169.2 212.4 169.6 214.5 C169.9 216.5 170.1 219.6 170.7 220.6 C171.2 221.6 172.4 221.3 172.9 220.6 C173.4 219.8 173.6 218.2 173.5 216.1 C173.3 214.1 172 210.9 171.8 208.3 C171.6 205.8 172 201 172.3 200.6 C172.7 200.1 175.2 202.6 176.2 202.8 C177.3 203 178.2 202.4 178.5 201.7 C178.7 200.9 178.6 199.5 177.9 198.3 C177.3 197.1 175.8 195.8 174.6 194.4 C173.4 193 171.7 191.6 170.7 190 C169.7 188.4 169.3 187.4 168.5 185 C167.6 182.6 166.7 178.9 165.7 175.5 C164.6 172.2 163.5 168.6 162.3 164.9 C161.1 161.2 159.6 157.5 158.4 153.3 C157.2 149 155.8 144.1 155.1 139.3 C154.4 134.6 153.9 129.7 154 124.9 C154.1 120 155.3 115.2 155.7 110.4 C156 105.6 157 100.4 156.2 95.9 C155.5 91.5 153.9 86.5 151.2 83.7 C148.5 80.9 142.6 75.3 140.1 79.2 C137.6 83.1 136.9 99.3 136.2 107.1 Z",
      legL: "M85.5 157.1 C80.5 154 72.6 158.1 69.9 160.5 C67.3 162.9 69.8 167 69.4 171.6 C69 176.3 68.2 181.8 67.7 188.3 C67.3 194.8 66.6 203.5 66.6 210.6 C66.6 217.6 67.2 223.6 67.7 230.6 C68.3 237.7 69.1 245.6 69.9 252.9 C70.8 260.1 71.9 268.3 72.7 274 C73.6 279.8 74.9 283.1 75 287.4 C75 291.6 73.8 295.2 73.3 299.6 C72.7 304.1 71.6 308.9 71.6 314.1 C71.6 319.3 72.4 325.2 73.3 330.8 C74.2 336.3 76 342.7 77.2 347.5 C78.4 352.2 80.4 355.6 80.5 359.2 C80.6 362.7 78.8 365.4 77.7 368.6 C76.7 371.9 75.1 375.7 74.4 378.6 C73.7 381.6 73 384.3 73.3 386.4 C73.6 388.6 74.8 390.8 76.1 391.4 C77.4 392.1 81.7 392 84.4 392 C87.1 392 91 392 92.2 391.4 C93.4 390.9 94.5 389.5 95 387.5 C95.5 385.6 95.2 382.7 95 379.8 C94.8 376.8 94.2 373.3 93.9 369.7 C93.6 366.2 93.5 363.4 93.3 358.6 C93.1 353.8 92.6 346.7 92.8 340.8 C93 334.9 94.1 328.6 94.4 323 C94.8 317.4 95 312.3 95 307.4 C95 302.5 94.5 297.8 94.4 293.5 C94.3 289.2 94.2 287.8 94.4 281.8 C94.7 275.8 95.6 265.1 96.1 257.3 C96.6 249.5 96.8 241.9 97.2 235.1 C97.6 228.2 97.9 220.8 98.3 216.1 C98.8 211.5 99.7 213.4 100 207.2 C100.3 201.1 102.4 187.8 100 179.4 C97.6 171.1 90.5 160.3 85.5 157.1 Z",
      legR: "M100 179.4 C97.6 187.8 99.7 201.1 100 207.2 C100.3 213.4 101.2 211.5 101.7 216.1 C102.1 220.8 102.4 228.2 102.8 235.1 C103.2 241.9 103.4 249.5 103.9 257.3 C104.4 265.1 105.3 275.8 105.6 281.8 C105.8 287.8 105.7 289.2 105.6 293.5 C105.5 297.8 105 302.5 105 307.4 C105 312.3 105.2 317.4 105.6 323 C105.9 328.6 107 334.9 107.2 340.8 C107.4 346.7 106.9 353.8 106.7 358.6 C106.5 363.4 106.4 366.2 106.1 369.7 C105.8 373.3 105.2 376.8 105 379.8 C104.8 382.7 104.5 385.6 105 387.5 C105.5 389.5 106.6 390.9 107.8 391.4 C109 392 112.9 392 115.6 392 C118.3 392 122.6 392.1 123.9 391.4 C125.2 390.8 126.4 388.6 126.7 386.4 C127 384.3 126.3 381.6 125.6 378.6 C124.9 375.7 123.3 371.9 122.3 368.6 C121.2 365.4 119.4 362.7 119.5 359.2 C119.6 355.6 121.6 352.2 122.8 347.5 C124 342.7 125.8 336.3 126.7 330.8 C127.6 325.2 128.4 319.3 128.4 314.1 C128.4 308.9 127.3 304.1 126.7 299.6 C126.2 295.2 125 291.6 125 287.4 C125.1 283.1 126.4 279.8 127.3 274 C128.1 268.3 129.2 260.1 130.1 252.9 C130.9 245.6 131.7 237.7 132.3 230.6 C132.8 223.6 133.4 217.6 133.4 210.6 C133.4 203.5 132.7 194.8 132.3 188.3 C131.8 181.8 131 176.3 130.6 171.6 C130.2 167 132.7 162.9 130.1 160.5 C127.4 158.1 119.5 154 114.5 157.1 C109.5 160.3 102.4 171.1 100 179.4 Z",
      torso: "M87.8 42.5 C83.6 44.4 87.6 50.7 87.2 53.6 C86.8 56.6 86.8 58.9 85.5 60.3 C84.3 61.7 80.7 63 77.7 64.2 C74.8 65.4 71.2 66.3 67.7 67.5 C64.2 68.8 59.8 69.7 56.6 71.4 C53.3 73.2 50.4 75.2 48.2 78.1 C46.1 81.1 44.6 85.2 43.8 89.3 C43 93.3 42.4 98.4 43.2 102.6 C44.1 106.8 46.4 111.3 48.8 114.3 C51.2 117.3 55 118.7 57.7 120.4 C60.4 122.2 63.5 121.3 64.9 124.9 C66.4 128.4 66.1 136 66.6 141.6 C67.2 147.1 67.8 153.3 68.3 158.3 C68.7 163.3 68.7 167 69.4 171.6 C70 176.3 70.6 181.8 72.2 186.1 C73.8 190.4 75.9 194.4 78.9 197.2 C81.8 200 86.5 201.3 90 202.8 C93.5 204.3 96.7 206.1 100 206.1 C103.3 206.1 106.5 204.3 110 202.8 C113.5 201.3 118.2 200 121.1 197.2 C124.1 194.4 126.2 190.4 127.8 186.1 C129.4 181.8 130 176.3 130.6 171.6 C131.3 167 131.3 163.3 131.7 158.3 C132.2 153.3 132.8 147.1 133.4 141.6 C133.9 136 133.6 128.4 135.1 124.9 C136.5 121.3 139.6 122.2 142.3 120.4 C145 118.7 148.8 117.3 151.2 114.3 C153.6 111.3 155.9 106.8 156.8 102.6 C157.6 98.4 157 93.3 156.2 89.3 C155.4 85.2 153.9 81.1 151.8 78.1 C149.6 75.2 146.7 73.2 143.4 71.4 C140.2 69.7 135.8 68.8 132.3 67.5 C128.8 66.3 125.2 65.4 122.3 64.2 C119.3 63 115.7 61.7 114.5 60.3 C113.2 58.9 113.2 56.6 112.8 53.6 C112.4 50.7 116.4 44.4 112.2 42.5 C108.1 40.6 91.9 40.6 87.8 42.5 Z",
      earL: "M81.6 32.5 C81 30.1 79 30.6 78.3 31.4 C77.6 32.1 77.1 34.9 77.2 36.9 C77.3 39 78 42.1 78.9 43.6 C79.7 45.1 81.7 47.7 82.2 45.8 C82.7 44 82.3 34.9 81.6 32.5 Z",
      earR: "M117.8 45.8 C118.3 47.7 120.3 45.1 121.1 43.6 C122 42.1 122.7 39 122.8 36.9 C122.9 34.9 122.4 32.1 121.7 31.4 C121 30.6 119 30.1 118.4 32.5 C117.7 34.9 117.3 44 117.8 45.8 Z",
      head: "M100 8 C96.7 8 92.8 8.6 90 10.2 C87.2 11.9 84.8 14.9 83.3 18 C81.8 21.2 81.3 25.4 81.1 29.1 C80.9 32.9 81.4 37.1 82.2 40.3 C82.9 43.4 83.9 45.8 85.5 48.1 C87.2 50.3 89.8 52.3 92.2 53.6 C94.6 54.9 97.4 55.9 100 55.9 C102.6 55.9 105.4 54.9 107.8 53.6 C110.2 52.3 112.8 50.3 114.5 48.1 C116.1 45.8 117.1 43.4 117.8 40.3 C118.6 37.1 119.1 32.9 118.9 29.1 C118.7 25.4 118.2 21.2 116.7 18 C115.2 14.9 112.8 11.9 110 10.2 C107.2 8.6 103.3 8 100 8 Z",
    },
    female: {
      armL: "M66.6 79.2 C64.7 75.3 59.5 80.9 57.1 83.7 C54.7 86.5 53.2 91.5 52.4 95.9 C51.5 100.4 52.1 105.6 52.2 110.4 C52.3 115.2 53.2 120 53 124.9 C52.9 129.7 52.3 134.6 51.5 139.3 C50.6 144.1 49.3 149 48.1 153.3 C46.9 157.5 45.5 161.2 44.3 164.9 C43.2 168.6 42.1 172.2 41.1 175.5 C40 178.9 38.8 182.6 37.9 185 C37 187.3 36.7 188.1 35.7 189.6 C34.7 191 33.2 192.4 32 193.7 C30.9 194.9 29.6 196.2 28.9 197.3 C28.3 198.4 28.1 199.7 28.3 200.3 C28.5 201 29.3 201.5 30.3 201.3 C31.2 201.2 33.6 198.9 33.9 199.3 C34.2 199.8 34.4 204.1 34.1 206.5 C33.9 208.8 32.6 211.8 32.4 213.6 C32.2 215.5 32.3 217.1 32.7 217.8 C33.1 218.4 34.2 218.7 34.7 217.8 C35.3 216.8 35.5 214 35.9 212.1 C36.3 210.2 37 206.4 37.1 206.5 C37.2 206.6 37.6 211.8 37.8 214.1 C38.1 216.4 38.2 219.3 38.6 220.3 C39.1 221.3 40.2 221.4 40.6 220.3 C41.1 219.2 41.1 215.9 41.4 213.6 C41.6 211.4 42 207 42.1 207 C42.2 207 42.9 212.1 43.3 214.1 C43.8 216.2 44.1 218.5 44.7 219.3 C45.2 220 46.3 219.9 46.7 218.8 C47.1 217.6 46.8 214.2 47 212.1 C47.1 210.1 47.5 206.5 47.6 206.5 C47.7 206.4 48.5 210 49 211.6 C49.4 213.1 49.7 215.2 50.3 215.7 C50.9 216.2 52.1 215.9 52.4 214.7 C52.7 213.5 52.2 210.9 52.1 208.5 C52 206.1 51.9 203.7 51.9 200.3 C51.8 196.9 51.2 192.3 51.8 188 C52.4 183.8 54.3 179.2 55.6 175 C56.9 170.7 58.6 166.8 59.8 162.7 C61.1 158.6 62.1 154.7 63.2 150.5 C64.2 146.2 65.2 141.2 66.1 137.1 C66.9 133 67.9 131 68.4 126 C68.8 121 69 114.9 68.7 107.1 C68.4 99.3 68.5 83.1 66.6 79.2 Z",
      armR: "M131.3 107.1 C131 114.9 131.2 121 131.6 126 C132.1 131 133.1 133 133.9 137.1 C134.8 141.2 135.8 146.2 136.8 150.5 C137.9 154.7 138.9 158.6 140.2 162.7 C141.4 166.8 143.1 170.7 144.4 175 C145.7 179.2 147.6 183.8 148.2 188 C148.8 192.3 148.2 196.9 148.1 200.3 C148.1 203.7 148 206.1 147.9 208.5 C147.8 210.9 147.3 213.5 147.6 214.7 C147.9 215.9 149.1 216.2 149.7 215.7 C150.3 215.2 150.6 213.1 151 211.6 C151.5 210 152.3 206.4 152.4 206.5 C152.5 206.5 152.9 210.1 153 212.1 C153.2 214.2 152.9 217.6 153.3 218.8 C153.7 219.9 154.8 220 155.3 219.3 C155.9 218.5 156.2 216.2 156.7 214.1 C157.1 212.1 157.8 207 157.9 207 C158 207 158.4 211.4 158.6 213.6 C158.9 215.9 158.9 219.2 159.4 220.3 C159.8 221.4 160.9 221.3 161.4 220.3 C161.8 219.3 161.9 216.4 162.2 214.1 C162.4 211.8 162.8 206.6 162.9 206.5 C163 206.4 163.7 210.2 164.1 212.1 C164.5 214 164.7 216.8 165.3 217.8 C165.8 218.7 166.9 218.4 167.3 217.8 C167.7 217.1 167.8 215.5 167.6 213.6 C167.4 211.8 166.1 208.8 165.9 206.5 C165.6 204.1 165.8 199.8 166.1 199.3 C166.4 198.9 168.8 201.2 169.7 201.3 C170.7 201.5 171.5 201 171.7 200.3 C171.9 199.7 171.7 198.4 171.1 197.3 C170.4 196.2 169.1 194.9 168 193.7 C166.8 192.4 165.3 191 164.3 189.6 C163.3 188.1 163 187.3 162.1 185 C161.2 182.6 160 178.9 158.9 175.5 C157.9 172.2 156.8 168.6 155.7 164.9 C154.5 161.2 153.1 157.5 151.9 153.3 C150.7 149 149.4 144.1 148.5 139.3 C147.7 134.6 147.1 129.7 147 124.9 C146.8 120 147.7 115.2 147.8 110.4 C147.9 105.6 148.5 100.4 147.6 95.9 C146.8 91.5 145.3 86.5 142.9 83.7 C140.5 80.9 135.3 75.3 133.4 79.2 C131.5 83.1 131.6 99.3 131.3 107.1 Z",
      legL: "M86.6 151.6 C82.3 147.9 76.1 154.9 73.8 157.1 C71.6 159.4 74.5 160.5 73.3 164.9 C72.1 169.4 68.6 177.6 66.6 183.9 C64.7 190.2 62.1 196.1 61.6 202.8 C61.1 209.5 62.8 216.2 63.8 223.9 C64.8 231.6 66.3 240.9 67.7 249 C69.1 257 71 266.1 72.2 272.3 C73.4 278.6 74.7 281.8 75 286.3 C75.2 290.7 74.2 294.4 73.8 299.1 C73.5 303.7 72.7 308.8 72.7 314.1 C72.7 319.4 73.1 325.2 73.8 330.8 C74.6 336.3 76.2 342.7 77.2 347.5 C78.2 352.2 79.9 355.6 80 359.2 C80.1 362.7 78.6 365.4 77.7 368.6 C76.9 371.9 75.5 375.7 75 378.6 C74.4 381.6 74 384.3 74.4 386.4 C74.8 388.6 76 390.8 77.2 391.4 C78.4 392.1 82.1 392 84.4 392 C86.7 392 90 392 91.1 391.4 C92.2 390.9 93.4 389.5 93.9 387.5 C94.3 385.6 94 382.7 93.9 379.8 C93.8 376.8 93.5 373.3 93.3 369.7 C93.1 366.2 92.9 363.4 92.8 358.6 C92.7 353.8 92.5 346.7 92.8 340.8 C93 334.9 94.1 328.6 94.4 323 C94.8 317.4 94.9 312.3 95 307.4 C95.1 302.5 94.9 297.9 95 293.5 C95.1 289 95.2 286.7 95.5 280.7 C95.9 274.7 96.8 264.9 97.2 257.3 C97.7 249.7 98 241.7 98.3 235.1 C98.7 228.4 99.2 221.7 99.4 217.3 C99.7 212.8 99.9 214.7 100 208.3 C100.1 202 102.2 188.9 100 179.4 C97.8 169.9 91 155.3 86.6 151.6 Z",
      legR: "M100 179.4 C97.8 188.9 99.9 202 100 208.3 C100.1 214.7 100.3 212.8 100.6 217.3 C100.8 221.7 101.3 228.4 101.7 235.1 C102 241.7 102.3 249.7 102.8 257.3 C103.2 264.9 104.1 274.7 104.5 280.7 C104.8 286.7 104.9 289 105 293.5 C105.1 297.9 104.9 302.5 105 307.4 C105.1 312.3 105.2 317.4 105.6 323 C105.9 328.6 107 334.9 107.2 340.8 C107.5 346.7 107.3 353.8 107.2 358.6 C107.1 363.4 106.9 366.2 106.7 369.7 C106.5 373.3 106.2 376.8 106.1 379.8 C106 382.7 105.7 385.6 106.1 387.5 C106.6 389.5 107.8 390.9 108.9 391.4 C110 392 113.3 392 115.6 392 C117.9 392 121.6 392.1 122.8 391.4 C124 390.8 125.2 388.6 125.6 386.4 C126 384.3 125.6 381.6 125 378.6 C124.5 375.7 123.1 371.9 122.3 368.6 C121.4 365.4 119.9 362.7 120 359.2 C120.1 355.6 121.8 352.2 122.8 347.5 C123.8 342.7 125.4 336.3 126.2 330.8 C126.9 325.2 127.3 319.4 127.3 314.1 C127.3 308.8 126.5 303.7 126.2 299.1 C125.8 294.4 124.8 290.7 125 286.3 C125.3 281.8 126.6 278.6 127.8 272.3 C129 266.1 130.9 257 132.3 249 C133.7 240.9 135.2 231.6 136.2 223.9 C137.2 216.2 138.9 209.5 138.4 202.8 C137.9 196.1 135.3 190.2 133.4 183.9 C131.4 177.6 127.9 169.4 126.7 164.9 C125.5 160.5 128.4 159.4 126.2 157.1 C123.9 154.9 117.7 147.9 113.4 151.6 C109 155.3 102.2 169.9 100 179.4 Z",
      torso: "M89.4 42.5 C85.9 44.4 89.7 50.6 89.4 53.6 C89.1 56.7 88.9 59.4 87.8 60.9 C86.6 62.4 83.2 63.6 80.5 64.8 C77.8 66 74.6 67 71.6 68.1 C68.6 69.2 65.4 69.9 62.7 71.4 C60 73 57.2 74.9 55.5 77.6 C53.7 80.3 52.8 84 52.1 87.6 C51.5 91.2 51.1 95.5 51.6 99.3 C52 103.1 53.3 107.2 54.9 110.4 C56.6 113.6 59.5 116 61.6 118.2 C63.7 120.4 66.6 120.4 67.7 123.8 C68.8 127.1 67.6 133.2 68.3 138.2 C68.9 143.2 70.8 149.4 71.6 153.8 C72.5 158.3 72.6 160.3 73.3 164.9 C73.9 169.6 74.2 176.8 75.5 181.6 C76.8 186.5 78.6 190.6 81.1 193.9 C83.6 197.1 87.4 199.3 90.5 201.1 C93.7 203 96.8 205 100 205 C103.2 205 106.3 203 109.5 201.1 C112.6 199.3 116.4 197.1 118.9 193.9 C121.4 190.6 123.2 186.5 124.5 181.6 C125.8 176.8 126.1 169.6 126.7 164.9 C127.4 160.3 127.5 158.3 128.4 153.8 C129.2 149.4 131.1 143.2 131.7 138.2 C132.4 133.2 131.2 127.1 132.3 123.8 C133.4 120.4 136.3 120.4 138.4 118.2 C140.5 116 143.4 113.6 145.1 110.4 C146.7 107.2 148 103.1 148.4 99.3 C148.9 95.5 148.5 91.2 147.9 87.6 C147.2 84 146.3 80.3 144.5 77.6 C142.8 74.9 140 73 137.3 71.4 C134.6 69.9 131.4 69.2 128.4 68.1 C125.4 67 122.2 66 119.5 64.8 C116.8 63.6 113.4 62.4 112.2 60.9 C111.1 59.4 110.9 56.7 110.6 53.6 C110.3 50.6 114.1 44.4 110.6 42.5 C107 40.6 93 40.6 89.4 42.5 Z",
      earL: "M81.6 32.5 C81 30.1 79 30.6 78.3 31.4 C77.6 32.1 77.1 34.9 77.2 36.9 C77.3 39 78 42.1 78.9 43.6 C79.7 45.1 81.7 47.7 82.2 45.8 C82.7 44 82.3 34.9 81.6 32.5 Z",
      earR: "M117.8 45.8 C118.3 47.7 120.3 45.1 121.1 43.6 C122 42.1 122.7 39 122.8 36.9 C122.9 34.9 122.4 32.1 121.7 31.4 C121 30.6 119 30.1 118.4 32.5 C117.7 34.9 117.3 44 117.8 45.8 Z",
      head: "M100 4.1 C96.1 4.1 91.7 4.5 88.3 6.3 C85 8.2 81.8 11.6 80 15.2 C78.1 18.9 77.7 23.7 77.2 28 C76.6 32.4 76.4 37.6 76.6 41.4 C76.8 45.2 76.2 48.8 78.3 50.9 C80.4 52.9 85.8 52.7 89.4 53.6 C93 54.6 96.5 56.4 100 56.4 C103.5 56.4 107 54.6 110.6 53.6 C114.2 52.7 119.6 52.9 121.7 50.9 C123.8 48.8 123.2 45.2 123.4 41.4 C123.6 37.6 123.4 32.4 122.8 28 C122.3 23.7 121.9 18.9 120 15.2 C118.2 11.6 115 8.2 111.7 6.3 C108.3 4.5 103.9 4.1 100 4.1 Z",
    },
  };

  // Which figure a crew member gets. GET /crew has no `sex` field yet, so: the
  // Male/Female switch on their My health card (remembered in this browser per
  // astronaut), else `sex` from the backend when it sends one ("male"/"female",
  // "M"/"F"), else the demo crew's default below.
  const DEFAULT_SEX = { a1: "female", a2: "male", a3: "female", a4: "male" };
  const SEX_KEY = "ahm-body-sex";
  function normSex(v) { return /^f/i.test(v || "") ? "female" : /^m/i.test(v || "") ? "male" : null; }
  function storedSex(aid) {
    try { return normSex(JSON.parse(localStorage.getItem(SEX_KEY) || "{}")[aid]); } catch { return null; }
  }
  function rememberSex(aid, sex) {
    try {
      const all = JSON.parse(localStorage.getItem(SEX_KEY) || "{}");
      all[aid] = sex;
      localStorage.setItem(SEX_KEY, JSON.stringify(all));
    } catch { /* private window: still switches, just not remembered */ }
  }
  function sexOf(member) {
    const id = member && member.id;
    return storedSex(id) || normSex(member && member.sex) || DEFAULT_SEX[id] || "male";
  }

  // Heart and lungs, drawn over the torso (the My health body card uses these too).
  const BODY_ORGANS = {
    heart: `<rect x="96.3" y="88.3" width="3.7" height="17.2" rx="1.6"/> <rect x="101.3" y="82.6" width="2" height="7.4" rx="1"/> <rect x="104.1" y="80.9" width="2" height="8.2" rx="1"/> <rect x="107.1" y="82.6" width="2" height="6.6" rx="1"/> <path d="M 100.4 104.7 L 100.4 94.9 C 100.4 86.7 111.5 86.7 111.5 94.1 L 111.5 100.6 L 107.8 100.6 L 107.8 94.5 C 107.8 90.8 104.1 90.8 104.1 94.9 L 104.1 104.7 Z"/> <path d="M 95.9 103.1 C 92.6 108.8 92.6 117 96.7 122.8 C 101.6 127.7 111.5 128.5 119.7 126 C 123 124.4 123 121.1 122.1 117.8 C 120.5 112.1 117.2 105.5 112.3 102.3 C 107.4 99.8 100.8 100.6 95.9 103.1 Z"/>`,
    lungs: `<path d="M 86.9 67.8 C 78.7 71.1 72.1 87.5 71.3 108 C 70.5 118.7 71.3 125.2 73.8 128.5 Q 84.4 118.7 95.1 125.2 C 96.7 112.1 95.9 87.5 94.3 74.4 C 92.6 69.5 90.2 67 86.9 67.8 Z"/> <path d="M 113.1 67.8 C 121.3 71.1 127.9 87.5 128.7 108 C 129.5 118.7 128.7 125.2 126.2 128.5 Q 121.3 121.9 117.2 126.9 C 120.5 120.3 122.1 109.6 115.6 103.1 C 109.8 98.2 105.7 90.8 105.7 74.4 C 107.4 69.5 109.8 67 113.1 67.8 Z"/>`,
  };

  // A crew member's whole-body avatar (owner, 2026-11-14): the My health
  // silhouette, male or female by sexOf, with the affected parts filled in
  // their severity colour (style.css .body-fig).
  //   hits: { part: level }, part one of head, heart, lungs, skin (arms and
  //   legs, as on My health), torso, whole_body (outlines the whole figure);
  //   level watch | alert | critical, or info (on treatment, nothing due).
  // Decorative: the text next to it says the same, so it is aria-hidden.
  const FIGURE_LIMBS = ["armL", "armR", "legL", "legR"];
  function bodyFigure(member, hits = {}, cls = "") {
    const sex = sexOf(member), s = BODY_SHAPES[sex];
    const lv = part => (hits[part] ? ` lv-${hits[part]}` : "");
    const paths = list => list.map(p => `<path d="${s[p]}"/>`).join("");
    const whole = hits.whole_body ? ` whole-${hits.whole_body}` : "";
    return `<svg class="body-fig${whole} ${cls}" data-sex="${sex}" viewBox="20 2 160 392" aria-hidden="true" focusable="false">` +
      `<g class="bf-part${lv("skin")}" data-part="skin">${paths(FIGURE_LIMBS)}</g>` +
      `<g class="bf-part${lv("torso")}" data-part="torso">${paths(["torso"])}</g>` +
      `<g class="bf-heart${lv("heart")}" data-part="heart">${BODY_ORGANS.heart}</g>` +
      `<g class="bf-lungs${lv("lungs")}" data-part="lungs">${BODY_ORGANS.lungs}</g>` +
      `<g class="bf-part${lv("head")}" data-part="head">${paths(["earL", "earR", "head"])}</g></svg>`;
  }
  // Most urgent level per part, for bodyFigure: add(hits, part, level).
  const LEVEL_RANK = { info: 0, watch: 1, alert: 2, critical: 3 };
  function addHit(hits, part, level) {
    if (!part || !level) return hits;
    if (!(part in hits) || LEVEL_RANK[level] > LEVEL_RANK[hits[part]]) hits[part] = level;
    return hits;
  }

  window.AHM = {
    FIELDS, PROFILE_NAMES, REGION_NAMES, SEVERITY_RANK, ENV_NAMES, vitalIcon, vitalColor,
    settings, linkWithSettings, openStream, getJSON, postJSON, putJSON,
    LIGHTING_NAMES, circadianCardText,
    verdict, deltaPct, dur, fmt, esc, profileName,
    withStress, loadStress, recentVitals, stressBand, withScan, thresholdLevel,
    withCycle, cycleFor, cycleAt, setCycle, CYCLE_SHIFT,
    BODY_SHAPES, BODY_ORGANS, normSex, rememberSex, sexOf, bodyFigure, addHit,
    healthScore, sentTo, setSentTo, loadSentTo, SENT_KEY,
    HAZARDS, HRP_RISKS, nasaRefs,
  };

  // ---- physical vs psychological ----------------------------------------------
  // The Commander's view sorts warnings into these two groups. (Crew members
  // never see warnings at all: decision, NotKaemy 2026-11-14.)
  const PSYCH_PROFILES = new Set(["sleep_debt"]);
  const isPsychological = a => a.hazard === "isolation" || PSYCH_PROFILES.has(a.profile);

  // ---- watch the whole crew (Commander, Crew Medical Officer) -------------------------
  // These roles are on board, so nothing is delayed. Against the real backend
  // they POLL GET /vitals + GET /alerts every 3 s instead of holding 4 SSE
  // streams: a browser allows only ~6 connections per host, and the astronaut
  // console (1) + Ground (4) already need 5 when the demo runs on one machine.
  // Mock mode keeps in-page streams (they use no connections).
  const POLL_MS = 3000;

  async function watchCrew(cfg, opts = {}) {
    const list = await getJSON(cfg.base, "/crew", cfg.mock);
    if (cfg.mock) return streamCrew(cfg, list, opts);
    const { onVitals, onAlert, onConn } = opts;
    const lastTs = {};
    const poll = async () => {
      let ok = 0;
      await Promise.all(list.map(async c => {
        const p = `/astronauts/${encodeURIComponent(c.id)}`;
        try {
          if (onVitals) {
            const v = await getJSON(cfg.base, `${p}/vitals`, false);
            if (v.timestamp !== lastTs[c.id]) { lastTs[c.id] = v.timestamp; onVitals(c.id, v); }
          }
          if (onAlert) (await getJSON(cfg.base, `${p}/alerts`, false)).slice().reverse().forEach(onAlert);   // oldest first
          ok++;
        } catch { /* counted below */ }
      }));
      if (onConn) {
        if (ok === list.length) onConn("connected", "pill-on");
        else onConn(ok ? `${ok}/${list.length} reachable` : "offline", ok ? "pill-wait" : "pill-off");
      }
    };
    poll();
    setInterval(poll, POLL_MS);
    return list;
  }

  function streamCrew(cfg, list, { onVitals, onAlert, onConn } = {}) {
    const sources = [];
    const update = () => {
      const live = sources.filter(s => s.readyState === 1).length;
      if (!onConn) return;
      if (live === sources.length) onConn(cfg.mock ? "connected (mock)" : "connected", "pill-on");
      else onConn(live ? `${live}/${sources.length} streams` : "connecting…", "pill-wait");
    };
    for (const c of list) {
      const { source } = openStream({ ...cfg, aid: c.id, view: "crew" });
      sources.push(source);
      source.onopen = update;
      source.onerror = update;
      if (onVitals) source.addEventListener("vitals", e => onVitals(c.id, JSON.parse(e.data)));
      if (onAlert) source.addEventListener("alert", e => onAlert(JSON.parse(e.data)));
    }
    return list;
  }

  Object.assign(window.AHM, { isPsychological, watchCrew });

  // ---- page chrome shared by every page (menus, user, sign-out) -------------
  // Links marked data-href keep ?mock / ?base / ?aid when moving between pages.
  document.querySelectorAll("a[data-href]").forEach(a => { a.href = linkWithSettings(a.dataset.href); });
  // History keeps the menu of the page it was opened from (history.js reads ?from=).
  const fromPage = location.pathname.split("/").pop().replace(/\.html$/, "");
  document.querySelectorAll('a[data-href="history.html"]').forEach(a => {
    if (fromPage && fromPage !== "history") a.href += `${a.href.includes("?") ? "&" : "?"}from=${encodeURIComponent(fromPage)}`;
  });
  const who = window.AHMAuth && window.AHMAuth.session();
  // Just the role (the account name is the tooltip), so a seven-tab menu still
  // fits on one line at 1280 px.
  document.querySelectorAll("[data-user]").forEach(el => {
    el.textContent = who ? who.label : "";
    el.title = who ? `Signed in as ${who.user}` : "";
  });
  // "All views" and other presenter-only links.
  if (!who || who.role !== "demo") document.querySelectorAll("[data-demo-only]").forEach(el => { el.hidden = true; });
  document.querySelectorAll("[data-signout]").forEach(b => b.addEventListener("click", () => window.AHMAuth.logout()));
})();
