// Written with AI assistance (Claude Code, Anthropic) and reviewed by the team. See README "Use of AI".
// Test feed (owner, 2026-11-14). Signed in as `test` (or with ?test in the
// URL), Mission Control shows one scripted test subject instead of the crew.
// Every 10 s the feed sends the next step, going through the vitals in turn:
//   step 1: heart rate WRONG (deep in the red zone), everything else usual
//   step 2: heart rate GOOD (its usual)
//   step 3: SpO2 wrong, step 4: SpO2 good, ... then round again.
// So every green-to-red threshold scale is shown going red and back to green.
// The step comes from the clock, so every open tab shows the same step.
// No backend involved: the stream is simulated in the browser, like mock.js.

(function () {
  const STEP_MS = 10000;

  const USUAL = {
    heart_rate_bpm: 70, spo2_pct: 98, resp_rate_bpm: 14, temp_c: 36.6,
    sleep_h_last_night: 7.5, mood_1to5: 4, hrv_sdnn_ms: 50, hrv_for_stress: 50,
    bone_density_g_cm2: 1.2, muscle_mass_kg: 26,
  };
  // Wrong readings: each past its critical threshold (common.js THRESHOLDS).
  const WRONG = {
    heart_rate_bpm: 98,          // +40 %
    spo2_pct: 91,                // 7 points below usual
    resp_rate_bpm: 21,           // +50 %
    temp_c: 38.1,                // +1.5 °C
    sleep_h_last_night: 4.5,     // -40 %
    mood_1to5: 1,                // 3 below usual
    hrv_sdnn_ms: 32,             // -36 %
    hrv_for_stress: 26,          // stress is derived from HRV: this gives ~100
    bone_density_g_cm2: 1.15,    // -4.2 %
    muscle_mass_kg: 24.4,        // -6.2 %
  };
  // The vitals in the order they are tested (same order as the tiles).
  const ORDER = [
    ["heart_rate_bpm", "Heart rate"], ["spo2_pct", "SpO₂"], ["resp_rate_bpm", "Resp. rate"],
    ["temp_c", "Temperature"], ["sleep_h_last_night", "Sleep last night"], ["mood_1to5", "Mood"],
    ["hrv_sdnn_ms", "HRV"], ["hrv_for_stress", "Stress"], ["bone_density_g_cm2", "Bone density"],
    ["muscle_mass_kg", "Muscle mass"],
  ];

  const stepNo = (t = Date.now()) => Math.floor(t / STEP_MS);
  function step(t = Date.now()) {
    const n = stepNo(t);
    const [key, label] = ORDER[Math.floor(n / 2) % ORDER.length];
    return { key, label, wrong: n % 2 === 0, nextInS: Math.ceil((STEP_MS - (t % STEP_MS)) / 1000) };
  }

  function snapshot() {
    const s = step();
    const v = { ...USUAL };
    if (s.wrong) v[s.key] = WRONG[s.key];
    const hrv = s.key === "hrv_for_stress" ? v.hrv_for_stress : v.hrv_sdnn_ms;
    const baseline = { ...USUAL };
    delete v.hrv_for_stress; delete baseline.hrv_for_stress;
    return { ...v, hrv_sdnn_ms: hrv, baseline, timestamp: new Date().toISOString().replace(/\.\d+Z$/, "Z"),
             source: "test feed", test_step: s };
  }

  // EventSource stand-in: "open", then a "vitals" event now and on every step.
  class TestEventSource {
    constructor() {
      this.readyState = 0;
      this.listeners = {};
      this.onopen = this.onerror = this.onmessage = null;
      this.timers = [];
      this.timers.push(setTimeout(() => {
        this.readyState = 1;
        if (this.onopen) this.onopen(new Event("open"));
        this.emit();
        // align to the step boundary, then every step
        this.timers.push(setTimeout(() => { this.emit(); this.timers.push(setInterval(() => this.emit(), STEP_MS)); },
                                    STEP_MS - (Date.now() % STEP_MS) + 50));
      }, 100));
    }
    addEventListener(type, fn) { (this.listeners[type] ||= []).push(fn); }
    removeEventListener(type, fn) { this.listeners[type] = (this.listeners[type] || []).filter(f => f !== fn); }
    emit() {
      if (this.readyState !== 1) return;
      const data = JSON.stringify(snapshot());
      (this.listeners.vitals || []).forEach(fn => fn(new MessageEvent("vitals", { data })));
    }
    close() { this.readyState = 2; this.timers.forEach(t => { clearTimeout(t); clearInterval(t); }); }
  }

  const session = window.AHMAuth && window.AHMAuth.session();
  window.AHMTestFeed = {
    enabled: new URLSearchParams(location.search).has("test") || (session && session.role === "test"),
    crew: [{ id: "t1", name: "Test subject", role: "Test feed", status: "nominal" }],
    EventSource: TestEventSource,
    step,
    STEP_S: STEP_MS / 1000,
  };
})();
