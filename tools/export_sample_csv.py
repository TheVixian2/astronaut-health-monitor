"""Write each astronaut's sample CSV for the "Sample CSV" button from the seeded crew.

One row per day for 14 days after space adaptation (mission days 7-20), in the same columns as
web/sample-baseline.csv, so the personal-baseline upload reads it as it is. Values come from the
stored readings (sensor errors left out): resting heart rate and HRV from the night (before 05:00),
SpO2, temperature and breathing as daily averages, sleep as logged, mood from the latest check-in,
active minutes as the day's total.

Run after seeding, from the repo root:
    backend/.venv/Scripts/python tools/simulate_crew.py --reset-db --seed-baseline
    backend/.venv/Scripts/python tools/export_sample_csv.py [--out web]
"""

import argparse
import sqlite3
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
import engine  # noqa: E402
import store   # noqa: E402

FIRST_DAY, DAYS = 7, 14
HEADER = "date,resting_heart_rate,hrv_sdnn,spo2,temperature_c,resp_rate,sleep_hours,mood,active_minutes"


def rows_for(con: sqlite3.Connection, aid: str, mission_start: date) -> list[str]:
    out = []
    for i in range(DAYS):
        d = mission_start + timedelta(days=FIRST_DAY - 1 + i)
        lo, hi = f"{d.isoformat()}T00:00:00Z", f"{(d + timedelta(days=1)).isoformat()}T00:00:00Z"
        night = con.execute(
            "SELECT AVG(heart_rate_bpm), AVG(hrv_sdnn_ms) FROM samples WHERE astronaut_id = ? AND ts >= ? AND ts < ? "
            "AND substr(ts, 12, 2) < '05' AND quality = 'ok'", (aid, lo, hi)).fetchone()
        day = con.execute(
            "SELECT AVG(spo2_pct), AVG(temp_c), AVG(resp_rate_bpm), AVG(sleep_h_last_night), MAX(active_min) "
            "FROM samples WHERE astronaut_id = ? AND ts >= ? AND ts < ? AND quality = 'ok'", (aid, lo, hi)).fetchone()
        if None in night or None in day:
            continue
        mood = next((p["mood_1to5"] for ts, p in reversed(store.checkins_between(aid, "")) if ts < hi
                     and p.get("mood_1to5") is not None), engine.CREW[aid][2]["mood_1to5"])
        out.append(f"{d.isoformat()},{night[0]:.0f},{night[1]:.0f},{day[0]:.0f},{day[1]:.1f},{day[2]:.0f},"
                   f"{day[3]:.1f},{mood},{day[4]:.0f}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default="web", help="folder for sample-baseline-<id>.csv (default: web)")
    out = Path(ap.parse_args().out)
    start_iso = store.meta_get("mission_start")
    if not start_iso:
        sys.exit("No seeded mission found: run tools/simulate_crew.py --reset-db --seed-baseline first.")
    mission_start = datetime.fromisoformat(start_iso.replace("Z", "+00:00")).date()
    con = sqlite3.connect(store.DB_PATH)
    for aid, (name, role, _) in engine.CREW.items():
        rows = rows_for(con, aid, mission_start)
        text = "\n".join([
            '# Written with AI assistance (Claude Code, Anthropic) and reviewed by the team. See README "Use of AI".',
            f"# DEMO DATA, simulated: {name} ({role}), mission days {FIRST_DAY}-{FIRST_DAY + DAYS - 1}, one row per day, "
            "as a watch export might look. Made by tools/export_sample_csv.py from the seeded crew.",
            HEADER, *rows]) + "\n"
        path = out / f"sample-baseline-{aid}.csv"
        path.write_text(text, encoding="utf-8")
        print(f"{path}: {len(rows)} days")
    con.close()


if __name__ == "__main__":
    main()
