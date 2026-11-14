"""Room-level location from Bluetooth beacons (PROVISIONAL).

One Bluetooth Low Energy beacon per room. The watch scans and reports which beacons it
hears and how strongly (RSSI); the strongest beacon above a floor is the room. Signals
flicker, so the room only changes after two scans in a row agree. Watch-plus-beacon room
detection reaches roughly 86-92% in homes, with most errors in doorways (Bouse et al.,
Sensors 2024), so a room reading is treated as a good guess, never as fact.

Why it matters here: time with crewmates and time alone in one's quarters, each compared with
the astronaut's own normal, feed the psychological profile (behavioral.py: social_time).
Proximity sensors measured crew cohesion in Mars-500 (Johannes et al., PLoS ONE 2015) and
Antarctic winter-overs (Basner et al., Front Psychol 2026).

Privacy: rooms only, no coordinates. Only the astronaut sees where they are; the commander,
the Crew Medical Officer and Mission Control see the current room only during an emergency
(an active alert or an urgent wellbeing level), and the astronaut can see who looked. Nobody
gets a live map of the crew. There is no physical watch or beacon in this project: movement
is simulated from a daily schedule unless a scan arrives.
"""

import hashlib
import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field

RSSI_FLOOR_DBM = -90      # weaker than this is ignored (placeholder)
CONFIRM_SCANS = 2         # scans in a row that must agree before the room changes
SCAN_FRESH_S = 60         # a beacon reading older than this falls back to the schedule
SLOT_MIN = 5              # resolution of the daily time-with-crew calculation
AWAKE = (6 * 60, 22 * 60 + 30)  # minutes after midnight, station time (UTC)
IBEACON_UUID = "6D61B6C0-4D41-5253-2D44-472D48414221"  # one UUID for the habitat; major 1, minor = room

CREW_IDS = ("a1", "a2", "a3", "a4")
FIRST_NAME = {"a1": "Elena", "a2": "Mihai", "a3": "Sara", "a4": "Jonas"}

Kind = Literal["quarters", "shared", "private"]


@dataclass(frozen=True)
class RoomDef:
    id: str
    name: str
    kind: Kind
    owner: Optional[str] = None


ROOMS: dict[str, RoomDef] = {
    **{f"quarters_{a}": RoomDef(f"quarters_{a}", f"Crew quarters ({FIRST_NAME[a]})", "quarters", a)
       for a in CREW_IDS},
    "galley": RoomDef("galley", "Galley and wardroom", "shared"),
    "command": RoomDef("command", "Command deck", "shared"),
    "lab": RoomDef("lab", "Science lab", "shared"),
    "exercise": RoomDef("exercise", "Exercise area", "shared"),
    "hygiene": RoomDef("hygiene", "Hygiene compartment", "private"),
}
BEACONS = {f"dg-{rid}": rid for rid in ROOMS}  # beacon id -> room id
MINOR = {rid: i + 1 for i, rid in enumerate(ROOMS)}


class BeaconReading(BaseModel):
    beacon_id: str
    rssi: int = Field(ge=-127, le=20)


class ScanRequest(BaseModel):
    timestamp: datetime
    beacons: list[BeaconReading] = Field(max_length=64)


class ScanResult(BaseModel):
    room: Optional[str]
    room_name: Optional[str]
    status: Literal["changed", "same", "waiting_confirmation", "too_weak", "no_known_beacon"]
    detail: str


class Room(BaseModel):
    id: str
    name: str
    kind: Kind
    owner: Optional[str]
    beacon_id: str
    ibeacon: dict


def rooms() -> list[Room]:
    return [Room(id=r.id, name=r.name, kind=r.kind, owner=r.owner, beacon_id=f"dg-{r.id}",
                 ibeacon={"uuid": IBEACON_UUID, "major": 1, "minor": MINOR[r.id]}) for r in ROOMS.values()]


# --- Simulated daily schedule ----------------------------------------------------
# (start min, end min, room or a role key). Station time is UTC.
WORK_ROOM = {"a1": "command", "a2": "lab", "a3": "lab", "a4": "command"}
HYGIENE = {"a1": 360, "a2": 375, "a3": 390, "a4": 405}       # 15-min slots from 06:00
EXERCISE = {"a1": (13 * 60, 14 * 60 + 30), "a2": (14 * 60 + 30, 16 * 60),
            "a3": (16 * 60, 17 * 60 + 30), "a4": (8 * 60, 9 * 60 + 30)}
P_SOCIAL = {"a1": 0.55, "a2": 0.6, "a3": 0.65, "a4": 0.5}   # evening half-hours spent in the galley
DECLINE_FROM_DAY = 22        # a2 withdraws a little after the mission midpoint (matches the seed)


def _rng(*parts) -> random.Random:
    return random.Random(int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:12], 16))


def scheduled_room(aid: str, t: datetime, mission_day: int, seed: int = 0) -> str:
    """Where the schedule puts this astronaut at time t. Deterministic, so live and seeded agree."""
    m = t.hour * 60 + t.minute
    day = t.date().isoformat()
    quarters = f"quarters_{aid}"
    withdraw = 0.0
    if aid == "a2" and mission_day >= DECLINE_FROM_DAY:
        withdraw = min(1.0, (mission_day - DECLINE_FROM_DAY + 1) / 14)   # ramps up over two weeks
    if m < AWAKE[0] or m >= AWAKE[1]:
        return quarters
    if HYGIENE[aid] <= m < HYGIENE[aid] + 15:
        return "hygiene"
    meal = 420 <= m < 465 or 720 <= m < 780 or 1080 <= m < 1140      # 07:00, 12:00, 18:00
    if meal:
        skip = 0.05 + 0.15 * withdraw
        return quarters if _rng(seed, aid, day, "meal", m // 60).random() < skip else "galley"
    lo, hi = EXERCISE[aid]
    if lo <= m < hi:
        return "exercise"
    if 465 <= m < 1080:                                               # work, with short breaks
        return quarters if _rng(seed, aid, day, "break", m // 30).random() < 0.08 else WORK_ROOM[aid]
    if m < 420:
        return quarters
    p = P_SOCIAL[aid] * (1 - 0.35 * withdraw)                         # evening free time
    return "galley" if _rng(seed, aid, day, "evening", m // 30).random() < p else quarters


def simulate_visits(aid: str, start: datetime, end: datetime, mission_start: date, seed: int = 0) -> list[tuple]:
    """Seeded history: (astronaut_id, room, entered_at, left_at, source) rows."""
    rows, cur, since = [], None, start
    t = start
    while t < end:
        room = scheduled_room(aid, t, (t.date() - mission_start).days + 1, seed)
        if room != cur:
            if cur is not None:
                rows.append((aid, cur, _iso(since), _iso(t), "simulated"))
            cur, since = room, t
        t += timedelta(minutes=SLOT_MIN)
    if cur is not None:
        rows.append((aid, cur, _iso(since), _iso(end), "simulated"))
    return rows


def _iso(t: datetime) -> str:
    return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --- Beacon scans ----------------------------------------------------------------

@dataclass
class _ScanState:
    room: Optional[str] = None
    at: float = -1e9          # loop time of the last confirmed scan
    candidate: Optional[str] = None
    candidate_n: int = 0


_scans: dict[str, _ScanState] = {a: _ScanState() for a in CREW_IDS}


def handle_scan(aid: str, body: ScanRequest, loop_time: float) -> ScanResult:
    st = _scans[aid]
    known = [b for b in body.beacons if b.beacon_id in BEACONS]
    if not known:
        return ScanResult(room=st.room, room_name=_name(st.room), status="no_known_beacon",
                          detail="None of the beacons heard belong to the habitat.")
    best = max(known, key=lambda b: b.rssi)
    if best.rssi < RSSI_FLOOR_DBM:
        return ScanResult(room=st.room, room_name=_name(st.room), status="too_weak",
                          detail=f"Strongest beacon {best.rssi} dBm is below {RSSI_FLOOR_DBM} dBm; keeping the last room.")
    room = BEACONS[best.beacon_id]
    if room == st.room:
        st.at, st.candidate, st.candidate_n = loop_time, None, 0
        return ScanResult(room=room, room_name=_name(room), status="same", detail="Same room as before.")
    st.candidate_n = st.candidate_n + 1 if st.candidate == room else 1
    st.candidate = room
    if st.candidate_n < CONFIRM_SCANS and st.room is not None:
        return ScanResult(room=st.room, room_name=_name(st.room), status="waiting_confirmation",
                          detail=f"Heard {ROOMS[room].name}; waiting for {CONFIRM_SCANS} scans in a row to agree.")
    st.room, st.at, st.candidate, st.candidate_n = room, loop_time, None, 0
    return ScanResult(room=room, room_name=_name(room), status="changed", detail=f"Now in {ROOMS[room].name}.")


def current_room(aid: str, t: datetime, mission_day: int, loop_time: float) -> tuple[str, str]:
    """(room, source): the confirmed beacon room if recent, otherwise the schedule."""
    st = _scans[aid]
    if st.room and loop_time - st.at < SCAN_FRESH_S:
        return st.room, "beacon"
    return scheduled_room(aid, t, mission_day), "simulated"


def _name(room: Optional[str]) -> Optional[str]:
    return ROOMS[room].name if room else None


# --- Daily time with crewmates / alone in quarters -----------------------------------

def daily_social(visits: list[tuple[str, str, str, str]], first_day: date, last_day: date) -> dict[str, dict[date, tuple[float, float]]]:
    """visits: (astronaut_id, room, entered_at, left_at). Returns aid -> day -> (crew_h, quarters_h),
    awake hours only. 'With crew' = a shared room with at least one other astronaut in it."""
    n_days = (last_day - first_day).days + 1
    if n_days <= 0:
        return {a: {} for a in CREW_IDS}
    per_day = 24 * 60 // SLOT_MIN
    origin = datetime.combine(first_day, datetime.min.time(), tzinfo=timezone.utc)
    grid = {a: [None] * (n_days * per_day) for a in CREW_IDS}
    for aid, room, entered, left in visits:
        if aid not in grid:
            continue
        a = int((datetime.fromisoformat(entered.replace("Z", "+00:00")) - origin).total_seconds() // (SLOT_MIN * 60))
        b = int((datetime.fromisoformat(left.replace("Z", "+00:00")) - origin).total_seconds() // (SLOT_MIN * 60))
        for i in range(max(a, 0), min(b, len(grid[aid]))):
            grid[aid][i] = room
    out: dict[str, dict[date, tuple[float, float]]] = {a: {} for a in CREW_IDS}
    h = SLOT_MIN / 60
    for d in range(n_days):
        day = first_day + timedelta(days=d)
        lo, hi = d * per_day + AWAKE[0] // SLOT_MIN, d * per_day + AWAKE[1] // SLOT_MIN
        for aid in CREW_IDS:
            slots = grid[aid][lo:hi]
            known = sum(1 for r in slots if r is not None)
            if known < 0.8 * (hi - lo):
                continue                                   # too little data for this day
            crew_h = quarters_h = 0.0
            for i, room in enumerate(slots, start=lo):
                if room is None:
                    continue
                if room == f"quarters_{aid}":
                    quarters_h += h
                elif ROOMS.get(room) and ROOMS[room].kind == "shared" and any(
                        grid[o][i] == room for o in CREW_IDS if o != aid):
                    crew_h += h
            out[aid][day] = (round(crew_h, 2), round(quarters_h, 2))
    return out
