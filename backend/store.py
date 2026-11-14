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

VITAL_FIELDS = ("heart_rate_bpm", "systolic_mmhg", "diastolic_mmhg", "spo2_pct", "temp_c",
                "resp_rate_bpm", "sleep_h_last_night", "mood_1to5")
MIN_BASELINE_SAMPLES = 50

SCHEMA = """
CREATE TABLE IF NOT EXISTS samples (            -- one row per tick, per astronaut
  astronaut_id TEXT NOT NULL,
  ts           TEXT NOT NULL,                   -- ISO 8601 UTC, YYYY-MM-DDTHH:MM:SSZ
  heart_rate_bpm REAL, systolic_mmhg REAL, diastolic_mmhg REAL,
  spo2_pct REAL, temp_c REAL, resp_rate_bpm REAL,
  sleep_h_last_night REAL, mood_1to5 INTEGER,
  cabin_co2_mmhg REAL,                          -- the astronaut's module; feeds co2 and sans
  source       TEXT NOT NULL,                   -- 'real' | 'simulated'
  PRIMARY KEY (astronaut_id, ts)
);
CREATE INDEX IF NOT EXISTS idx_samples_recent ON samples (astronaut_id, ts DESC);

CREATE TABLE IF NOT EXISTS alerts (             -- so an alert survives a restart
  id TEXT PRIMARY KEY, astronaut_id TEXT NOT NULL, profile TEXT NOT NULL,
  severity TEXT NOT NULL, started_at TEXT NOT NULL, cleared_at TEXT,
  alert_json TEXT NOT NULL,
  insight_json TEXT                             -- cached: never explain the same alert twice
);

CREATE TABLE IF NOT EXISTS checkins (           -- vision + mood history = the SANS trend
  astronaut_id TEXT NOT NULL, ts TEXT NOT NULL, payload_json TEXT NOT NULL,
  PRIMARY KEY (astronaut_id, ts)
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


def init() -> None:
    with _db() as con:
        con.executescript(SCHEMA)


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


def add_sample(aid: str, ts: str, vitals: dict, cabin_co2: float, source: str) -> None:
    _write("INSERT OR REPLACE INTO samples VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
           (aid, ts, *[vitals[f] for f in VITAL_FIELDS], cabin_co2, source))


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
            "WHERE astronaut_id = ? AND ts >= ? AND ts < ?", (aid, start, end)).fetchall()
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


def co2_avg(aid: str, since: str) -> Optional[float]:
    with _db() as con:
        (avg,) = con.execute("SELECT AVG(cabin_co2_mmhg) FROM samples WHERE astronaut_id = ? AND ts >= ?",
                             (aid, since)).fetchone()
    return avg


def history(aid: str, since: str, bucket_s: int) -> list[dict]:
    """Vitals averaged into time buckets, oldest first, for charts."""
    avgs = ", ".join(f"AVG({f}) AS {f}" for f in VITAL_FIELDS)
    with _db() as con:
        rows = con.execute(
            f"SELECT (CAST(strftime('%s', ts) AS INTEGER) / ?) * ? AS b, {avgs}, AVG(cabin_co2_mmhg) "
            "FROM samples WHERE astronaut_id = ? AND ts >= ? GROUP BY b ORDER BY b",
            (bucket_s, bucket_s, aid, since)).fetchall()
    out = []
    for b, *vals in rows:
        point = {"ts": iso(datetime.fromtimestamp(b, timezone.utc))}
        point.update({f: (round(v, 1) if v is not None else None) for f, v in zip(VITAL_FIELDS, vals[:-1])})
        point["cabin_co2_mmhg"] = round(vals[-1], 2) if vals[-1] is not None else None
        out.append(point)
    return out


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
    with _db() as con:
        con.executemany("INSERT OR REPLACE INTO samples VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)


def insert_checkins(rows: list[tuple[str, str, dict]]) -> None:
    with _db() as con:
        con.executemany("INSERT OR REPLACE INTO checkins VALUES (?,?,?)",
                        [(aid, ts, json.dumps(p)) for aid, ts, p in rows])


def reset() -> None:
    with _db() as con:
        for table in ("samples", "alerts", "checkins", "meta"):
            con.execute(f"DELETE FROM {table}")
