# Written with AI assistance (Claude Code, Anthropic) and reviewed by the team. See README "Use of AI".
"""Crew simulator and demo seeding for the backend.

Run with the backend's virtual environment, from the repo root:

  Windows:  backend\\.venv\\Scripts\\python tools\\simulate_crew.py --reset-db --seed-baseline
  macOS:    backend/.venv/bin/python tools/simulate_crew.py --reset-db --seed-baseline

  --reset-db        wipe backend/data/ahm.db (samples, alerts, check-ins)
  --seed-baseline   write six weeks of mission history, so the personal baseline
                    (mission days 7-14) is a real SELECT the moment the server
                    starts. Includes HRV, activity and room stays (beacons).
                    a2 declines slowly after the midpoint (HRV, activity, time
                    with crew, mood, PHQ-2, reaction time) to "watch": one
                    check-in with PHQ-2 >= 3 makes it "concern"
  --run             drive a running backend: scheduled scenarios
                    (--scenario a3:strain:60 = a3 reaches "urgent" 60 s after start)
                    and, with --post-hr, heart rate for a2-a4 every 3 s

Seed before starting the server, or restart it after seeding. Deterministic:
--seed (default 42) gives the same history every time.
"""

import argparse
import random
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import engine  # noqa: E402
import location  # noqa: E402
import store  # noqa: E402

MISSION_DAYS = 42   # "today" is mission day 42: six weeks in
STEP_MIN = 10       # one stored sample every 10 min (live ticks are every 3 s)
CHECKIN_EVERY_DAYS = 2
PRIVATE_CHECKINS = {"a2"}  # a2 keeps check-ins private, so the ground view shows redaction
RT_BASELINE_MS = {"a1": 248, "a2": 262, "a3": 255, "a4": 270}  # reaction test, 3-min PVT-B


def _walk(rng, value, target, step, rate=0.3):
    return value + rng.gauss(0, step) + (target - value) * rate


def seed(seed_value: int = 42, end: datetime | None = None) -> datetime:
    """Six weeks of history. Day-to-day variation is realistic on purpose (resting HR ~3%, HRV ~12%,
    activity ~25%, sleep ~0.5 h): with too little noise every change looks huge, and the accuracy
    check (tools/check_profile.py) would be meaningless. Returns the mission start.

    Each astronaut has their own random stream, so the past days come out the same whatever the
    time of day the seed runs: the demo story is repeatable."""
    end = end or datetime.now(timezone.utc).replace(second=0, microsecond=0)
    start = (end - timedelta(days=MISSION_DAYS - 1)).replace(hour=0, minute=0)
    samples, checkins, visits = [], [], []
    for aid, (_, _, b) in engine.CREW.items():
        rng = random.Random(f"vitals-{aid}-{seed_value}")
        v = {k: float(x) for k, x in b.items()}
        t, sleep_h, day_seen = start, b["sleep_h_last_night"], None
        day_target: dict = {}
        while t < end:
            day = (t - start).days + 1
            if day != day_seen:  # this day's own level for each signal
                day_seen = day
                d = engine.drift(aid, day)
                day_target = {
                    "hr": b["heart_rate_bpm"] * (1 + rng.gauss(0, 0.03)),
                    "hrv": b["hrv_sdnn_ms"] * d.get("hrv_sdnn_ms", 1.0) * (1 + rng.gauss(0, 0.12)),
                    "active": max(0.0, b["active_min"] * d.get("active_min", 1.0) * (1 + rng.gauss(0, 0.25))),
                }
            hour = t.hour + t.minute / 60
            asleep = hour >= 22.5 or hour < 5.5
            if t.hour == 6 and t.minute == 0:  # new night's sleep, logged on waking
                sleep_h = round(min(9.0, max(4.5, rng.gauss(b["sleep_h_last_night"], 0.5))), 1)
            # Days 1-6: space adaptation / headward fluid shift distorts vitals, which is
            # why the baseline window starts on day 7.
            adapt = (7 - day) / 6 if day < 7 else 0.0
            targets = {
                "heart_rate_bpm": day_target["hr"] * (0.88 if asleep else 1.0) * (1 + 0.08 * adapt),
                "spo2_pct": b["spo2_pct"],
                "temp_c": b["temp_c"] + (-0.3 if asleep else 0.1) + 0.2 * adapt,
                "resp_rate_bpm": b["resp_rate_bpm"] * (0.9 if asleep else 1.0),
                "hrv_sdnn_ms": day_target["hrv"] * (1.1 if asleep else 1.0),
            }
            steps = {"heart_rate_bpm": 1.5, "spo2_pct": 0.3, "temp_c": 0.03, "resp_rate_bpm": 0.4,
                     "hrv_sdnn_ms": 1.5}
            for f, target in targets.items():
                v[f] = _walk(rng, v[f], target, steps[f])
            v["spo2_pct"] = min(100.0, v["spo2_pct"])
            awake = max(0.0, min(1.0, (t.hour * 60 + t.minute - 360) / (16.5 * 60)))
            samples.append((aid, store.iso(t), round(v["heart_rate_bpm"], 1), round(v["spo2_pct"], 1),
                            round(v["temp_c"], 2), round(v["resp_rate_bpm"], 1), sleep_h, b["mood_1to5"],
                            round(v["hrv_sdnn_ms"], 1), round(day_target["active"] * awake, 1), "simulated"))
            t += timedelta(minutes=STEP_MIN)

        # Room stays from the Bluetooth beacons (simulated from the daily schedule in location.py).
        visits += location.simulate_visits(aid, start, end, start.date(), seed_value)

        # Check-ins get their own fixed random sequence: the number of vitals samples above depends
        # on the time of day, and must not change the check-in story between demo runs.
        rng_ck = random.Random(f"checkins-{aid}-{seed_value}")
        for day in range(CHECKIN_EVERY_DAYS, MISSION_DAYS + 1, CHECKIN_EVERY_DAYS):
            ts = start + timedelta(days=day - 1, hours=8)
            if ts >= end:
                break
            mood = b["mood_1to5"] + rng_ck.choice((0, 0, 0, -1))
            phq = (rng_ck.choice((0, 0, 0, 1)), 0)
            rt = rng_ck.gauss(RT_BASELINE_MS[aid], 8)
            lapses = rng_ck.choice((0, 1, 1, 2))
            if aid == "a2" and day >= engine.DECLINE_FROM_DAY:
                # The demo story: a slow decline after the mission midpoint (as in HI-SEAS),
                # ending at "watch" on day 42. One check-in with PHQ-2 >= 3 then makes it "concern".
                weeks_in = (day - engine.DECLINE_FROM_DAY + 1) / 7
                mood = b["mood_1to5"] - (1 if rng_ck.random() < min(0.6, 0.2 * weeks_in) else 0)
                phq = (1, 1) if day > MISSION_DAYS - 10 else (1, 0)
                rt = RT_BASELINE_MS[aid] * (1 + min(0.06, 0.02 * weeks_in)) + rng_ck.gauss(0, 6)
                lapses = 1 + round(min(2, 0.5 * weeks_in))
            payload = {"timestamp": store.iso(ts), "share_with_ground": aid not in PRIVATE_CHECKINS,
                       "mood_1to5": max(1, min(5, mood)),
                       "phq2": {"little_interest": phq[0], "feeling_down": phq[1]},
                       "reaction_test": {"mean_rt_ms": round(rt), "lapses": lapses, "false_starts": 0,
                                         "duration_s": 180}}
            checkins.append((aid, store.iso(ts), payload))

    store.init()
    store.insert_samples(samples)
    store.insert_checkins(checkins)
    store.insert_visits(visits)
    store.meta_set("mission_start", store.iso(start))
    store.meta_set("seeded_until", store.iso(end))
    print(f"Seeded {len(samples)} samples, {len(checkins)} check-ins and {len(visits)} room stays, mission days "
          f"1-{MISSION_DAYS} ({store.iso(start)} to {store.iso(end)}) into {store.DB_PATH}")
    return start


def run(base: str, scenarios: list[tuple[str, str, float]], post_hr: bool, rng: random.Random) -> None:
    import httpx

    pending = sorted(scenarios, key=lambda s: s[2])
    hr = {aid: float(engine.CREW[aid][2]["heart_rate_bpm"]) for aid in ("a2", "a3", "a4")}
    t0 = time.monotonic()
    print(f"Driving {base} (Ctrl+C to stop)")
    with httpx.Client(base_url=base, timeout=5) as client:
        while True:
            elapsed = time.monotonic() - t0
            while pending and pending[0][2] <= elapsed:
                aid, scenario, _ = pending.pop(0)
                r = client.post("/debug/scenario", json={"astronaut_id": aid, "scenario": scenario})
                print(f"t={elapsed:5.0f}s  {aid} -> {scenario}  ({r.status_code})")
            if post_hr:
                stamp = store.iso(datetime.now(timezone.utc))
                for aid in hr:
                    hr[aid] = _walk(rng, hr[aid], engine.CREW[aid][2]["heart_rate_bpm"], 1.0, 0.1)
                    client.post(f"/astronauts/{aid}/ingest",
                                json={"timestamp": stamp, "heart_rate_bpm": round(hr[aid], 1), "source": "simulated"})
            if not pending and not post_hr:
                return
            time.sleep(3)


def parse_scenario(text: str) -> tuple[str, str, float]:
    aid, scenario, at = text.split(":")
    return aid, scenario, float(at.rstrip("s"))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--reset-db", action="store_true")
    p.add_argument("--seed-baseline", action="store_true")
    p.add_argument("--run", action="store_true")
    p.add_argument("--scenario", action="append", default=[], type=parse_scenario,
                   metavar="AID:SCENARIO:SECONDS")
    p.add_argument("--post-hr", action="store_true")
    p.add_argument("--base", default="http://localhost:8000")
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()
    if not (args.reset_db or args.seed_baseline or args.run):
        p.error("nothing to do: pass --reset-db, --seed-baseline and/or --run")
    rng = random.Random(args.seed)
    if args.reset_db:
        store.init()
        store.reset()
        print(f"Reset {store.DB_PATH}")
    if args.seed_baseline:
        seed(args.seed)
    if args.run:
        run(args.base, args.scenario, args.post_hr, rng)


if __name__ == "__main__":
    main()
