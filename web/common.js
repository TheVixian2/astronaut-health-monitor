// Shared helpers for every web view. Field names follow docs/api-spec.md.
// Exposes window.AHM.

(function () {
  const FIELDS = [
    { key: "heart_rate_bpm", label: "Heart rate", unit: "bpm", region: "heart" },
    { key: "systolic_mmhg", label: "Systolic BP", unit: "mmHg", region: "heart" },
    { key: "diastolic_mmhg", label: "Diastolic BP", unit: "mmHg", region: "heart" },
    { key: "spo2_pct", label: "SpO₂", unit: "%", region: "lungs" },
    { key: "resp_rate_bpm", label: "Resp. rate", unit: "/min", region: "lungs" },
    { key: "temp_c", label: "Temperature", unit: "°C", region: "skin" },
    { key: "sleep_h_last_night", label: "Sleep last night", unit: "h", region: "head" },
    { key: "mood_1to5", label: "Mood", unit: "/5", region: "head" },
  ];

  // Display names for condition profiles. Unknown ids fall back to the raw id,
  // so post-pivot profiles still render before they are added here.
  const PROFILE_NAMES = {
    orthostatic: "Cardiovascular deconditioning",
    sans: "SANS risk (eyes)",
    co2: "CO₂ exposure",
    fever: "Fever / possible infection",
    sleep_debt: "Sleep debt / strain",
    spe: "Solar particle event",
  };

  const REGION_NAMES = { heart: "Heart", head: "Head", lungs: "Lungs", skin: "Skin", whole_body: "Whole body" };
  const SEVERITY_RANK = { watch: 1, alert: 2, critical: 3 };
  const ENV_NAMES = { iss: "ISS", moon: "Moon", mars: "Mars" };

  // ?base=...&aid=...&view=...&mock  — shared across pages.
  function settings() {
    const p = new URLSearchParams(location.search);
    return {
      base: (p.get("base") || "http://localhost:8000").replace(/\/+$/, ""),
      aid: p.get("aid") || "a1",
      view: p.get("view") || "crew",
      mock: p.has("mock"),
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
    return { url, source: mock ? new window.Mock.EventSource(url) : new EventSource(url) };
  }

  async function getJSON(base, path, mock) {
    if (mock) return window.Mock.get(path);
    const r = await fetch(base + path);
    if (!r.ok) throw new Error(`${path} → HTTP ${r.status}`);
    return r.json();
  }

  async function postJSON(base, path, body, mock) {
    if (mock) return window.Mock.post(path, body);
    const r = await fetch(base + path, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    if (!r.ok) throw new Error(`${path} → HTTP ${r.status}`);
    return r.json().catch(() => ({}));
  }

  // CLAUDE.md: round trip > act_within_s -> "Act on board now", else "Ground will see this in X".
  // Returns {onboard: bool|null, text}.
  function verdict(alert, mission) {
    if (!mission) return { onboard: null, text: `Act within ${dur(alert.act_within_s)}` };
    const roundTrip = 2 * mission.one_way_delay_s;
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

  window.AHM = {
    FIELDS, PROFILE_NAMES, REGION_NAMES, SEVERITY_RANK, ENV_NAMES,
    settings, linkWithSettings, openStream, getJSON, postJSON,
    verdict, deltaPct, dur, fmt, esc, profileName,
  };
})();
