"""Habitat rooms: where each crew member is, and time per room (PROVISIONAL).

In the real system a Bluetooth beacon in each module lets the watch know which room
it is in (strongest signal wins). The hygiene module has NO beacon, so it can never
be tracked. Here positions come from a deterministic daily schedule, so every demo
run is identical and nothing extra is stored.

Two uses, pitched differently:
- Live position: SAFETY (fire or depressurisation: the commander knows where everyone is).
- Hours per day in shared vs private rooms, vs the astronaut's own normal: a SUPPORTING
  wellbeing signal only. Evidence that time alone tracks mood is weak (small phone-sensing
  studies), so it is shown, never added to the wellbeing score.
"""

import random
from datetime import datetime, timedelta

ROOMS = {  # id -> (name, kind); kind: shared | private | untracked
    "command": ("Command deck", "shared"),
    "lab": ("Lab", "shared"),
    "galley": ("Galley & wardroom", "shared"),
    "exercise": ("Exercise", "shared"),
    "q_a1": ("Quarters 1", "private"),
    "q_a2": ("Quarters 2", "private"),
    "q_a3": ("Quarters 3", "private"),
    "q_a4": ("Quarters 4", "private"),
    "hygiene": ("Hygiene (not tracked)", "untracked"),
}
WORK_ROOM = {"a1": "command", "a2": "lab", "a3": "lab", "a4": "command"}
EXERCISE_HOUR = {"a1": 15, "a2": 10, "a3": 13, "a4": 16}  # 2-hour block, as on the ISS
MEALS = ((7.0, 7.67), (12.0, 12.75), (18.5, 19.5))
STEP_MIN = 5
MIDPOINT_DAY, MISSION_DAY_NOW = 21, 42  # matches tools/simulate_crew.py


def withdrawal(aid: str, day: int) -> float:
    """0..1. Only a2 withdraws, slowly, after the mission midpoint (the demo story)."""
    if aid != "a2" or day <= MIDPOINT_DAY:
        return 0.0
    return min(1.0, (day - MIDPOINT_DAY) / (MISSION_DAY_NOW - MIDPOINT_DAY))


def room_at(aid: str, t: datetime, mission_start: datetime) -> str:
    day = (t - mission_start).days + 1
    h = t.hour + t.minute / 60
    rng = random.Random(f"{aid}-{int(t.timestamp()) // (STEP_MIN * 60)}")
    own = f"q_{aid}"
    w = withdrawal(aid, day)
    if h >= 22.5 or h < 6.0:
        return own
    if h < 6.5 or rng.random() < 0.03:
        return "hygiene"
    if any(a <= h < b for a, b in MEALS):
        return own if random.Random(f"{aid}-meal-{day}-{int(h)}").random() < 0.6 * w else "galley"
    ex = EXERCISE_HOUR[aid]
    if ex <= h < ex + 2:
        return "exercise"
    if h < 18.5:
        return WORK_ROOM[aid] if rng.random() > 0.15 else "lab"
    # Evening free time: usually social, less so for someone withdrawing.
    return "galley" if random.Random(f"{aid}-eve-{day}-{int(h)}").random() < 0.6 - 0.45 * w else own


def hours_by_room(aid: str, start: datetime, end: datetime, mission_start: datetime) -> dict[str, float]:
    out: dict[str, float] = {}
    t = start
    while t < end:
        r = room_at(aid, t, mission_start)
        out[r] = out.get(r, 0.0) + STEP_MIN / 60
        t += timedelta(minutes=STEP_MIN)
    return {r: round(v, 1) for r, v in out.items()}


def by_kind(hours: dict[str, float]) -> dict[str, float]:
    out = {"shared": 0.0, "private": 0.0, "untracked": 0.0}
    for r, v in hours.items():
        out[ROOMS[r][1]] += v
    return {k: round(v, 1) for k, v in out.items()}


def waking_shared_normal(aid: str, mission_start: datetime) -> float:
    """Average daily hours in shared rooms over mission days 7-14: the astronaut's own normal."""
    days = [by_kind(hours_by_room(aid, mission_start + timedelta(days=d), mission_start + timedelta(days=d + 1),
                                  mission_start))["shared"] for d in range(6, 14)]
    return round(sum(days) / len(days), 1)


def since(aid: str, t: datetime, mission_start: datetime) -> datetime:
    """When the astronaut entered the room they are in now (looks back up to 12 h)."""
    room = room_at(aid, t, mission_start)
    s = t.replace(second=0, microsecond=0)
    s -= timedelta(minutes=s.minute % STEP_MIN)
    for _ in range(12 * 60 // STEP_MIN):
        prev = s - timedelta(minutes=STEP_MIN)
        if room_at(aid, prev, mission_start) != room:
            break
        s = prev
    return s
