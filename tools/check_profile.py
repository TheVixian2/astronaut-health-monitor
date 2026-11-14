# Written with AI assistance (Claude Code, Anthropic) and reviewed by the team. See README "Use of AI".
"""Accuracy check for the psychological profile, on simulated crews.

For each random seed: write six weeks of history (tools/simulate_crew.py) into a throwaway
database, then score every astronaut on every day after the baseline window (mission days
15-41) exactly as the server does, from complete days only.

Ground truth comes from the simulation itself:
  - a1, a3, a4 are stable all mission: any flag is a false alarm.
  - a2 is stable until day 21, then declines slowly (engine.drift, location.py, check-ins).
    Days 15-21 count as stable; days 35-41 (two weeks into the decline) should be flagged.

This measures the scoring against its own synthetic data: it shows false-alarm rates and
detection under realistic day-to-day noise. It is NOT clinical validation; no real
astronaut data is involved. The body-clock input (live lighting log) is not included.

  backend/.venv/bin/python tools/check_profile.py --seeds 20
"""

import argparse
import sys
import tempfile
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "tools"))
import behavioral  # noqa: E402
import location  # noqa: E402
import simulate_crew  # noqa: E402
import store  # noqa: E402

RANK = behavioral.LEVEL_RANK


def histories(mission_start: datetime, end: datetime) -> dict[str, behavioral.History]:
    """The same reads as main._load_store_view, for every astronaut."""
    start_iso, end_iso = store.iso(mission_start), store.iso(end)
    last_day = end.date() - timedelta(days=1)
    social = location.daily_social(store.visits_between(start_iso, end_iso), mission_start.date(), last_day)
    out = {}
    for aid in location.CREW_IDS:
        days = {}
        for dstr, a in store.daily_aggregates(aid, start_iso, end_iso).items():
            days[date.fromisoformat(dstr)] = behavioral.DayData(rhr=a["rhr"], hrv=a["hrv"], active=a["active"],
                                                                sleep=a["sleep"])
        for d, (c, q) in social[aid].items():
            dd = days.setdefault(d, behavioral.DayData())
            dd.crew_h, dd.quarters_h = c, q
        out[aid] = behavioral.History(days=days, checkins=store.checkins_between(aid, start_iso),
                                      mission_start=mission_start.date())
    return out


def run(seeds: int, verbose: bool) -> None:
    stable_days = Counter()      # level counts on astronaut-days that should be steady
    declined_days = Counter()    # level counts on a2 days 35-41
    first_flag = []              # mission day a2's current run at >= watch started
    final = Counter()
    with tempfile.TemporaryDirectory() as tmp:
        for seed in range(1, seeds + 1):
            store.DB_PATH = Path(tmp) / f"check-{seed}.db"
            end = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)
            import contextlib, io
            with contextlib.redirect_stdout(io.StringIO()):
                start = simulate_crew.seed(seed, end=end)
            hist = histories(start, end)
            for aid, h in hist.items():
                levels = {}
                for md in range(15, 42):
                    d = start.date() + timedelta(days=md - 1)
                    levels[md] = behavioral.compute(h, d).level
                for md, lv in levels.items():
                    if aid != "a2" or md <= 21:
                        stable_days[lv] += 1
                    elif md >= 35:
                        declined_days[lv] += 1
                final[(aid, levels[41])] += 1
                if aid == "a2":
                    run_start = None
                    for md in range(41, 21, -1):
                        if RANK[levels[md]] >= RANK["watch"]:
                            run_start = md
                        else:
                            break
                    first_flag.append(run_start)
                if verbose:
                    print(f"seed {seed:>2} {aid}: " + " ".join(f"{lv[0]}" for lv in levels.values()))

    def pct(c: Counter, at_least: str) -> float:
        n = sum(c.values())
        return 100 * sum(v for k, v in c.items() if RANK[k] >= RANK[at_least]) / n if n else 0.0

    n_stable, n_decl = sum(stable_days.values()), sum(declined_days.values())
    print(f"Simulated crews: {seeds} seeds x 4 astronauts, mission days 15-41\n")
    print(f"Stable astronaut-days ({n_stable}): levels {dict(stable_days)}")
    print(f"  false alarms at 'watch' or above:   {pct(stable_days, 'watch'):5.1f}%")
    print(f"  false alarms at 'concern' or above: {pct(stable_days, 'concern'):5.1f}%")
    print(f"a2 days 35-41, two weeks into the decline ({n_decl}): levels {dict(declined_days)}")
    print(f"  detected at 'watch' or above:       {pct(declined_days, 'watch'):5.1f}%")
    found = [d for d in first_flag if d is not None]
    if found:
        print(f"  flagged continuously from mission day {min(found)}-{max(found)} "
              f"(median {sorted(found)[len(found) // 2]}); decline starts on day 22")
    print(f"  not flagged on day 41 in {first_flag.count(None)} of {seeds} seeds")
    print("\nDay-41 level per astronaut:", dict(sorted(final.items())))
    print("\nSynthetic data only: this checks the scoring against its own simulation, not clinical accuracy.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seeds", type=int, default=20)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    run(args.seeds, args.verbose)
