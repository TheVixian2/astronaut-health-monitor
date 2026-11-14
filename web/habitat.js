// Commander, "Habitat" tab: a concept layout of the habitat with a live dot per
// crew member (GET /crew/locations, every 5 s) and, per person, time in shared
// rooms vs their own normal (GET /astronauts/{id}/rooms, every 60 s).
(function () {
  const A = window.AHM;
  const cfg = A.settings();
  const $ = id => document.getElementById(id);
  const viewer = "a1"; // the Commander (backend COMMANDER_ID)

  // Concept layout, viewBox 1000 x 300: [x, y, w, h].
  const LAYOUT = {
    command:  [20, 40, 170, 220],
    lab:      [200, 40, 200, 220],
    galley:   [410, 40, 230, 220],
    exercise: [650, 40, 150, 105],
    hygiene:  [650, 155, 150, 105],
    q_a1:     [810, 40, 170, 49],
    q_a2:     [810, 97, 170, 49],
    q_a3:     [810, 154, 170, 49],
    q_a4:     [810, 211, 170, 49],
  };
  const COLORS = { a1: "#f5c542", a2: "#f05a78", a3: "#3ccf8e", a4: "#6fb3ff" };
  let rooms = [], crewNames = {};

  const initials = name => name.replace(/^(Cmdr\.|Dr\.)\s*/, "").split(" ").map(p => p[0]).join("").slice(0, 2);

  function drawMap(locs) {
    const fill = { shared: "#1d2a3a", private: "#2a2140", untracked: "#222" };
    let svg = `<rect x="8" y="28" width="984" height="244" rx="40" fill="none" stroke="#ffffff33" stroke-width="2"/>`;
    for (const r of rooms) {
      const [x, y, w, h] = LAYOUT[r.id] || [];
      if (x == null) continue;
      svg += `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="8" fill="${fill[r.kind]}" stroke="#ffffff26"
        ${r.kind === "untracked" ? 'stroke-dasharray="6 4"' : ""}/>
        <text x="${x + 8}" y="${y + 16}" fill="#9aa4b2" font-size="12">${A.esc(r.name)}</text>`;
    }
    const perRoom = {};
    for (const l of locs) if (l.room) (perRoom[l.room] = perRoom[l.room] || []).push(l);
    for (const [room, people] of Object.entries(perRoom)) {
      const [x, y, w, h] = LAYOUT[room];
      people.forEach((l, i) => {
        const cx = x + w / 2 + (i - (people.length - 1) / 2) * 34, cy = y + h / 2 + (h > 60 ? 8 : 4);
        svg += `<g><title>${A.esc(l.name)} · ${A.esc(l.room_name)} since ${new Date(l.since).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</title>
          <circle cx="${cx}" cy="${cy}" r="15" fill="${COLORS[l.astronaut_id] || "#ccc"}"/>
          <text x="${cx}" y="${cy + 4}" text-anchor="middle" font-size="11" font-weight="700" fill="#111">${A.esc(initials(l.name))}</text></g>`;
      });
    }
    $("habMap").innerHTML = svg;
    const away = locs.filter(l => !l.room).map(l => l.name);
    $("habUntracked").textContent = away.length ? `Not tracked right now (hygiene module): ${away.join(", ")}.` : "";
  }

  function roomCard(aid, t) {
    const name = crewNames[aid] || aid;
    const d = t.shared_normal_h ? ((t.shared_7d_avg_h - t.shared_normal_h) / t.shared_normal_h) * 100 : 0;
    const low = d <= -15;
    const bar = (v, max, color) => `<div style="height:8px;border-radius:4px;background:#ffffff14"><div style="height:8px;border-radius:4px;width:${Math.min(100, (v / max) * 100)}%;background:${color}"></div></div>`;
    return `<article class="card cap-panel st-${low ? "watch" : "nominal"}">
      <div class="cc-head"><div><strong>${A.esc(name)}</strong><div class="muted small">Shared rooms (galley, lab, command, exercise)</div></div>
        <span class="st-pill">${low ? "less social" : "usual"}</span></div>
      <p class="small">Last 7 days: <strong>${t.shared_7d_avg_h} h/day</strong> vs normal ${t.shared_normal_h} h
        <span class="${low ? "warn" : "muted"}">(${d > 0 ? "+" : ""}${d.toFixed(0)}%)</span></p>
      ${bar(t.shared_7d_avg_h, 24, COLORS[aid])}
      <p class="small" style="margin-top:8px">Today so far: ${t.shared_h} h shared · ${t.private_h} h private
        <span class="muted">(normal by now: ${t.shared_so_far_normal_h} h shared)</span></p>
    </article>`;
  }

  async function refreshLocations() {
    try {
      drawMap(await A.getJSON(cfg.base, `/crew/locations?viewer=${viewer}`, cfg.mock));
      $("habConn").textContent = "live"; $("habConn").className = "pill pill-on";
    } catch {
      $("habConn").textContent = "offline"; $("habConn").className = "pill pill-off";
    }
  }

  async function refreshRooms() {
    const ids = Object.keys(crewNames);
    const cards = await Promise.all(ids.map(async aid => {
      try { return roomCard(aid, await A.getJSON(cfg.base, `/astronauts/${aid}/rooms?viewer=${viewer}`, cfg.mock)); }
      catch { return ""; }
    }));
    $("habRooms").innerHTML = cards.join("");
  }

  (async function init() {
    try {
      rooms = await A.getJSON(cfg.base, "/habitat", cfg.mock);
      for (const c of await A.getJSON(cfg.base, "/crew", cfg.mock)) crewNames[c.id] = c.name;
    } catch {
      $("habConn").textContent = "offline"; $("habConn").className = "pill pill-off";
      return;
    }
    refreshLocations(); refreshRooms();
    setInterval(refreshLocations, 5000);
    setInterval(refreshRooms, 60000);
  })();
})();
