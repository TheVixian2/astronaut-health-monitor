// Shared helpers for every web view. Field names follow docs/api-spec.md.
// Exposes window.AHM.

(function () {
  const FIELDS = [
    { key: "heart_rate_bpm", label: "Heart rate", unit: "bpm", region: "heart" },
    { key: "spo2_pct", label: "SpO₂", unit: "%", region: "lungs" },
    { key: "resp_rate_bpm", label: "Resp. rate", unit: "/min", region: "lungs" },
    { key: "temp_c", label: "Temperature", unit: "°C", region: "skin" },
    { key: "sleep_h_last_night", label: "Sleep last night", unit: "h", region: "head" },
    { key: "mood_1to5", label: "Mood", unit: "/5", region: "head" },
    // Heart-rate variability as Apple Watch records it (SDNN, ms). From the
    // watch for a1, simulated for the others (backend).
    { key: "hrv_sdnn_ms", label: "HRV", unit: "ms", region: "heart" },
    // Derived here from HRV (withStress below), not sent by the backend.
    { key: "stress_0to100", label: "Stress", unit: "/100", region: "head", derived: true },
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

  // ---- stress level -----------------------------------------------------------
  // Watches estimate stress from heart-rate variability: when the nervous system
  // is under load, the time between beats varies less. Apple Watch records HRV
  // as SDNN (ms) but keeps no stress score of its own, so the scale is ours
  // (owner's request, 2026-11-14), a design choice and not a validated score:
  //   HRV at the astronaut's own usual = 30 (low); every 10 % below it adds 16.
  //   Bands as on other watches' 0-100 stress scales: 0-25 resting, 26-50 low,
  //   51-75 medium, 76-100 high.
  const STRESS_AT_USUAL = 30;
  const STRESS_BANDS = [[25, "Resting"], [50, "Low"], [75, "Medium"], [100, "High"]];
  function stressFromHrv(hrv, usual) {
    if (typeof hrv !== "number" || typeof usual !== "number" || usual <= 0) return null;
    return Math.max(0, Math.min(100, Math.round(STRESS_AT_USUAL + (1 - hrv / usual) * 160)));
  }
  function stressBand(score) {
    return score == null ? "" : STRESS_BANDS.find(([max]) => score <= max)[1];
  }
  // A vitals snapshot with stress_0to100 added (and the usual level in baseline).
  function withStress(v) {
    if (!v || typeof v.hrv_sdnn_ms !== "number") return v;
    const usual = v.baseline ? v.baseline.hrv_sdnn_ms : null;
    const score = stressFromHrv(v.hrv_sdnn_ms, usual);
    return { ...v, stress_0to100: score,
             baseline: v.baseline ? { ...v.baseline, stress_0to100: score == null ? null : STRESS_AT_USUAL } : v.baseline };
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

  window.AHM = {
    FIELDS, PROFILE_NAMES, REGION_NAMES, SEVERITY_RANK, ENV_NAMES, vitalIcon,
    settings, linkWithSettings, openStream, getJSON, postJSON, putJSON,
    LIGHTING_NAMES, circadianCardText,
    verdict, deltaPct, dur, fmt, esc, profileName,
    withStress, stressBand, withScan,
    HAZARDS, HRP_RISKS, nasaRefs,
  };

  // ---- physical vs psychological ----------------------------------------------
  // The Commander's view sorts warnings into these two groups. (Crew members
  // never see warnings at all: decision, NotKaemy 2026-11-14.)
  const PSYCH_PROFILES = new Set(["sleep_debt"]);
  const isPsychological = a => a.hazard === "isolation" || PSYCH_PROFILES.has(a.profile);

  // ---- watch the whole crew (Commander, ship's doctor) -------------------------
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
  const who = window.AHMAuth && window.AHMAuth.session();
  document.querySelectorAll("[data-user]").forEach(el => { el.textContent = who ? `Signed in as ${who.user}: ${who.label}` : ""; });
  // "All views" and other presenter-only links.
  if (!who || who.role !== "demo") document.querySelectorAll("[data-demo-only]").forEach(el => { el.hidden = true; });
  document.querySelectorAll("[data-signout]").forEach(b => b.addEventListener("click", () => window.AHMAuth.logout()));
})();
