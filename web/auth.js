// Login gate for every page. Load it in <head>, before anything else, so a
// signed-out visitor is redirected before the page draws.
//
// NOT SECURITY. This is a placeholder for the hackathon demo: one universal
// account checked in the browser. Anyone can read these credentials here, and
// the backend itself has no auth (docs/api-spec.md: "Auth: none"). Real login
// would need the backend; ask Luca before relying on this for anything.

(function () {
  // The universal account. Change both lines to change the login.
  const USER = "crew";
  const PASSWORD = "mars2026";

  const KEY = "ahm-session";
  const TTL_MS = 12 * 3600 * 1000;   // stay signed in for 12 h

  // localStorage so the session covers every tab and both panes of demo.html.
  // Falls back to sessionStorage; if neither works, the gate is skipped rather
  // than trapping the presenter in a redirect loop.
  const store = (() => {
    for (const s of [() => window.localStorage, () => window.sessionStorage]) {
      try { const st = s(); st.setItem("ahm-probe", "1"); st.removeItem("ahm-probe"); return st; } catch { /* next */ }
    }
    return null;
  })();

  function session() {
    if (!store) return { user: USER, at: Date.now() };
    try {
      const s = JSON.parse(store.getItem(KEY) || "null");
      if (s && Date.now() - s.at < TTL_MS) return s;
    } catch { /* treat as signed out */ }
    return null;
  }

  function login(user, password) {
    if (user.trim().toLowerCase() !== USER || password !== PASSWORD) return false;
    if (store) store.setItem(KEY, JSON.stringify({ user: USER, at: Date.now() }));
    return true;
  }

  function logout() {
    if (store) store.removeItem(KEY);
    location.href = "login.html";
  }

  // Only same-folder page names are accepted as a redirect target.
  function safeNext(next) {
    return /^[a-z][a-z-]*\.html([?#].*)?$/.test(next || "") ? next : "index.html";
  }

  window.AHMAuth = { session, login, logout, safeNext };

  // Hide the app menus when a page is shown inside demo.html.
  if (window.top !== window.self) document.documentElement.classList.add("embedded");

  const page = location.pathname.split("/").pop() || "index.html";
  if (page !== "login.html" && !session()) {
    location.replace("login.html?next=" + encodeURIComponent(page + location.search + location.hash));
  }
})();
