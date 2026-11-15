// Written with AI assistance (Claude Code, Anthropic) and reviewed by the team. See README "Use of AI".
// PROVISIONAL (preview branch csv-baseline): a personal baseline from a CSV of
// past readings (e.g. pre-flight data exported from the astronaut's own watch).
// The file is parsed here and only the median of each column is sent
// (PUT /astronauts/{id}/baseline), so live and mock mode share one parser.
// Ideas from our AirHack 2026 loader: guess the delimiter, trim and lower-case
// headers, match columns by keyword, drop cells that aren't numbers, and say
// which columns were found when nothing matches.
(function () {
  const MAX_BYTES = 2 * 1024 * 1024;
  const MIN_ROWS = 7;
  // field -> header keywords (first match wins; order matters: "resp" before "rate", "hrv" before "heart")
  const COLUMNS = [
    ["hrv_sdnn_ms", ["hrv", "sdnn", "variability"]],
    ["resp_rate_bpm", ["resp", "breath"]],
    ["spo2_pct", ["spo2", "oxygen", "saturation"]],
    ["heart_rate_bpm", ["heart", "hr", "bpm", "pulse"]],
    ["temp_c", ["temp"]],
    ["sleep_h_last_night", ["sleep"]],
    ["mood_1to5", ["mood"]],
    ["active_min", ["active", "exercise", "activity"]],
  ];

  function splitter(line) {
    const counts = [",", ";", "\t"].map(d => [d, line.split(d).length]);
    return counts.sort((a, b) => b[1] - a[1])[0][0];
  }
  const median = xs => {
    const s = [...xs].sort((a, b) => a - b), m = s.length >> 1;
    return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
  };

  // -> { values: {field: median}, rows, columns: {field: header}, unmatched: [headers] }; throws Error with a plain message.
  function parseBaselineCsv(text, size) {
    if (size > MAX_BYTES) throw new Error("File is over 2 MB.");
    const lines = text.split(/\r?\n/).map(l => l.trim()).filter(l => l && !l.startsWith("#"));
    if (lines.length < 2) throw new Error("No data rows found.");
    const sep = splitter(lines[0]);
    const headers = lines[0].split(sep).map(h => h.trim().replace(/^"|"$/g, "").toLowerCase());
    const columns = {}, used = new Set();
    for (const [field, keys] of COLUMNS) {
      const i = headers.findIndex((h, j) => !used.has(j) && keys.some(k => h.includes(k)));
      if (i >= 0) { columns[field] = i; used.add(i); }
    }
    if (!Object.keys(columns).length) {
      throw new Error(`No vitals columns recognised. Columns in your CSV: ${headers.join(", ")}. ` +
        "Need at least one of: heart rate, HRV, SpO2, temperature, resp rate, sleep, mood, active minutes.");
    }
    const rows = lines.slice(1).map(l => l.split(sep));
    const values = {};
    for (const [field, i] of Object.entries(columns)) {
      const xs = rows.map(r => parseFloat(String(r[i] ?? "").replace(",", "."))).filter(Number.isFinite);
      if (xs.length >= MIN_ROWS) values[field] = Math.round(median(xs) * 10) / 10;
    }
    if (!Object.keys(values).length) throw new Error(`Need at least ${MIN_ROWS} rows with numbers.`);
    return {
      values, rows: rows.length,
      columns: Object.fromEntries(Object.entries(columns).map(([f, i]) => [f, headers[i]])),
      unmatched: headers.filter((_, j) => !used.has(j)),
    };
  }

  window.AHMBaselineUpload = { parseBaselineCsv, MIN_ROWS };
})();
