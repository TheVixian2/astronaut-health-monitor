"""SQLite persistence: samples, alerts and check-ins survive restarts.

All live writes go through one background thread, so a slow disk never blocks a
request or the tick loop. Reads open their own short-lived connection; WAL mode
lets them run alongside the writer. File: backend/data/ahm.db (gitignored).
Wipe and re-seed with:  python ../tools/simulate_crew.py --reset-db --seed-baseline
"""

import json
import logging
import os
import queue
import sqlite3
import statistics
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger("store")

DB_PATH = Path(os.getenv("AHM_DB") or Path(__file__).with_name("data") / "ahm.db")

VITAL_FIELDS = ("heart_rate_bpm", "spo2_pct", "temp_c",
                "resp_rate_bpm", "sleep_h_last_night", "mood_1to5")
MIN_BASELINE_SAMPLES = 50

SCHEMA = """
CREATE TABLE IF NOT EXISTS samples (            -- one row per tick, per astronaut
  astronaut_id TEXT NOT NULL,
  ts           TEXT NOT NULL,                   -- ISO 8601 UTC, YYYY-MM-DDTHH:MM:SSZ
  heart_rate_bpm REAL,
  spo2_pct REAL, temp_c REAL, resp_rate_bpm REAL,
  sleep_h_last_night REAL, mood_1to5 INTEGER,
  source       TEXT NOT NULL,                   -- 'real' | 'simulated'
  quality      TEXT NOT NULL DEFAULT 'ok',      -- ok | suspect | implausible | artifact (quality.py)
  PRIMARY KEY (astronaut_id, ts)
);
CREATE INDEX IF NOT EXISTS idx_samples_recent ON samples (astronaut_id, ts DESC);

CREATE TABLE IF NOT EXISTS alerts (             -- so an alert survives a restart
  id TEXT PRIMARY KEY, astronaut_id TEXT NOT NULL, profile TEXT NOT NULL,
  severity TEXT NOT NULL, started_at TEXT NOT NULL, cleared_at TEXT,
  alert_json TEXT NOT NULL,
  insight_json TEXT                             -- cached: never explain the same alert twice
);

CREATE TABLE IF NOT EXISTS checkins (           -- mood, PHQ-2, reaction tests = the wellbeing trend
  astronaut_id TEXT NOT NULL, ts TEXT NOT NULL, payload_json TEXT NOT NULL,
  PRIMARY KEY (astronaut_id, ts)
);

CREATE TABLE IF NOT EXISTS notices (            -- behavioral health: who was told what, and why
  id TEXT PRIMARY KEY, astronaut_id TEXT NOT NULL, target TEXT NOT NULL,
  created_at TEXT NOT NULL, notice_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def iso(t: datetime) -> str:
    return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=10000")
    return con


@contextmanager
def _db():
    con = connect()
    try:
        with con:  # commits on success, rolls back on error
            yield con
    finally:
        con.close()


SAMPLE_COLUMNS = ("astronaut_id", "ts", *VITAL_FIELDS, "source")
_INSERT_SAMPLE = (f"INSERT OR REPLACE INTO samples ({', '.join(SAMPLE_COLUMNS)}, quality) "
                  f"VALUES ({', '.join('?' * (len(SAMPLE_COLUMNS) + 1))})")
USABLE = "quality IN ('ok', 'suspect')"  # what charts and reports show; the baseline uses only 'ok'


def init() -> None:
    with _db() as con:
        con.executescript(SCHEMA)
        columns = {row[1] for row in con.execute("PRAGMA table_info(samples)")}
        if "quality" not in columns:  # database created before sensor-quality flags existed
            con.execute("ALTER TABLE samples ADD COLUMN quality TEXT NOT NULL DEFAULT 'ok'")


# --- Background writer -------------------------------------------------------

class _Writer(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True, name="db-writer")
        self.q: queue.Queue = queue.Queue(maxsize=20000)
        self._stopping = threading.Event()

    def run(self) -> None:
        con = connect()
        while not (self._stopping.is_set() and self.q.empty()):
            try:
                batch = [self.q.get(timeout=0.5)]
            except queue.Empty:
                continue
            while len(batch) < 1000:
                try:
                    batch.append(self.q.get_nowait())
                except queue.Empty:
                    break
            try:
                with con:
                    for sql, params in batch:
                        con.execute(sql, params)
            except sqlite3.Error:
                log.exception("DB write failed; %d statements dropped", len(batch))
        con.close()

    def stop(self) -> None:
        self._stopping.set()
        self.join(timeout=5)


_writer: Optional[_Writer] = None


def start_writer() -> None:
    global _writer
    _writer = _Writer()
    _writer.start()


def stop_writer() -> None:
    if _writer:
        _writer.stop()


def _write(sql: str, params: tuple) -> None:
    try:
        _writer.q.put_nowait((sql, params))
    except queue.Full:
        log.warning("DB write queue full; dropping a write")


def add_sample(aid: str, ts: str, vitals: dict, source: str, quality: str = "ok") -> None:
    _write(_INSERT_SAMPLE, (aid, ts, *[vitals[f] for f in VITAL_FIELDS], source, quality))


def mark_artifact(aid: str, start: str, end: str) -> None:
    """The astronaut didn't feel it: flag the readings as a likely sensor error (never delete)."""
    _write("UPDATE samples SET quality = 'artifact' WHERE astronaut_id = ? AND ts >= ? AND ts <= ? "
           "AND quality != 'implausible'", (aid, start, end))


def update_alert(alert: dict) -> None:
    _write("UPDATE alerts SET alert_json = ? WHERE id = ?", (json.dumps(alert), alert["id"]))


def meta_set_async(key: str, value: str) -> None:
    _write("INSERT OR REPLACE INTO meta VALUES (?, ?)", (key, value))


def save_notice(notice: dict) -> None:
    _write("INSERT OR REPLACE INTO notices VALUES (?,?,?,?,?)",
           (notice["id"], notice["astronaut_id"], notice["target"], notice["created_at"], json.dumps(notice)))


def load_notices() -> list[dict]:
    with _db() as con:
        rows = con.execute("SELECT notice_json FROM notices ORDER BY created_at").fetchall()
    return [json.loads(r[0]) for r in rows]


def save_alert(alert: dict) -> None:
    _write("INSERT OR REPLACE INTO alerts VALUES (?,?,?,?,?,NULL,?,?)",
           (alert["id"], alert["astronaut_id"], alert["profile"], alert["severity"],
            alert["started_at"], json.dumps(alert),
            json.dumps(alert["insight"]) if alert.get("insight") else None))


def set_insight(alert: dict) -> None:
    _write("UPDATE alerts SET insight_json = ?, alert_json = ? WHERE id = ?",
           (json.dumps(alert["insight"]), json.dumps(alert), alert["id"]))


def clear_alert(alert_id: str, ts: str) -> None:
    _write("UPDATE alerts SET cleared_at = ? WHERE id = ?", (ts, alert_id))


# --- Synchronous reads and rare writes (call via asyncio.to_thread) ----------

def add_checkin(aid: str, ts: str, payload: dict) -> None:
    with _db() as con:
        con.execute("INSERT OR REPLACE INTO checkins VALUES (?,?,?)", (aid, ts, json.dumps(payload)))


def load_alerts() -> list[tuple[dict, Optional[str]]]:
    """All stored alerts, oldest first, as (alert dict with cached insight, cleared_at)."""
    with _db() as con:
        rows = con.execute(
            "SELECT alert_json, insight_json, cleared_at FROM alerts ORDER BY started_at").fetchall()
    out = []
    for alert_json, insight_json, cleared_at in rows:
        alert = json.loads(alert_json)
        if insight_json:
            alert["insight"] = json.loads(insight_json)
        out.append((alert, cleared_at))
    return out


def baseline(aid: str, start: str, end: str) -> Optional[dict]:
    """Median of each vital over [start, end), or None if there is too little stored data."""
    with _db() as con:
        rows = con.execute(
            f"SELECT {', '.join(VITAL_FIELDS)} FROM samples "
            "WHERE astronaut_id = ? AND ts >= ? AND ts < ? AND quality = 'ok'", (aid, start, end)).fetchall()
    if len(rows) < MIN_BASELINE_SAMPLES:
        return None
    cols = list(zip(*rows))
    return {f: statistics.median(v for v in col if v is not None) for f, col in zip(VITAL_FIELDS, cols)}


def checkins_between(aid: str, start: str, end: Optional[str] = None) -> list[tuple[str, dict]]:
    sql = "SELECT ts, payload_json FROM checkins WHERE astronaut_id = ? AND ts >= ?"
    params: tuple = (aid, start)
    if end:
        sql += " AND ts < ?"
        params += (end,)
    with _db() as con:
        rows = con.execute(sql + " ORDER BY ts", params).fetchall()
    return [(ts, json.loads(p)) for ts, p in rows]


def history(aid: str, since: str, bucket_s: int) -> list[dict]:
    """Vitals per time bucket (average, low, high), oldest first, for charts. Sensor errors are left out."""
    avgs = ", ".join(f"AVG({f}), MIN({f}), MAX({f})" for f in VITAL_FIELDS)
    with _db() as con:
        rows = con.execute(
            f"SELECT (CAST(strftime('%s', ts) AS INTEGER) / ?) * ? AS b, {avgs} "
            f"FROM samples WHERE astronaut_id = ? AND ts >= ? AND {USABLE} GROUP BY b ORDER BY b",
            (bucket_s, bucket_s, aid, since)).fetchall()
    out = []
    for b, *vals in rows:
        point = {"ts": iso(datetime.fromtimestamp(b, timezone.utc))}
        r = [round(v, 1) if v is not None else None for v in vals]
        point.update({f: r[3 * i] for i, f in enumerate(VITAL_FIELDS)})
        point["low"] = {f: r[3 * i + 1] for i, f in enumerate(VITAL_FIELDS)}
        point["high"] = {f: r[3 * i + 2] for i, f in enumerate(VITAL_FIELDS)}
        out.append(point)
    return out


def quality_counts(aid: str, since: str) -> dict[str, int]:
    with _db() as con:
        rows = con.execute("SELECT quality, COUNT(*) FROM samples WHERE astronaut_id = ? AND ts >= ? "
                           "GROUP BY quality", (aid, since)).fetchall()
    return dict(rows)


def period_stats(aid: str, since: str) -> dict[str, dict]:
    """Average, min and max of each vital since `since`, sensor errors excluded."""
    cols = ", ".join(f"AVG({f}), MIN({f}), MAX({f})" for f in VITAL_FIELDS)
    with _db() as con:
        row = con.execute(f"SELECT {cols} FROM samples WHERE astronaut_id = ? AND ts >= ? AND {USABLE}",
                          (aid, since)).fetchone()
    return {f: dict(avg=row[3 * i], min=row[3 * i + 1], max=row[3 * i + 2]) for i, f in enumerate(VITAL_FIELDS)}


def delete_checkins_after(aid: str, ts: str) -> None:
    with _db() as con:
        con.execute("DELETE FROM checkins WHERE astronaut_id = ? AND ts > ?", (aid, ts))


def meta_get(key: str) -> Optional[str]:
    with _db() as con:
        row = con.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None


def meta_set(key: str, value: str) -> None:
    with _db() as con:
        con.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (key, value))


def insert_samples(rows: list[tuple]) -> None:
    """Rows in SAMPLE_COLUMNS order; quality defaults to 'ok'."""
    with _db() as con:
        con.executemany(_INSERT_SAMPLE, [(*r, "ok") for r in rows])


def insert_checkins(rows: list[tuple[str, str, dict]]) -> None:
    with _db() as con:
        con.executemany("INSERT OR REPLACE INTO checkins VALUES (?,?,?)",
                        [(aid, ts, json.dumps(p)) for aid, ts, p in rows])


def reset() -> None:
    with _db() as con:
        for table in ("samples", "alerts", "checkins", "notices", "meta"):
            con.execute(f"DELETE FROM {table}")
