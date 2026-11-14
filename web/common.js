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
    return { url, source: mock ? new window.Mock.EventSource(url) : new EventSource(url) };
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
    FIELDS, PROFILE_NAMES, REGION_NAMES, SEVERITY_RANK, ENV_NAMES,
    settings, linkWithSettings, openStream, getJSON, postJSON, putJSON,
    LIGHTING_NAMES, circadianCardText,
    verdict, deltaPct, dur, fmt, esc, profileName,
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
  document.querySelectorAll("[data-user]").forEach(el => { el.textContent = who ? `Signed in as ${who.user} · ${who.label}` : ""; });
  // "All views" and other presenter-only links.
  if (!who || who.role !== "demo") document.querySelectorAll("[data-demo-only]").forEach(el => { el.hidden = true; });
  document.querySelectorAll("[data-signout]").forEach(b => b.addEventListener("click", () => window.AHMAuth.logout()));
})();
