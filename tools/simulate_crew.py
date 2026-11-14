"""Crew simulator and demo seeding for the backend.

Run with the backend's virtual environment, from the repo root:

  Windows:  backend\\.venv\\Scripts\\python tools\\simulate_crew.py --reset-db --seed-baseline
  macOS:    backend/.venv/bin/python tools/simulate_crew.py --reset-db --seed-baseline

  --reset-db        wipe backend/data/ahm.db (samples, alerts, check-ins)
  --seed-baseline   write six weeks of mission history, so the personal baseline
                    (mission days 7-14) is a real SELECT the moment the server
                    starts, and a1's SANS risk sits just below its trigger:
                    one check-in during the demo tips it over
  --run             drive a running backend: scheduled scenarios
                    (--scenario a3:fever:60 = a3 gets fever 60 s after start)
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
import store  # noqa: E402

MISSION_DAYS = 42   # "today" is mission day 42: six weeks in
STEP_MIN = 10       # one stored sample every 10 min (live ticks are every 3 s)
CHECKIN_EVERY_DAYS = 2
ACUITY_BASELINE = {"a1": 9, "a2": 10, "a3": 9, "a4": 10}
PRIVATE_CHECKINS = {"a2"}  # a2 keeps check-ins private, so the ground view shows redaction


def _walk(rng, value, target, step, rate=0.3):
    return value + rng.gauss(0, step) + (target - value) * rate


def seed(rng: random.Random) -> None:
    end = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    start = (end - timedelta(days=MISSION_DAYS - 1)).replace(hour=0, minute=0)
    samples, checkins = [], []
    for aid, (_, _, b) in engine.CREW.items():
        v = {k: float(x) for k, x in b.items()}
        co2 = engine.CABIN_CO2_NOMINAL_MMHG
        t, sleep_h = start, b["sleep_h_last_night"]
        while t < end:
            day = (t - start).days + 1
            hour = t.hour + t.minute / 60
            asleep = hour >= 22.5 or hour < 5.5
            if t.hour == 6 and t.minute == 0:  # new night's sleep, logged on waking
                sleep_h = round(min(8.5, max(5.0, rng.gauss(b["sleep_h_last_night"], 0.4))), 1)
            # Days 1-6: space adaptation / headward fluid shift distorts vitals, which is
            # why the baseline window starts on day 7.
            adapt = (7 - day) / 6 if day < 7 else 0.0
            targets = {
                "heart_rate_bpm": b["heart_rate_bpm"] * (0.88 if asleep else 1.0) * (1 + 0.08 * adapt),
                "systolic_mmhg": b["systolic_mmhg"] * (1 - 0.05 * adapt),
                "diastolic_mmhg": b["diastolic_mmhg"],
                "spo2_pct": b["spo2_pct"],
                "temp_c": b["temp_c"] + (-0.3 if asleep else 0.1) + 0.2 * adapt,
                "resp_rate_bpm": b["resp_rate_bpm"] * (0.9 if asleep else 1.0),
            }
            steps = {"heart_rate_bpm": 1.5, "systolic_mmhg": 1.5, "diastolic_mmhg": 1.0,
                     "spo2_pct": 0.3, "temp_c": 0.03, "resp_rate_bpm": 0.4}
            for f, target in targets.items():
                v[f] = _walk(rng, v[f], target, steps[f])
            v["spo2_pct"] = min(100.0, v["spo2_pct"])
            # a1's module CO2 creeps up over the last two weeks: one of the SANS inputs.
            co2_target = 3.3 if aid == "a1" and day > MISSION_DAYS - 14 else engine.CABIN_CO2_NOMINAL_MMHG
            co2 = max(0.0, _walk(rng, co2, co2_target, 0.08))
            samples.append((aid, store.iso(t), round(v["heart_rate_bpm"], 1), round(v["systolic_mmhg"], 1),
                            round(v["diastolic_mmhg"], 1), round(v["spo2_pct"], 1), round(v["temp_c"], 2),
                            round(v["resp_rate_bpm"], 1), sleep_h, b["mood_1to5"], round(co2, 2), "simulated"))
            t += timedelta(minutes=STEP_MIN)

        for day in range(CHECKIN_EVERY_DAYS, MISSION_DAYS + 1, CHECKIN_EVERY_DAYS):
            ts = start + timedelta(days=day - 1, hours=8)
            if ts >= end:
                break
            acuity = ACUITY_BASELINE[aid]
            symptoms = []
            if aid == "a1":  # slow SANS build-up, stopping just short of the trigger
                if day >= 34:
                    acuity -= 1
                if day in (38, 40):
                    symptoms.append("headache")
            payload = {"timestamp": store.iso(ts), "share_with_ground": aid not in PRIVATE_CHECKINS,
                       "mood_1to5": max(1, min(5, b["mood_1to5"] + rng.choice((0, 0, 0, -1)))),
                       "vision": {"amsler_distortion": False, "acuity_line": acuity}}
            if symptoms:
                payload["symptoms"] = symptoms
            checkins.append((aid, store.iso(ts), payload))

    store.init()
    store.insert_samples(samples)
    store.insert_checkins(checkins)
    store.meta_set("mission_start", store.iso(start))
    store.meta_set("seeded_until", store.iso(end))
    print(f"Seeded {len(samples)} samples and {len(checkins)} check-ins, mission days 1-{MISSION_DAYS} "
          f"({store.iso(start)} to {store.iso(end)}) into {store.DB_PATH}")


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
        seed(rng)
    if args.run:
        run(args.base, args.scenario, args.post_hr, rng)


if __name__ == "__main__":
    main()
