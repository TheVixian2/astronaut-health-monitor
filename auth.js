// Login gate and roles for every page. Load it in <head>, before anything else,
// so a signed-out visitor is redirected before the page draws.
//
// NOT SECURITY. Placeholder accounts for the hackathon demo, checked in the
// browser. Anyone can read them here, and the backend itself has no auth
// (docs/api-spec.md: "Auth: none"). Real login would need the backend.

(function () {
  // One account per role. Each role lands on its own interface and can only
  // open the pages listed for it in PAGE_ROLES. Change usernames/passwords here.
  const ACCOUNTS = {
    crew:    { password: "mars2026", role: "crew",    home: "self-check.html", label: "Astronaut" },
    captain: { password: "mars2026", role: "captain", home: "captain.html",    label: "Commander" },
    doctor:  { password: "mars2026", role: "doctor",  home: "doctor.html",     label: "Crew Medical Officer" },
    ground:  { password: "mars2026", role: "ground",  home: "ground.html",     label: "Mission Control" },
    demo:    { password: "mars2026", role: "demo",    home: "index.html",      label: "Presenter (all views)" },
  };

  // Which roles may open which page. "demo" (the presenter) may open all of them.
  const PAGE_ROLES = {
    "index.html": ["demo"],
    "demo.html": ["demo"],
    "self-check.html": ["crew", "demo"],
    "captain.html": ["captain", "demo"],
    "doctor.html": ["doctor", "demo"],
    "ground.html": ["ground", "demo"],
    "stream-check.html": ["ground", "demo"],
    "history.html": ["crew", "captain", "doctor", "ground", "demo"],
  };

  const KEY = "ahm-session";
  const TTL_MS = 12 * 3600 * 1000;   // stay signed in for 12 h

  // localStorage so the session covers every tab and both panes of demo.html.
  // Falls back to sessionStorage; if neither works the gate lets everyone in as
  // the presenter rather than trapping them in a redirect loop.
  const store = (() => {
    for (const s of [() => window.localStorage, () => window.sessionStorage]) {
      try { const st = s(); st.setItem("ahm-probe", "1"); st.removeItem("ahm-probe"); return st; } catch { /* next */ }
    }
    return null;
  })();

  function session() {
    if (!store) return { user: "demo", ...ACCOUNTS.demo, at: Date.now() };
    try {
      const s = JSON.parse(store.getItem(KEY) || "null");
      // Sessions from before roles existed have no role: sign in again.
      if (s && s.role && ACCOUNTS[s.user] && Date.now() - s.at < TTL_MS) return { ...s, ...ACCOUNTS[s.user], password: undefined };
    } catch { /* treat as signed out */ }
    return null;
  }

  // Returns the account on success, null on a wrong username or password.
  function login(user, password) {
    const name = user.trim().toLowerCase();
    const acc = ACCOUNTS[name];
    if (!acc || password !== acc.password) return null;
    if (store) store.setItem(KEY, JSON.stringify({ user: name, role: acc.role, at: Date.now() }));
    return { user: name, ...acc, password: undefined };
  }

  function logout() {
    if (store) store.removeItem(KEY);
    location.href = "login.html";
  }

  const pageOf = href => (href || "").split(/[?#]/)[0] || "index.html";
  function canOpen(href, s = session()) {
    const roles = PAGE_ROLES[pageOf(href)];
    return !!s && (!roles || roles.includes(s.role));
  }

  // Only same-folder page names are accepted as a redirect target.
  function safeNext(next) {
    return /^[a-z][a-z-]*\.html([?#].*)?$/.test(next || "") ? next : null;
  }

  window.AHMAuth = { session, login, logout, canOpen, safeNext, ACCOUNTS };

  // Hide the app menus when a page is shown inside demo.html.
  if (window.top !== window.self) document.documentElement.classList.add("embedded");

  const page = location.pathname.split("/").pop() || "index.html";

  // ---- bigger interface on big windows (owner's call, 2026-11-14) ----------
  // Pages are laid out for 1280 x 720. On a bigger window the whole page is
  // zoomed by the same factor (capped at 1.75) so it fills the window; the
  // effective layout never drops below 1280 x 720, so breakpoints and the
  // full-height tabs behave as they do there. Zoom also scales vh, so
  // style.css divides window heights by --z. Not on the presenter page or
  // demo.html, which size themselves. Runs here, in <head>, to avoid a jump.
  if (page !== "index.html" && page !== "demo.html") {
    const applyZoom = () => {
      const z = Math.round(Math.max(1, Math.min(innerWidth / 1280, innerHeight / 720, 1.75)) * 100) / 100;
      document.documentElement.style.zoom = z === 1 ? "" : String(z);
      document.documentElement.style.setProperty("--z", String(z));
      window.AHM_ZOOM = z;
      // Charts: the canvas is pinned to its box in style.css, so only the text
      // needs the zoom (Chart.js draws in the zoomed pixels it measures).
      if (window.Chart) {
        window.Chart.defaults.font.family = '"Archivo", system-ui, sans-serif';
        window.Chart.defaults.font.size = Math.round(12 * z);
      }
    };
    applyZoom();
    addEventListener("resize", applyZoom);
    addEventListener("DOMContentLoaded", applyZoom);   // Chart.js may load after this script
  }

  // ---- the console follows the module's lighting (style.css, html[data-light]) ----
  // self-check.js sets the mode from GET /circadian; here we only restore the
  // last known mode on console pages (no silver flash in Pre-sleep), or take
  // ?light=pre_sleep for a demo on any page.
  {
    const consolePage = ["self-check.html", "captain.html", "doctor.html"].includes(page);
    let light = new URLSearchParams(location.search).get("light");
    if (!light && consolePage) { try { light = sessionStorage.getItem("ahm-light"); } catch { /* none */ } }
    if (light) document.documentElement.dataset.light = light;
  }

  if (page === "login.html") return;
  const s = session();
  if (!s) {
    location.replace("login.html?next=" + encodeURIComponent(page + location.search + location.hash));
  } else if (!canOpen(page, s)) {
    location.replace(s.home + location.search);   // wrong role: go to your own interface
  }
})();
