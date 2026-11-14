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
    // Colours come from style.css (.hab-*), so the map follows the light theme.
    let svg = `<rect class="hab-hull" x="8" y="28" width="984" height="244" rx="40"/>`;
    for (const r of rooms) {
      const [x, y, w, h] = LAYOUT[r.id] || [];
      if (x == null) continue;
      svg += `<rect class="hab-room ${A.esc(r.kind)}" x="${x}" y="${y}" width="${w}" height="${h}" rx="6"/>
        <text class="hab-label" x="${x + 8}" y="${y + 17}">${A.esc(r.name)}</text>`;
    }
    const perRoom = {};
    for (const l of locs) if (l.room) (perRoom[l.room] = perRoom[l.room] || []).push(l);
    for (const [room, people] of Object.entries(perRoom)) {
      const [x, y, w, h] = LAYOUT[room];
      people.forEach((l, i) => {
        const cx = x + w / 2 + (i - (people.length - 1) / 2) * 34, cy = y + h / 2 + (h > 60 ? 8 : 4);
        svg += `<g><title>${A.esc(l.name)} in ${A.esc(l.room_name)} since ${new Date(l.since).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</title>
          <circle cx="${cx}" cy="${cy}" r="15" fill="${COLORS[l.astronaut_id] || "#ccc"}"/>
          <text class="hab-dot-label" x="${cx}" y="${cy + 4}" text-anchor="middle">${A.esc(initials(l.name))}</text></g>`;
      });
    }
    $("habMap").innerHTML = svg;
    const away = locs.filter(l => !l.room).map(l => l.name);
    $("habUntracked").textContent = away.length ? `Not tracked right now (hygiene module): ${away.join(", ")}.` : "";
  }

  // One tall card per crew member (styles: "Habitat tab" in style.css): the
  // 7-day average as a big number, a bar out of 24 h with a marker at their
  // normal, and today so far as a small table.
  function roomCard(aid, t) {
    const name = crewNames[aid] || aid;
    const d = t.shared_normal_h ? ((t.shared_7d_avg_h - t.shared_normal_h) / t.shared_normal_h) * 100 : 0;
    const low = d <= -15;
    const pct = h => `${Math.min(100, Math.max(0, (h / 24) * 100)).toFixed(1)}%`;
    return `<article class="card cap-panel hab-card st-${low ? "watch" : "nominal"}">
      <div class="cc-head"><div><strong>${A.esc(name)}</strong><div class="muted small">Shared rooms (galley, lab, command, exercise)</div></div>
        <span class="st-pill">${low ? "less social" : "usual"}</span></div>
      <div>
        <div class="hab-stat"><span class="hab-big">${t.shared_7d_avg_h}</span> h/day <span class="muted small">shared, last 7 days</span></div>
        <div class="small">normal ${t.shared_normal_h} h <span class="hab-delta ${low ? "low" : "muted"}">${d > 0 ? "+" : ""}${d.toFixed(0)}%</span></div>
      </div>
      <div class="hab-bar" title="Out of 24 h. The marker is their normal.">
        <div class="hab-fill" style="width:${pct(t.shared_7d_avg_h)};background:${COLORS[aid] || "var(--accent)"}"></div>
        <div class="hab-normal" style="left:${pct(t.shared_normal_h)}"></div>
      </div>
      <table class="hab-today">
        <caption class="muted small">Today so far</caption>
        <tr><th>Shared rooms</th><td class="num">${t.shared_h} h</td></tr>
        <tr><th>Private</th><td class="num">${t.private_h} h</td></tr>
        <tr><th>Normal by now (shared)</th><td class="num muted">${t.shared_so_far_normal_h} h</td></tr>
      </table>
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
