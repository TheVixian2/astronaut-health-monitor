"""Astronaut Health Monitor backend. The contract is docs/api-spec.md.

Heart rate for a1 comes from the watch (POST /ingest). Every other vital, and all
of a2-a4, is simulated server-side as a mean-reverting random walk around each
astronaut's own baseline, shifted coherently by a scenario (POST /debug/scenario).

Every tick is stored (store.py). The baseline is the median of stored mission
days 7-14. The condition engine (engine.py) raises an alert only on a NEW match,
and the explanation comes from insight_service.py: Claude when a key is set,
otherwise the built-in explanation made from the real numbers. Circadian rhythm
lives in circadian.py, live Mars light time in horizons.py (NASA JPL).

Run:   uvicorn main:app --reload           ->  http://localhost:8000/docs
Seed:  python ../tools/simulate_crew.py --reset-db --seed-baseline   (before the demo)
"""

import asyncio
import json
import logging
import os
import random
import statistics
import uuid
from collections import deque
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, model_validator

import behavioral
import circadian
import engine
import horizons
import iss_live
import insight_service
import location
import quality
import store

logging.basicConfig(level=logging.INFO, format="%(levelname)s:     %(name)s: %(message)s")
log = logging.getLogger("ahm")

TICK_S = 3
REFRESH_EVERY_TICKS = 20  # baselines and wellbeing every ~60 s
REAL_HR_FRESH_S = 10      # watch HR older than this falls back to simulated
DEFAULT_MISSION_DAY = int(os.getenv("AHM_MISSION_DAY", "42"))  # used when the DB has no mission start
LIVE_LIGHT_TIME = os.getenv("AHM_LIVE_LIGHT_TIME") == "1"      # use JPL Horizons for the Mars verdict

Status = Literal["nominal", "watch", "alert", "critical"]
Severity = Literal["watch", "alert", "critical"]
Hazard = Literal["radiation", "isolation", "distance", "gravity", "environment"]
BodyRegion = Literal["heart", "head", "lungs", "skin", "whole_body"]
Environment = Literal["iss", "moon", "mars"]
Source = Literal["real", "simulated"]


def now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


# --- Models (shapes from docs/api-spec.md) ---------------------------------

class CrewMember(BaseModel):
    id: str
    name: str
    role: str
    status: Status


class IngestRequest(BaseModel):
    timestamp: datetime
    heart_rate_bpm: float
    source: Source
    hrv_sdnn_ms: Optional[float] = Field(default=None, ge=0, le=500)   # PROVISIONAL: from the watch
    active_min: Optional[float] = Field(default=None, ge=0, le=1440)   # PROVISIONAL: active minutes today


class Accepted(BaseModel):
    accepted: bool = True


class Baseline(BaseModel):
    heart_rate_bpm: int
    spo2_pct: int
    temp_c: float
    resp_rate_bpm: int
    sleep_h_last_night: float
    mood_1to5: int
    hrv_sdnn_ms: float = 0   # PROVISIONAL: heart-rate variability (ms) from the watch
    active_min: float = 0    # PROVISIONAL: active minutes so far today (baseline: a usual whole day)


Quality = Literal["ok", "suspect", "implausible"]


class Vitals(Baseline):
    timestamp: datetime
    source: Source
    baseline: Baseline
    quality: Quality = "ok"  # PROVISIONAL: sensor check of this reading (quality.py)


class Insight(BaseModel):
    why: str
    trend: str
    recommended_action: str


class Confirmation(BaseModel):  # PROVISIONAL
    status: Literal["pending", "felt", "not_felt"]
    question: str
    answered_at: Optional[datetime] = None
    note: Optional[str] = None


class Alert(BaseModel):
    id: str
    astronaut_id: str
    profile: str
    severity: Severity
    hazard: Hazard
    body_region: BodyRegion
    started_at: datetime
    onboard_action: str
    act_within_s: int
    ground_eta_s: int
    insight: Optional[Insight] = None
    # PROVISIONAL additions (not yet in docs/api-spec.md)
    data_quality: Literal["ok", "suspect"] = "ok"   # suspect = a sensor glitch was seen at the time
    confirmation: Optional[Confirmation] = None     # "do you feel this?"; null for check-in-based alerts
    # Psychological alerts: the commander sees them first (the deputy if the commander is the one
    # flagged) and releases them to the astronaut; Mission Control always gets them after the delay.
    psychological: bool = False
    routed_to: Optional[str] = None                 # who has it first on board
    released_to_crew_at: Optional[datetime] = None  # when the astronaut was shown it
    released_by: Optional[str] = None               # astronaut id, or "automatic"
    crew_message: Optional[str] = None              # what the astronaut sees once it is released


class Mission(BaseModel):
    environment: Environment
    one_way_delay_s: int                         # how long the Ground stream waits (demo-compressed)
    real_one_way_delay_s: Optional[int] = None   # true light time; the verdict uses this

    @model_validator(mode="after")
    def _default_real_delay(self):
        if self.real_one_way_delay_s is None:
            self.real_one_way_delay_s = self.one_way_delay_s
        return self


class MissionView(Mission):
    blackout: bool = False  # PROVISIONAL, read-only here: set it with PUT /mission/blackout


class CheckinRequest(BaseModel):
    timestamp: datetime
    mood_1to5: Optional[int] = None
    sleep_h: Optional[float] = None
    symptoms: Optional[list[str]] = None
    share_with_ground: bool
    # PROVISIONAL (behavioral health): wording in GET /checkin/questions
    phq2: Optional[behavioral.Phq2] = None
    phq9: Optional[behavioral.Phq9] = None          # asked when PHQ-2 >= 2 (two-step screening)
    reaction_test: Optional[behavioral.ReactionTest] = None


class ScenarioRequest(BaseModel):
    astronaut_id: str
    # "strain" is PROVISIONAL: injects a behavioral-health check-in that reaches the urgent level
    scenario: Literal["sleep_debt", "strain", "clear"]


# PROVISIONAL additions (not yet in docs/api-spec.md)

Target = Literal["commander", "deputy", "ground", "self"]
View = Literal["self", "commander", "deputy", "ground"]


class Notice(BaseModel):
    id: str
    astronaut_id: str          # whose wellbeing this is about
    target: Target
    level: behavioral.Level
    reason: Literal["flagged", "released", "auto_released", "safety"]
    alert_id: Optional[str] = None
    areas: list[str]           # e.g. ["mood", "sleep"]: never the answers themselves
    created_at: datetime
    ground_eta_s: Optional[int] = None
    message: str


class Routing(BaseModel):
    routed_to: str             # who sees a psychological flag first on board
    routed_to_name: str
    active_alert_id: Optional[str]
    released: Optional[bool]   # null when no psychological alert is active


class Wellbeing(BaseModel):
    astronaut_id: str
    name: str
    view: View
    mission_day: int
    withheld: bool             # self view before a flag is released: the numbers, not the assessment
    level: Optional[behavioral.Level]
    score: Optional[int]
    rule: Optional[str]        # the safety rule that set the level, if any
    confidence: Literal["high", "medium", "low"]
    coverage: float            # share of the weight that had enough data
    group_points: dict[str, float]
    signals: list[behavioral.Signal]
    phq: Optional[behavioral.PhqResult]
    needs_phq9: bool
    trend: Optional[behavioral.Trend]
    personal_or_shared: str
    suggestions: list[str]
    routing: Routing
    note: str


class CrewMemberWellbeing(BaseModel):
    astronaut_id: str
    name: str
    role: str
    level: behavioral.Level
    score: int
    trend: str
    confidence: str
    unreleased_alert: bool
    visible_because: Literal["commander_first", "shared", "ground"]  # commander_first: not shown to them yet
    areas: list[str] = []              # which areas raised the level; never the answers


class CrewWellbeing(BaseModel):
    view: View
    crew_wide: list[str]       # trends shared by >= 3 crew, without names
    members: list[CrewMemberWellbeing]
    suggestions: list[str]
    note: str


class PsychReportAlert(BaseModel):
    id: str
    profile: str
    severity: Severity
    started_at: datetime
    routed_to: Optional[str]
    released_to_crew_at: Optional[datetime]
    released_by: Optional[str]
    still_active: bool


class PsychReport(BaseModel):
    profile: Wellbeing
    alerts: list[PsychReportAlert]
    crew_context: list[str]
    data_quality: dict[str, int]
    text: str                  # plain-language report, small enough for a congested deep-space link
    size_bytes: int
    method: dict


class LocationNow(BaseModel):
    room: Optional[str]
    room_name: Optional[str]
    since: Optional[datetime]
    source: Literal["beacon", "simulated"]


class LocationView(BaseModel):
    astronaut_id: str
    view: Literal["self", "commander", "doctor", "ground"]
    current: LocationNow
    reason: Optional[str]                        # why someone other than the astronaut may see it
    today_minutes: Optional[dict[str, int]]      # self only: room -> minutes today
    week: Optional[dict[str, Optional[float]]]   # self only: 7-day averages vs usual
    seen_by: Optional[list[dict]]                # self only: who looked, when and why
    note: str


class ConfirmRequest(BaseModel):
    felt: bool
    note: Optional[str] = Field(default=None, max_length=500)


BLACKOUT_REASON = "Solar conjunction: the Sun blocks radio contact with Earth (about 2 weeks on a Mars mission)."


class BlackoutRequest(BaseModel):
    active: bool
    until: Optional[datetime] = None
    reason: str = BLACKOUT_REASON


class Blackout(BaseModel):
    active: bool
    started_at: Optional[datetime] = None
    until: Optional[datetime] = None
    reason: Optional[str] = None
    note: str = ("During a blackout everything on board keeps working: monitoring, alerts, explanations and "
                 "protocols need no link to Earth. Data for Mission Control is held and delivered when "
                 "contact returns.")


class SensorSignal(BaseModel):
    field: str
    status: Literal["ok", "spike", "implausible", "flatline", "dropout"]
    detail: str
    source: Source


class SensorReport(BaseModel):
    astronaut_id: str
    quality: Quality
    signals: list[SensorSignal]
    stored_last_hour: dict[str, int]  # readings stored in the last hour, by quality flag
    events_last_hour: dict[str, int]  # spikes / implausible / flatline / dropout seen in the last hour
    ok_pct_last_hour: Optional[float]
    note: str


class Protocol(BaseModel):
    profile: str
    act_within_s: int
    onboard_action: str
    steps: list[str]
    note: str


class VitalSummary(BaseModel):
    field: str
    label: str
    baseline: float
    average: Optional[float]
    low: Optional[float]
    high: Optional[float]
    deviation_pct: Optional[float]


class ReportAlert(BaseModel):
    id: str
    profile: str
    severity: Severity
    started_at: datetime
    still_active: bool
    astronaut_confirmation: Optional[str]  # pending | felt | not_felt | null
    data_quality: str


class CheckinSummary(BaseModel):
    count: int
    mood_avg: Optional[float]
    headaches: int
    private_not_included: int  # ground view: check-ins the astronaut kept private


class DataQualitySummary(BaseModel):
    readings: int
    ok_pct: Optional[float]
    suspect: int
    sensor_errors: int  # readings the astronaut said they didn't feel
    implausible: int


class TimeToAction(BaseModel):
    alerts_answered: int
    median_response_s: Optional[float]  # alert raised -> astronaut answered "do you feel this?"
    round_trip_to_earth_s: int          # what waiting for Houston would cost instead
    note: str


class Report(BaseModel):
    astronaut_id: str
    name: str
    view: Literal["crew", "ground"]
    generated_at: datetime
    period_days: int
    mission_day: int
    vitals: list[VitalSummary]
    alerts: list[ReportAlert]
    checkins: CheckinSummary
    circadian: Optional[circadian.CircadianSummary]  # null in the ground view if the astronaut opted out
    data_quality: DataQualitySummary
    time_to_action: TimeToAction
    delivery: str
    text: str        # compact plain-language summary, the store-and-forward packet for Mission Control
    size_bytes: int
    note: str


class LightTime(BaseModel):
    environment: Environment
    live_one_way_delay_s: Optional[int]  # Mars today, from NASA JPL Horizons; null if unreachable
    computed_for: Optional[date]
    in_use: bool                         # whether the verdict currently uses the live value
    note: str
    source: str
    source_url: str


class HistoryPoint(BaseModel):
    ts: datetime
    hrv_sdnn_ms: Optional[float] = None
    active_min: Optional[float] = None
    heart_rate_bpm: Optional[float] = None
    spo2_pct: Optional[float] = None
    temp_c: Optional[float] = None
    resp_rate_bpm: Optional[float] = None
    sleep_h_last_night: Optional[float] = None
    mood_1to5: Optional[float] = None
    low: dict[str, Optional[float]] = {}   # lowest reading in the bucket, per field
    high: dict[str, Optional[float]] = {}  # highest reading in the bucket, per field


# --- State -----------------------------------------------------------------------

SEVERITY_RANK = {"watch": 1, "alert": 2, "critical": 3}
WALK_STEP = {"heart_rate_bpm": 1.0, "spo2_pct": 0.2, "temp_c": 0.02, "resp_rate_bpm": 0.3, "hrv_sdnn_ms": 1.0}


class AstronautState:
    def __init__(self, aid: str):
        self.id = aid
        self.name, self.role, cfg = engine.CREW[aid]
        self.configured = Baseline(**cfg)
        self.baseline = self.configured
        self.baseline_stored = False  # True once days 7-14 come from the database
        self.values = {k: float(v) for k, v in cfg.items()}
        self.values["sleep_h_last_night"] = circadian.last_sleep_h(aid)
        self.scenario: Optional[str] = None
        self.real_hr: Optional[tuple[float, float, str]] = None  # watch (bpm, loop time, source)
        self.alerts: list[Alert] = []
        self.active: dict[str, Alert] = {}  # profile -> alert
        self.misses: dict[str, int] = {}    # profile -> consecutive non-matching ticks
        self.manual: dict[str, float] = {}  # sleep/mood from the latest check-in
        self.checkins: list[tuple[str, dict]] = []  # last 14 days, oldest first
        self.sensors = quality.SensorMonitor()
        self.quality: str = "ok"            # quality flag of the latest reading
        self.muted: dict[str, int] = {}     # profile -> calm ticks; astronaut said "I don't feel it"
        # Psychological profile (behavioral.py), recomputed from the stored history every ~60 s.
        self.history: Optional[behavioral.History] = None
        self.profile: Optional[behavioral.Result] = None
        self.trend: Optional[behavioral.Trend] = None
        self.watch_extra: Optional[tuple[Optional[float], Optional[float], float]] = None  # hrv, active, loop t
        # Room from the Bluetooth beacons (location.py)
        self.room: Optional[str] = None
        self.room_since: Optional[datetime] = None
        self.room_source: str = "simulated"
        self.location_seen: list[dict] = []   # who saw the room during an emergency, and why

    def watch_dropout(self) -> bool:
        loop = asyncio.get_running_loop()
        return self.real_hr is not None and loop.time() - self.real_hr[1] >= REAL_HR_FRESH_S

    def target(self, field: str) -> float:
        base = getattr(self.baseline, field) * engine.drift(self.id, mission_day(now())).get(field, 1.0)
        mult = engine.SCENARIO_MULT.get(self.scenario, {}).get(field, 1.0)
        return base * mult

    def sleep_nights(self) -> list[float]:
        if self.scenario == "sleep_debt":
            return list(engine.SCENARIO_SLEEP_NIGHTS_H)
        nights = circadian.recent_sleep_h(self.id, engine.SLEEP_DEBT_NIGHTS)
        if "sleep_h_last_night" in self.manual:
            nights[-1] = self.manual["sleep_h_last_night"]
        return nights

    def tick(self) -> None:
        rate = 0.25 if self.scenario else 0.1  # a scenario shows up within ~30 s
        for field, step in WALK_STEP.items():
            v = self.values[field]
            self.values[field] = v + random.gauss(0, step) + (self.target(field) - v) * rate
        self.values["spo2_pct"] = min(self.values["spo2_pct"], 100.0)
        # Last night's sleep comes from the on-board lighting log unless the check-in says otherwise.
        self.values["sleep_h_last_night"] = self.sleep_nights()[-1]
        mood = engine.SCENARIO_SLEEP_MOOD if self.scenario == "sleep_debt" else self.baseline.mood_1to5
        self.values["mood_1to5"] = self.manual.get("mood_1to5", mood)
        # Active minutes today: builds up over the waking day toward this astronaut's usual total.
        t = now()
        awake = max(0.0, min(1.0, (t.hour * 60 + t.minute - 360) / (16.5 * 60)))
        total = self.baseline.active_min * engine.drift(self.id, mission_day(t)).get("active_min", 1.0)
        self.values["active_min"] = round(total * awake, 1)

    def snapshot(self) -> Vitals:
        v = self.values
        hr, source = v["heart_rate_bpm"], "simulated"
        loop = asyncio.get_running_loop()
        hrv, active = v["hrv_sdnn_ms"], v["active_min"]
        if self.real_hr and loop.time() - self.real_hr[1] < REAL_HR_FRESH_S:
            hr, source = self.real_hr[0], self.real_hr[2]
        if self.watch_extra and loop.time() - self.watch_extra[2] < REAL_HR_FRESH_S:
            hrv = self.watch_extra[0] if self.watch_extra[0] is not None else hrv
            active = self.watch_extra[1] if self.watch_extra[1] is not None else active
        return Vitals(
            timestamp=now(), source=source, baseline=self.baseline,
            heart_rate_bpm=round(hr), spo2_pct=round(v["spo2_pct"]),
            temp_c=round(v["temp_c"], 1), resp_rate_bpm=round(v["resp_rate_bpm"]),
            sleep_h_last_night=round(v["sleep_h_last_night"], 1),
            mood_1to5=max(1, min(5, round(v["mood_1to5"]))), hrv_sdnn_ms=round(hrv),
            active_min=round(active, 1), quality=self.quality)

    def context(self, t: datetime) -> engine.Context:
        return engine.Context(sleep_last_nights=self.sleep_nights(),
                              mood=max(1, min(5, round(self.values["mood_1to5"]))))

    def status(self) -> Status:
        if not self.active:
            return "nominal"
        return max((a.severity for a in self.active.values()), key=SEVERITY_RANK.get)


crew = {aid: AstronautState(aid) for aid in engine.CREW}
# Demo default: Mars, Ground stream compressed to 20 s; the verdict uses the real 22 min.
mission = Mission(environment="mars", one_way_delay_s=20, real_one_way_delay_s=1320)
blackout = Blackout(active=False)
blackout_resumed_at = 0.0  # loop time when the last blackout ended (held ground data waits for it)
mission_start = now() - timedelta(days=DEFAULT_MISSION_DAY - 1)
seeded_until: Optional[str] = None
light_time: dict = {"live_one_way_delay_s": None, "computed_for": None}
subscribers: dict[str, dict[asyncio.Queue, str]] = {aid: {} for aid in crew}  # queue -> "crew" | "ground"
background: set[asyncio.Task] = set()
notices: list[Notice] = []
COMMANDER_ID = next(aid for aid, (_, role, _) in engine.CREW.items() if role == "Commander")
CMO_ID = next(aid for aid, (_, role, _) in engine.CREW.items() if role == "Crew Medical Officer")
# Who gets the commander's own psychological flags. TEAM: confirm; the spec says "the pilot" but the
# crew has no pilot, so the Crew Medical Officer is the default.
DEPUTY_ID = os.getenv("AHM_DEPUTY", CMO_ID)
RELEASE_AFTER_S = int(os.getenv("AHM_RELEASE_AFTER_S", str(12 * 3600)))  # a flag never stays hidden for good


def mission_day(t: datetime) -> int:
    return (t - mission_start).days + 1


def get_state(aid: str) -> AstronautState:
    if aid not in crew:
        raise HTTPException(404, f"Unknown astronaut id '{aid}'")
    return crew[aid]


def publish(aid: str, event: str, model: BaseModel, views: Optional[set[str]] = None) -> None:
    """Send an SSE event to everyone watching this astronaut, or only to the given views."""
    data = model.model_dump_json()
    for q, view in list(subscribers[aid].items()):
        if views and view not in views:
            continue
        try:
            q.put_nowait((event, data))
        except asyncio.QueueFull:
            pass  # slow client: drop rather than block the server


def spawn(coro) -> None:
    task = asyncio.create_task(coro)
    background.add(task)
    task.add_done_callback(background.discard)


# --- Store view (baselines, check-ins) ----------------------------------------

def _round_baseline(b: dict) -> dict:
    return {f: (round(v, 1) if f in ("temp_c", "sleep_h_last_night") else round(v)) for f, v in b.items()}


def _load_store_view(t: datetime) -> dict:
    """Everything the profile needs, read in one go (runs in a thread). Complete days only."""
    w0, w1 = store.iso(mission_start + timedelta(days=6)), store.iso(mission_start + timedelta(days=14))
    today = t.date()
    start_iso = store.iso(mission_start)
    today_iso = store.iso(datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc))
    social = location.daily_social(store.visits_between(start_iso, today_iso),
                                   mission_start.date(), today - timedelta(days=1))
    view = {}
    for aid in crew:
        days: dict[date, behavioral.DayData] = {}
        for dstr, a in store.daily_aggregates(aid, start_iso, today_iso).items():
            days[date.fromisoformat(dstr)] = behavioral.DayData(rhr=a["rhr"], hrv=a["hrv"], active=a["active"],
                                                                sleep=a["sleep"])
        for d, (crew_h, quarters_h) in social[aid].items():
            dd = days.setdefault(d, behavioral.DayData())
            dd.crew_h, dd.quarters_h = crew_h, quarters_h
        view[aid] = dict(baseline=store.baseline(aid, w0, w1), days=days,
                         checkins=store.checkins_between(aid, start_iso))
    return view


async def refresh_from_store() -> None:
    t = now()
    view = await asyncio.to_thread(_load_store_view, t)
    b0, b1 = (mission_start + timedelta(days=6)).date(), (mission_start + timedelta(days=13)).date()
    for aid, d in view.items():
        s = crew[aid]
        s.baseline_stored = d["baseline"] is not None
        base = _round_baseline(d["baseline"]) if s.baseline_stored else s.configured.model_dump()
        acts = [x.active for day, x in d["days"].items() if b0 <= day <= b1 and x.active is not None]
        if acts:
            base["active_min"] = round(statistics.fmean(acts))  # a usual whole day, not a mid-day counter
        s.baseline = Baseline(**base)
        newest = d["checkins"][-1][0] if d["checkins"] else ""
        s.checkins = d["checkins"] + [c for c in s.checkins if c[0] > newest]  # keep any not yet read back
        s.history = behavioral.History(days=d["days"], checkins=s.checkins, mission_start=mission_start.date())
    await asyncio.to_thread(compute_profiles, t)


# --- Psychological profile (behavioral.py) ---------------------------------------------

CREW_WIDE_TEXT = {
    "sleep": "is sleeping less than usual",
    "body_clock": "has irregular or drifting bedtimes",
    "hrv": "has a lower heart-rate variability than usual",
    "activity": "is less active than usual",
    "social_time": "is spending less time with crewmates than usual",
    "mood": "reports a lower mood than usual",
    "reaction_time": "has slower reaction times than usual",
    "resting_heart_rate": "has a higher resting heart rate than usual",
}  # PHQ answers are never aggregated: too personal even without names
LEVEL_PROFILE = {"concern": "wellbeing_concern", "urgent": "wellbeing_urgent"}
crew_counts: dict[str, int] = {}


def compute_profiles(t: datetime) -> None:
    """Profile and trend for every astronaut (runs in a thread). Today's check-ins count."""
    global crew_counts
    yesterday = t.date() - timedelta(days=1)
    results = {}
    for aid, s in crew.items():
        if s.history is None:
            continue
        s.history.checkins = s.checkins
        s.history.body_clock_status = circadian.assess(aid, t, mission.environment).summary.status
        results[aid] = behavioral.compute(s.history, yesterday, live=True)
    crew_counts = behavioral.mark_crew_wide(results)
    for aid, r in results.items():
        crew[aid].profile = r
        crew[aid].trend = behavioral.trend(crew[aid].history, t.date(), r)


def routed_to(aid: str) -> str:
    return DEPUTY_ID if aid == COMMANDER_ID else COMMANDER_ID


def psych_alerts(s: AstronautState, active_only: bool = True) -> list[Alert]:
    pool = s.active.values() if active_only else s.alerts
    return [a for a in pool if a.psychological]


def withheld_for_self(s: AstronautState) -> bool:
    return any(a.released_to_crew_at is None for a in psych_alerts(s))


def personal_or_shared(signals: list[behavioral.Signal]) -> str:
    raised = [x for x in signals if x.severity >= 0.5]
    if not raised:
        return "Nothing stands out."
    shared = sorted({x.area for x in raised if x.crew_wide})
    personal = sorted({x.area for x in raised if not x.crew_wide})
    parts = []
    if shared:
        parts.append(f"Shared with most of the crew: {', '.join(shared)} (likely the schedule or environment).")
    if personal:
        parts.append(f"Personal: {', '.join(personal)}.")
    return " ".join(parts)


def wellbeing_view(s: AstronautState, view: str, t: datetime) -> Wellbeing:
    r = s.profile
    if r is None:
        raise HTTPException(503, "The profile is not ready yet; try again in a minute.")
    withheld = view == "self" and withheld_for_self(s)
    top = max(psych_alerts(s), key=lambda a: SEVERITY_RANK[a.severity], default=None)
    to = routed_to(s.id)
    routing = Routing(routed_to=to, routed_to_name=crew[to].name, active_alert_id=top.id if top else None,
                      released=(top.released_to_crew_at is not None) if top else None)
    signals = r.signals
    if withheld:  # the astronaut's own numbers stay visible; the assessment waits for the release
        signals = [x.model_copy(update=dict(z=None, severity=0.0, points=0.0, trend="unknown", crew_wide=False))
                   for x in r.signals]
    return Wellbeing(
        astronaut_id=s.id, name=s.name, view=view, mission_day=mission_day(t), withheld=withheld,
        level=None if withheld else r.level, score=None if withheld else r.score,
        rule=None if withheld else r.rule, confidence=r.confidence, coverage=r.coverage,
        group_points={} if withheld else r.group_points, signals=signals, phq=r.phq, needs_phq9=r.needs_phq9,
        trend=None if withheld else s.trend,
        personal_or_shared="" if withheld else personal_or_shared(r.signals),
        suggestions=(["Keep your check-ins going so changes are easy to spot."] if withheld
                     else behavioral.suggestions_for(r)),
        routing=routing,
        note="Decision support only, never a diagnosis. Each input is compared with your own mission days "
             "7-14; PHQ uses its validated cut-offs. GET /wellbeing/method shows every weight.")


def _area_list(r: Optional[behavioral.Result], profile: str) -> list[str]:
    if r is None or profile == "sleep_debt":
        return ["sleep"]
    return sorted({x.area for x in r.signals if x.severity >= 0.5}) or ["general"]


def send_notice(s: AstronautState, target: str, level: str, reason: str, alert: Alert, areas: list[str]) -> None:
    area_text = ", ".join(areas)
    first = crew[alert.routed_to].name if alert.routed_to else "the commander"
    if reason == "flagged" and target == "ground":
        message = (f"{s.name}'s wellbeing check is at '{level}' (areas: {area_text}). {first} has it first "
                   f"on board.")
    elif reason == "flagged":
        role = "As deputy for the commander's own wellbeing" if target == "deputy" else "As commander"
        message = (f"{s.name}'s wellbeing check is at '{level}' (areas: {area_text}). They haven't been shown "
                   f"it yet. {role}, talk with them privately, then release it to them.")
    else:
        message = alert.crew_message or "Your commander shared a wellbeing check with you."
        if reason == "auto_released":
            message += " (Shared with you automatically: a flag never stays hidden.)"
    n = Notice(id=f"nt-{uuid.uuid4().hex[:8]}", astronaut_id=s.id, target=target, level=level, reason=reason,
               alert_id=alert.id, areas=areas, created_at=now(),
               ground_eta_s=ground_eta_s() if target == "ground" else None, message=message)
    notices.append(n)
    store.save_notice(n.model_dump(mode="json"))
    if target == "ground":
        publish(s.id, "notice", n, views={"ground"})               # delayed, and held during a blackout
    elif target in ("commander", "deputy"):
        publish(alert.routed_to, "notice", n, views={"crew"})      # their own console
    else:
        publish(s.id, "notice", n, views={"crew"})                 # the astronaut themselves
    log.info("%s: wellbeing notice to %s (%s, %s)", s.id, target, level, reason)


def release_alert(s: AstronautState, alert: Alert, by: str, reason: str = "released") -> None:
    alert.released_to_crew_at = now()
    alert.released_by = by
    store.update_alert(alert.model_dump(mode="json"))
    publish(s.id, "alert", alert)  # now on every view, the astronaut's included
    level = s.profile.level if s.profile else "watch"
    send_notice(s, "self", level, reason, alert, _area_list(s.profile, alert.profile))
    log.info("%s: %s released to the astronaut by %s", s.id, alert.profile, by)


def psych_insight(s: AstronautState, profile: str, r: behavioral.Result) -> Insight:
    """Built on board from the profile: psychological data is never sent to a cloud model."""
    p = engine.PROFILES[profile]
    top = sorted((x for x in r.signals if x.points > 0), key=lambda x: -x.points)[:3]
    why = f"{s.name}'s wellbeing check is at '{r.level}' (score {r.score}/100, confidence {r.confidence})."
    if r.rule:
        why += f" {r.rule}"
    trend = " ".join(x.detail for x in top) or "Several small changes added up."
    if s.trend and s.trend.direction != "unknown" and s.trend.points_per_week is not None:
        trend += f" Over the last 2 weeks the score is {s.trend.direction} ({s.trend.points_per_week:+.0f} a week)."
    left = blackout_left_s()
    delay = mission.real_one_way_delay_s
    if left is not None:
        verdict = "Earth is out of contact (blackout): act on board; Mission Control gets this when contact returns."
    elif engine.acts_on_board(p["act_within_s"], delay):
        verdict = f"A reply from Mission Control takes about {2 * delay / 60:.0f} min, so the first step is on board."
    else:
        verdict = f"Mission Control will see this in about {delay / 60:.0f} min."
    return Insight(why=why, trend=trend, recommended_action=f"{p['onboard_action']} {verdict}")


def evaluate_wellbeing(t: datetime) -> None:
    """Raise, escalate or clear psychological alerts from each profile (concern and urgent only)."""
    for s in crew.values():
        r = s.profile
        if r is None:
            continue
        want = LEVEL_PROFILE.get(r.level)
        current = [a.profile for a in psych_alerts(s) if a.profile in LEVEL_PROFILE.values()]
        rank = {"wellbeing_concern": 1, "wellbeing_urgent": 2}
        if want and (not current or rank[want] > max(rank[c] for c in current)):
            for c in current:
                clear_alert(s, c)
            v = s.snapshot().model_dump(include=set(store.VITAL_FIELDS))
            raise_alert(s, want, v, s.context(t), profile_result=r)
        elif not want:
            for c in current:
                clear_alert(s, c)
        # A flag never stays hidden for good: release it automatically after RELEASE_AFTER_S.
        for a in psych_alerts(s, active_only=False):
            if a.released_to_crew_at is None and (t - a.started_at).total_seconds() >= RELEASE_AFTER_S:
                release_alert(s, a, "automatic", "auto_released")


# --- Alerts ------------------------------------------------------------------------

def blackout_left_s() -> Optional[float]:
    """None when Earth is reachable; seconds of blackout left otherwise (0 = end unknown)."""
    if not blackout.active:
        return None
    return max(0.0, (blackout.until - now()).total_seconds()) if blackout.until else 0.0


def ground_eta_s() -> int:
    """When Mission Control will see something sent now: light time, plus any blackout left."""
    return int(mission.real_one_way_delay_s + (blackout_left_s() or 0))


async def attach_insight(s: AstronautState, alert: Alert, v: dict, ctx: engine.Context) -> None:
    # The same alert id is re-sent with insight filled in (null until then).
    b = s.baseline.model_dump()
    left = blackout_left_s()
    fallback = insight_service.Insight(**engine.fallback_insight(
        alert.profile, v, b, ctx, mission.real_one_way_delay_s, left))
    if left is not None:
        result = fallback  # no link to Earth, so no cloud model: the on-board explanation is used
    else:
        result = await insight_service.generate_insight(
            alert.profile, v, b, onboard_action=alert.onboard_action,
            act_within_s=alert.act_within_s, one_way_delay_s=mission.real_one_way_delay_s, fallback=fallback)
    alert.insight = Insight(**result.model_dump())
    store.set_insight(alert.model_dump(mode="json"))
    publish_alert(s, alert)


def publish_alert(s: AstronautState, alert: Alert) -> None:
    """An unreleased psychological alert goes to Mission Control's view only, never the astronaut's."""
    hidden = alert.psychological and alert.released_to_crew_at is None
    publish(s.id, "alert", alert, views={"ground"} if hidden else None)


def raise_alert(s: AstronautState, profile: str, v: dict, ctx: engine.Context,
                profile_result: Optional[behavioral.Result] = None) -> Alert:
    p = engine.PROFILES[profile]
    psych = profile in engine.PSYCHOLOGICAL
    question = engine.CONFIRM_QUESTIONS.get(profile)
    alert = Alert(
        id=f"al-{uuid.uuid4().hex[:8]}", astronaut_id=s.id, profile=profile,
        severity=p["severity"], hazard=p["hazard"], body_region=p["body_region"],
        started_at=now(), onboard_action=p["onboard_action"], act_within_s=p["act_within_s"],
        ground_eta_s=ground_eta_s(), insight=None,
        data_quality="suspect" if s.quality == "suspect" else "ok",
        confirmation=Confirmation(status="pending", question=question) if question else None,
        psychological=psych, routed_to=routed_to(s.id) if psych else None,
        crew_message=engine.CREW_MESSAGE.get(profile) if psych else None)
    if profile_result is not None:
        alert.insight = psych_insight(s, profile, profile_result)
    s.alerts.append(alert)
    s.active[profile] = alert
    s.misses[profile] = 0
    store.save_alert(alert.model_dump(mode="json"))
    publish_alert(s, alert)
    log.info("%s: %s alert raised%s", s.id, profile, f" (to {alert.routed_to} first)" if psych else "")
    if psych:
        r = profile_result or s.profile
        level, areas = (r.level if r else "watch"), _area_list(r, profile)
        send_notice(s, "deputy" if s.id == COMMANDER_ID else "commander", level, "flagged", alert, areas)
        send_notice(s, "ground", level, "flagged", alert, areas)
        if profile_result is not None and profile_result.rule and "question 9" in profile_result.rule:
            release_alert(s, alert, "automatic", "safety")  # safety: the astronaut is not left alone with it
    if profile_result is None:
        spawn(attach_insight(s, alert, v, ctx))
    return alert


def clear_alert(s: AstronautState, profile: str) -> None:
    alert = s.active.pop(profile, None)
    s.misses.pop(profile, None)
    if alert:
        store.clear_alert(alert.id, store.iso(now()))
        log.info("%s: %s alert cleared", s.id, profile)


def evaluate_vitals(s: AstronautState, snap: Vitals, t: datetime) -> bool:
    """Run the vitals profiles. Returns True if a profile the astronaut said they don't feel still matches."""
    if s.quality == "implausible":
        return False  # a reading no body can produce never raises or clears an alert
    v = snap.model_dump(include=set(store.VITAL_FIELDS))
    b = s.baseline.model_dump()
    ctx = s.context(t)
    muted_match = False
    for profile in engine.VITALS_PROFILES:
        if engine.matches(profile, v, b, ctx):
            s.misses[profile] = 0
            if profile in s.muted:
                s.muted[profile] = 0
                muted_match = True
            elif profile not in s.active:  # the NEW-match gate
                raise_alert(s, profile, v, ctx)
        else:
            if profile in s.muted:  # unmute once readings have been calm for a while
                s.muted[profile] += 1
                if s.muted[profile] >= engine.CLEAR_AFTER_TICKS:
                    del s.muted[profile]
            if profile in s.active:
                s.misses[profile] = s.misses.get(profile, 0) + 1
                if s.misses[profile] >= engine.CLEAR_AFTER_TICKS:
                    clear_alert(s, profile)
    return muted_match


# --- Background loops ------------------------------------------------------------

async def tick_loop() -> None:
    ticks = 0
    while True:
        await asyncio.sleep(TICK_S)
        try:
            t = now()
            if blackout.active and blackout.until and t >= blackout.until:
                end_blackout()
            for aid, s in crew.items():
                s.tick()
                snap = s.snapshot()
                v = snap.model_dump(include=set(store.VITAL_FIELDS))
                s.quality, _ = s.sensors.check(v, snap.source, s.watch_dropout())
                muted_match = evaluate_vitals(s, snap, t)
                if muted_match and s.quality == "ok":
                    s.quality = "suspect"  # the same episode the astronaut said they don't feel
                snap.quality = s.quality
                store.add_sample(aid, store.iso(t), v, snap.source, s.quality)
                publish(aid, "vitals", snap)
                room, src = location.current_room(aid, t, mission_day(t), asyncio.get_running_loop().time())
                if room != s.room:
                    store.open_visit(aid, room, store.iso(t), src)
                    s.room, s.room_since = room, t
                s.room_source = src
            ticks += 1
            if ticks % 10 == 0:  # real ISS cabin data into every stream, ~30 s
                env = CabinEnvironment(**iss_live.snapshot())
                for aid in crew:
                    publish(aid, "environment", env)
            if ticks % REFRESH_EVERY_TICKS == 0:
                await refresh_from_store()
                evaluate_wellbeing(t)
        except Exception:
            log.exception("tick failed; carrying on")  # the demo must keep running


def end_blackout() -> None:
    global blackout, blackout_resumed_at
    if blackout.active:
        blackout_resumed_at = asyncio.get_running_loop().time()
        log.info("Blackout over: contact with Earth restored; held data is being delivered")
    blackout = Blackout(active=False)


async def fetch_light_time() -> None:
    today = now().date()
    value = await horizons.mars_one_way_light_time_s(today)
    if value is None:
        return
    light_time.update(live_one_way_delay_s=value, computed_for=today)
    log.info("JPL Horizons: Earth-Mars one-way light time today %d s (%.1f min)", value, value / 60)
    if LIVE_LIGHT_TIME and mission.environment == "mars":
        mission.real_one_way_delay_s = value


async def load_alerts() -> None:
    for alert_dict, cleared_at in await asyncio.to_thread(store.load_alerts):
        s = crew.get(alert_dict.get("astronaut_id"))
        if s is None:
            continue
        try:
            alert = Alert(**alert_dict)
        except Exception:
            continue  # e.g. a profile cut from the spec since it was stored
        s.alerts.append(alert)
        if cleared_at is None:
            s.active[alert.profile] = alert  # keeps the NEW-match gate across restarts


@asynccontextmanager
async def lifespan(app: FastAPI):
    global mission_start, seeded_until
    await asyncio.to_thread(store.init)
    store.start_writer()
    iss_live.start()  # real cabin data from NASA ISS Live; never blocks
    stored_start = await asyncio.to_thread(store.meta_get, "mission_start")
    if stored_start:
        mission_start = datetime.fromisoformat(stored_start)
    seeded_until = await asyncio.to_thread(store.meta_get, "seeded_until")
    await load_alerts()
    await refresh_from_store()
    for s in crew.values():
        log.info("%s baseline: %s", s.id, "stored mission days 7-14" if s.baseline_stored
                 else "configured (run tools/simulate_crew.py --seed-baseline)")
    t = now()
    # Psychological profile: notices back from the database, open room stays closed at restart,
    # then today's levels (restored alerts keep the new-match gate, so nothing is re-sent).
    for n in await asyncio.to_thread(store.load_notices):
        try:
            notices.append(Notice(**n))
        except Exception:
            continue
    await asyncio.to_thread(store.close_open_visits, store.iso(t))
    evaluate_wellbeing(t)
    spawn(tick_loop())
    spawn(fetch_light_time())
    yield
    for task in list(background):
        task.cancel()
    iss_live.stop()
    store.stop_writer()


app = FastAPI(title="Dr. Galactic backend", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# --- Endpoints -----------------------------------------------------------------

@app.get("/")
async def root() -> dict:
    return {"service": "Dr. Galactic backend (astronaut-health-monitor)", "docs": "/docs"}


@app.get("/crew")
async def get_crew() -> list[CrewMember]:
    return [CrewMember(id=s.id, name=s.name, role=s.role, status=s.status()) for s in crew.values()]


@app.post("/astronauts/{aid}/ingest", status_code=202)
async def ingest(aid: str, body: IngestRequest) -> Accepted:
    state = get_state(aid)
    loop_t = asyncio.get_running_loop().time()
    state.real_hr = (body.heart_rate_bpm, loop_t, body.source)
    state.values["heart_rate_bpm"] = body.heart_rate_bpm
    if body.hrv_sdnn_ms is not None or body.active_min is not None:
        state.watch_extra = (body.hrv_sdnn_ms, body.active_min, loop_t)
    return Accepted()


@app.get("/astronauts/{aid}/vitals")
async def get_vitals(aid: str) -> Vitals:
    return get_state(aid).snapshot()


def sse(event: str, data: str) -> str:
    return f"event: {event}\ndata: {data}\n\n"


async def event_stream(request: Request, aid: str, view: str):
    loop = asyncio.get_running_loop()
    q: asyncio.Queue = asyncio.Queue(maxsize=1000)
    subscribers[aid][q] = view
    pending: deque = deque()  # (release_at, event, data); ground view holds events back
    try:
        yield f": connected view={view} one_way_delay_s={mission.one_way_delay_s}\n\n"
        if view == "crew":
            yield sse("vitals", crew[aid].snapshot().model_dump_json())
        elif blackout.active:
            yield ": blackout - Earth is out of contact; data is held until contact returns\n\n"
        while not await request.is_disconnected():
            # Blackout (store-and-forward): the ground view holds everything until contact returns,
            # keeping every alert but only the latest vitals; after that, data still takes the light time.
            held = view == "ground" and blackout.active
            resume_at = blackout_resumed_at + mission.one_way_delay_s if view == "ground" else 0.0
            timeout = 15.0
            if pending and not held:
                timeout = max(0.0, min(timeout, max(pending[0][0], resume_at) - loop.time()))
            try:
                event, data = await asyncio.wait_for(q.get(), timeout)
                if held and event == "vitals":
                    pending = deque(p for p in pending if p[1] != "vitals")
                delay = mission.one_way_delay_s if view == "ground" else 0
                pending.append((loop.time() + delay, event, data))
            except asyncio.TimeoutError:
                if held:
                    yield ": blackout\n\n"
                elif not pending:
                    yield ": keepalive\n\n"
            if held:
                continue
            while pending and pending[0][0] <= loop.time() and loop.time() >= resume_at:
                _, event, data = pending.popleft()
                yield sse(event, data)
    finally:
        subscribers[aid].pop(q, None)


@app.get("/astronauts/{aid}/stream")
async def stream(aid: str, request: Request, view: Literal["crew", "ground"] = "crew"):
    get_state(aid)
    return StreamingResponse(
        event_stream(request, aid, view), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/astronauts/{aid}/alerts")
async def get_alerts(aid: str, viewer: Optional[str] = None) -> list[Alert]:
    """Newest first. With viewer = the astronaut themselves, unreleased psychological alerts are left out."""
    s = get_state(aid)
    alerts = s.alerts
    if viewer == aid:
        alerts = [a for a in alerts if not (a.psychological and a.released_to_crew_at is None)]
    return list(reversed(alerts))


@app.put("/astronauts/{aid}/alerts/{alert_id}/release")
async def release(aid: str, alert_id: str, viewer: str) -> Alert:
    """PROVISIONAL. The commander (or the deputy, for the commander's own flags) shows a
    psychological alert to the astronaut, ideally after talking with them in private."""
    s = get_state(aid)
    alert = next((a for a in s.alerts if a.id == alert_id), None)
    if alert is None:
        raise HTTPException(404, f"No alert '{alert_id}' for {aid}")
    if not alert.psychological:
        raise HTTPException(409, "Only psychological alerts are released; this one is already shown to everyone.")
    if viewer != alert.routed_to:
        raise HTTPException(403, f"Only {crew[alert.routed_to].name}, who has it first on board, can release it.")
    if alert.released_to_crew_at is None:
        release_alert(s, alert, viewer)
    return alert


@app.post("/astronauts/{aid}/alerts/{alert_id}/confirm")
async def confirm_alert(aid: str, alert_id: str, body: ConfirmRequest) -> Alert:
    # PROVISIONAL. "Do you feel this?" Sensors aren't right 100% of the time; if the astronaut
    # doesn't feel it, the readings around the alert are marked as a likely sensor error in their
    # history (kept, never deleted) and left out of the baseline, charts and reports.
    s = get_state(aid)
    alert = next((a for a in s.alerts if a.id == alert_id), None)
    if alert is None:
        raise HTTPException(404, f"No alert '{alert_id}' for {aid}")
    if alert.confirmation is None:
        raise HTTPException(409, "This alert comes from the astronaut's own check-in, so there is nothing to confirm.")
    t = now()
    alert.confirmation = Confirmation(status="felt" if body.felt else "not_felt",
                                      question=alert.confirmation.question, answered_at=t, note=body.note)
    if not body.felt:
        store.mark_artifact(aid, store.iso(alert.started_at - timedelta(minutes=2)), store.iso(t))
        if s.active.get(alert.profile) is alert:
            clear_alert(s, alert.profile)
        s.muted[alert.profile] = 0  # don't re-raise this episode; unmutes after readings calm down
    store.update_alert(alert.model_dump(mode="json"))
    publish(aid, "alert", alert)  # same id, re-sent with the answer
    return alert


@app.get("/mission")
async def get_mission() -> MissionView:
    return MissionView(**mission.model_dump(), blackout=blackout.active)


@app.put("/mission")
async def put_mission(body: Mission) -> MissionView:
    global mission
    mission = body
    return MissionView(**mission.model_dump(), blackout=blackout.active)


@app.get("/mission/blackout")
async def get_blackout() -> Blackout:  # PROVISIONAL
    return blackout


@app.put("/mission/blackout")
async def put_blackout(body: BlackoutRequest) -> Blackout:
    # PROVISIONAL. Communications blackout (e.g. solar conjunction): everything on board keeps
    # working; the ground view holds data and delivers it when contact returns.
    global blackout
    if body.active:
        blackout = Blackout(active=True, started_at=now(), until=body.until, reason=body.reason)
        log.info("Blackout started: %s", body.reason)
    else:
        end_blackout()
    return blackout


async def record_checkin(s: AstronautState, body: CheckinRequest) -> None:
    ts = store.iso(body.timestamp)
    payload = body.model_dump(mode="json", exclude_none=True)
    await asyncio.to_thread(store.add_checkin, s.id, ts, payload)
    s.checkins = sorted(s.checkins + [(ts, payload)], key=lambda c: c[0])
    if body.mood_1to5 is not None:
        s.manual["mood_1to5"] = body.mood_1to5
    if body.sleep_h is not None:
        s.manual["sleep_h_last_night"] = body.sleep_h
    await asyncio.to_thread(compute_profiles, now())  # a single check-in can change the profile
    evaluate_wellbeing(now())


@app.post("/astronauts/{aid}/checkin", status_code=202)
async def checkin(aid: str, body: CheckinRequest) -> Accepted:
    await record_checkin(get_state(aid), body)
    return Accepted()


@app.post("/debug/scenario", status_code=202)
async def debug_scenario(body: ScenarioRequest) -> Accepted:
    # Dev only. The stage fallback if the watch misbehaves.
    s = get_state(body.astronaut_id)
    if body.scenario == "clear":
        s.scenario = None
        s.manual.clear()
        s.muted.clear()
        # Snap vitals back to baseline so leftover drift can't raise a stray alert after a demo run.
        s.values.update({f: float(getattr(s.baseline, f)) for f in WALK_STEP})
        s.sensors.prev = {}
        for profile in list(s.active):
            clear_alert(s, profile)
        if seeded_until:  # drop live check-ins so the wellbeing demo can run again
            await asyncio.to_thread(store.delete_checkins_after, s.id, seeded_until)
            s.checkins = [c for c in s.checkins if c[0] <= seeded_until]
        await asyncio.to_thread(compute_profiles, now())
        evaluate_wellbeing(now())
    elif body.scenario == "strain":
        # Same path as a real check-in, kept PRIVATE: strong PHQ-2, low mood and a slow reaction test,
        # enough to reach "urgent", so the automatic notification can be shown.
        rts = [p["reaction_test"] for _, p in s.checkins if p.get("reaction_test")]
        rt = statistics.fmean(x["mean_rt_ms"] for x in rts) if rts else 260.0
        lapses = statistics.fmean(x["lapses"] for x in rts) if rts else 1.0
        await record_checkin(s, CheckinRequest(
            timestamp=now(), mood_1to5=1, share_with_ground=False,
            phq2=behavioral.Phq2(little_interest=3, feeling_down=3),
            reaction_test=behavioral.ReactionTest(mean_rt_ms=round(rt * 1.4), lapses=round(lapses) + 6)))
    else:
        s.scenario = body.scenario
        s.manual.clear()
    return Accepted()


# --- PROVISIONAL: sensor accuracy, protocols, reports (not yet in docs/api-spec.md) ---

SENSOR_NOTE = ("Sensors are not right 100% of the time. Every reading is checked for impossible values, "
               "sudden jumps, a stuck sensor and watch dropouts. Suspicious readings are kept but flagged, "
               "and a vitals alert asks whether you actually feel it. Readings you say you didn't feel are "
               "marked as sensor errors in your history (never deleted) and left out of your baseline, "
               "charts and reports.")
VITAL_LABELS = {"heart_rate_bpm": "Heart rate (bpm)", "spo2_pct": "SpO2 (%)", "temp_c": "Temperature (°C)",
                "resp_rate_bpm": "Breathing (/min)", "sleep_h_last_night": "Sleep (h)", "mood_1to5": "Mood (1-5)",
                "hrv_sdnn_ms": "Heart-rate variability (ms)", "active_min": "Active minutes today"}
QUALITY_FLAGS = ("ok", "suspect", "implausible", "artifact")


@app.get("/astronauts/{aid}/sensors")
async def get_sensors(aid: str) -> SensorReport:
    s = get_state(aid)
    counts = await asyncio.to_thread(store.quality_counts, aid, store.iso(now() - timedelta(hours=1)))
    stored = {flag: counts.get(flag, 0) for flag in QUALITY_FLAGS}
    total = sum(stored.values())
    return SensorReport(
        astronaut_id=aid, quality=s.quality,
        signals=[SensorSignal(field=c.field, status=c.status, detail=c.detail, source=c.source)
                 for c in s.sensors.last_checks],
        stored_last_hour=stored, events_last_hour=dict(s.sensors.recent_counts()),
        ok_pct_last_hour=round(100 * stored["ok"] / total, 1) if total else None, note=SENSOR_NOTE)


@app.get("/protocols")
async def get_protocols() -> list[Protocol]:
    # Works with no link to Earth: what to do on board when help is late or unreachable.
    return [Protocol(profile=p, act_within_s=engine.PROFILES[p]["act_within_s"],
                     onboard_action=engine.PROFILES[p]["onboard_action"], steps=steps,
                     note="Suggested steps for the demo; check against the onboard medical checklist. "
                          "Not medical advice.")
            for p, steps in engine.PROTOCOLS.items()]


def _report_text(s: AstronautState, days: int, t: datetime, vitals: list[VitalSummary],
                 alerts: list[ReportAlert], ck: CheckinSummary,
                 circ: Optional[circadian.CircadianSummary], dq: DataQualitySummary, view: str,
                 tta: TimeToAction) -> str:
    lines = [f"Health report: {s.name} ({s.id}), mission day {mission_day(t)}, last {days} days.",
             "Compared with the astronaut's own baseline (mission days 7-14):"]
    for vs in vitals:
        if vs.average is not None and vs.field != "mood_1to5":
            dev = f" ({vs.deviation_pct:+.0f}%)" if vs.deviation_pct is not None else ""
            lines.append(f"- {vs.label}: avg {vs.average:g} vs baseline {vs.baseline:g}{dev}, "
                         f"range {vs.low:g}-{vs.high:g}")
    if alerts:
        lines.append(f"Alerts ({len(alerts)}):")
        answer = {"felt": "astronaut felt it", "not_felt": "astronaut did not feel it, marked as a likely "
                  "sensor error and excluded", "pending": "not answered yet", None: "from check-ins"}
        for a in alerts:
            lines.append(f"- {a.started_at:%d %b %H:%M} {a.profile} ({a.severity}): {answer[a.astronaut_confirmation]}"
                         + ("; sensor glitch seen at the time" if a.data_quality == "suspect" else ""))
    else:
        lines.append("Alerts: none.")
    mood = f", mood avg {ck.mood_avg:.1f}/5" if ck.mood_avg is not None else ""
    lines.append(f"Check-ins: {ck.count}{mood}, headaches {ck.headaches}"
                 + (f"; {ck.private_not_included} kept private" if ck.private_not_included else "") + ".")
    if circ:
        lines.append(f"Sleep and light: avg {circ.sleep_avg_h} h, bedtime spread {circ.bedtime_spread_min / 60:.1f} h, "
                     f"drift {circ.drift_min_per_night:+.0f} min/night, status {circ.status}.")
    elif view == "ground":
        lines.append("Sleep and light: not shared by the astronaut.")
    if tta.median_response_s is not None:
        lines.append(f"Time to action: the astronaut answered {tta.alerts_answered} alert(s) in a median of "
                     f"{tta.median_response_s:.0f} s, vs a {tta.round_trip_to_earth_s / 60:.0f}-min round trip to Earth.")
    if dq.readings:
        lines.append(f"Data quality: {dq.ok_pct:.1f}% of {dq.readings} readings OK; {dq.sensor_errors} marked as "
                     f"sensor errors by the astronaut, {dq.suspect} flagged as suspect, {dq.implausible} impossible "
                     f"values ignored.")
    lines.append("Decision support only, never a diagnosis.")
    return "\n".join(lines)


@app.get("/astronauts/{aid}/report")
async def get_report(aid: str, days: int = Query(7, ge=1, le=42),
                     view: Literal["crew", "ground"] = "crew") -> Report:
    """The astronaut's history as one compact report: the store-and-forward packet for Mission Control."""
    s = get_state(aid)
    t = now()
    since = store.iso(t - timedelta(days=days))
    stats, counts, checks = await asyncio.gather(
        asyncio.to_thread(store.period_stats, aid, since),
        asyncio.to_thread(store.quality_counts, aid, since),
        asyncio.to_thread(store.checkins_between, aid, since))
    b = s.baseline.model_dump()
    vitals = []
    for f, st in stats.items():
        avg = round(st["avg"], 1) if st["avg"] is not None else None
        vitals.append(VitalSummary(
            field=f, label=VITAL_LABELS[f], baseline=b[f], average=avg,
            low=round(st["min"], 1) if st["min"] is not None else None,
            high=round(st["max"], 1) if st["max"] is not None else None,
            deviation_pct=round(100 * engine.pct(avg, b[f]), 1) if avg is not None else None))
    alerts = [ReportAlert(id=a.id, profile=a.profile, severity=a.severity, started_at=a.started_at,
                          still_active=s.active.get(a.profile) is a,
                          astronaut_confirmation=a.confirmation.status if a.confirmation else None,
                          data_quality=a.data_quality)
              for a in s.alerts if store.iso(a.started_at) >= since]
    private = [c for c in checks if not c[1].get("share_with_ground")]
    if view == "ground":
        checks = [c for c in checks if c[1].get("share_with_ground")]
    moods = [p["mood_1to5"] for _, p in checks if p.get("mood_1to5") is not None]
    ck = CheckinSummary(
        count=len(checks), mood_avg=round(statistics.fmean(moods), 1) if moods else None,
        headaches=sum("headache" in (p.get("symptoms") or []) for _, p in checks),
        private_not_included=len(private) if view == "ground" else 0)
    circ = None if (view == "ground" and not circadian.is_shared(aid)) else \
        circadian.assess(aid, t, mission.environment).summary
    readings = sum(counts.values())
    dq = DataQualitySummary(
        readings=readings, ok_pct=round(100 * counts.get("ok", 0) / readings, 1) if readings else None,
        suspect=counts.get("suspect", 0), sensor_errors=counts.get("artifact", 0),
        implausible=counts.get("implausible", 0))
    answered = [(a.confirmation.answered_at - a.started_at).total_seconds() for a in s.alerts
                if store.iso(a.started_at) >= since and a.confirmation and a.confirmation.answered_at]
    tta = TimeToAction(
        alerts_answered=len(answered),
        median_response_s=round(statistics.median(answered), 1) if answered else None,
        round_trip_to_earth_s=2 * mission.real_one_way_delay_s,
        note="Seconds from an alert to the astronaut's answer, compared with waiting for a reply from Earth.")
    text = _report_text(s, days, t, vitals, alerts, ck, circ, dq, view, tta)
    size = len(text.encode("utf-8"))
    left = blackout_left_s()
    if left is not None:
        delivery = (f"Communications blackout: saved on board ({size} bytes); it reaches Mission Control about "
                    f"{mission.real_one_way_delay_s / 60:.0f} min after contact returns.")
    else:
        delivery = f"Reaches Mission Control about {mission.real_one_way_delay_s / 60:.0f} min after sending ({size} bytes)."
    return Report(
        astronaut_id=aid, name=s.name, view=view, generated_at=t, period_days=days, mission_day=mission_day(t),
        vitals=vitals, alerts=alerts, checkins=ck,
        circadian=circ, data_quality=dq, time_to_action=tta, delivery=delivery, text=text, size_bytes=size,
        note="Built from the stored history. Readings the astronaut marked as sensor errors are left out.")


# --- PROVISIONAL: history, live light time (not yet in docs/api-spec.md) ---

@app.get("/astronauts/{aid}/history")
async def get_history(aid: str, hours: float = Query(24, gt=0, le=24 * 60),
                      bucket_s: Optional[int] = Query(None, ge=TICK_S, le=86400)) -> list[HistoryPoint]:
    """Average, low and high per bucket. bucket_s=3600 gives hour-by-hour."""
    get_state(aid)
    bucket_s = bucket_s or max(TICK_S, int(hours * 3600 / 300))  # default: at most ~300 points per chart
    rows = await asyncio.to_thread(store.history, aid, store.iso(now() - timedelta(hours=hours)), bucket_s)
    return [HistoryPoint(**r) for r in rows]


# --- PROVISIONAL: psychological profile, report, location ------------------------------
# `viewer` is who is looking: their astronaut id, or "ground". The web login decides it;
# this is a demo-level check, not security (docs/api-spec.md: "Auth: none").

def _view_for(target: AstronautState, viewer: str) -> str:
    if viewer == target.id:
        return "self"
    if viewer == "ground":
        return "ground"
    if viewer == routed_to(target.id):
        return "deputy" if target.id == COMMANDER_ID else "commander"
    raise HTTPException(403, "Only the astronaut, the commander (the deputy for the commander's own check) "
                             "or Mission Control can see this.")


@app.get("/checkin/questions")
async def checkin_questions() -> dict:
    """Exact wording: PHQ-2, the PHQ-9 follow-up, and the reaction test."""
    return {"phq2": behavioral.PHQ2_QUESTIONS, "phq9": behavioral.PHQ9_QUESTIONS,
            "reaction_test": behavioral.REACTION_TEST}


@app.get("/wellbeing/method")
async def wellbeing_method() -> dict:
    """Every input, its weight and evidence, the level bands and the safety rules."""
    return behavioral.method()


@app.get("/astronauts/{aid}/wellbeing")
async def get_wellbeing(aid: str, viewer: str) -> Wellbeing:
    s = get_state(aid)
    return wellbeing_view(s, _view_for(s, viewer), now())


@app.get("/crew/wellbeing")
async def get_crew_wellbeing(viewer: str) -> CrewWellbeing:
    """For the commander and Mission Control: every crew member's level, plus crew-wide trends."""
    if viewer not in (COMMANDER_ID, "ground"):
        raise HTTPException(403, "The crew view is for the commander and Mission Control.")
    view = "ground" if viewer == "ground" else "commander"
    members = []
    for s in crew.values():
        if s.id == viewer or s.profile is None:
            continue  # the commander's own check goes to the deputy
        members.append(CrewMemberWellbeing(
            astronaut_id=s.id, name=s.name, role=s.role, level=s.profile.level, score=s.profile.score,
            trend=s.trend.direction if s.trend else "unknown", confidence=s.profile.confidence,
            unreleased_alert=withheld_for_self(s),
            visible_because="ground" if view == "ground" else "commander_first" if withheld_for_self(s) else "shared",
            areas=_area_list(s.profile, "wellbeing") if s.profile.level != "steady" else []))
    crew_wide = [f"Most of the crew ({n} of {len(crew)}) {CREW_WIDE_TEXT[name]}."
                 for name, n in crew_counts.items() if n >= behavioral.CREW_WIDE_MIN and name in CREW_WIDE_TEXT]
    suggestions = []
    if any(crew_counts.get(n, 0) >= behavioral.CREW_WIDE_MIN for n in ("sleep", "body_clock")):
        suggestions.append("Consider reviewing the crew schedule and the lighting plan; a crew rest period may help.")
    env = iss_live.snapshot()
    if env["status"] in ("elevated", "above_limit"):
        suggestions.append(f"Cabin CO2 is {env['co2_1h_avg_mmhg'] or env['co2_mmhg']} mmHg (live ISS reading; "
                           f"NASA limit {env['co2_limit_mmhg']:g} mmHg). Headaches and poorer sleep start around this "
                           "level: consider checking the CO2 scrubber and ventilation.")
    if crew_counts.get("social_time", 0) >= behavioral.CREW_WIDE_MIN:
        suggestions.append("Consider shared crew time: a common meal or a crew evening.")
    if crew_counts.get("mood", 0) >= behavioral.CREW_WIDE_MIN:
        suggestions.append("Consider a lighter day; check the environment (CO2, noise, temperature).")
    if crew_counts.get("reaction_time", 0) >= behavioral.CREW_WIDE_MIN:
        suggestions.append("Consider moving demanding tasks until the crew is better rested.")
    if not suggestions:
        suggestions.append("No crew-wide strain.")
    return CrewWellbeing(
        view=view, crew_wide=crew_wide, members=members, suggestions=suggestions,
        note=f"Crew-wide trends never name anyone and need at least {behavioral.CREW_WIDE_MIN} people. "
             "Questionnaire answers are never aggregated.")


# --- PROVISIONAL: live cabin environment from NASA ISS Live (iss_live.py) -----------

class CabinEnvironment(BaseModel):
    source: str
    updated_at: Optional[datetime]
    ppco2_lab_mmhg: Optional[float]
    ppco2_node3_mmhg: Optional[float]
    ppo2_lab_mmhg: Optional[float]
    cabin_pressure_mmhg: Optional[float]
    cabin_temp_c: Optional[float]
    co2_mmhg: Optional[float]          # the higher of Lab and Node 3 right now
    co2_1h_avg_mmhg: Optional[float]   # what NASA-STD-3001's 3 mmHg limit applies to
    co2_limit_mmhg: float
    status: Literal["ok", "elevated", "above_limit", "unavailable"]
    note: str
    source_url: str


@app.get("/environment")
async def get_environment() -> CabinEnvironment:
    return CabinEnvironment(**iss_live.snapshot())


# --- PROVISIONAL: habitat rooms (location.py: same rooms and stays as the beacons and the profile) ---

class Room(BaseModel):
    id: str
    name: str
    kind: Literal["shared", "private", "untracked"]


class Location(BaseModel):
    astronaut_id: str
    name: str
    room: Optional[str]   # null while in the hygiene module: it has no beacon, never tracked
    room_name: str
    since: Optional[datetime]


class RoomTime(BaseModel):
    astronaut_id: str
    day_start: datetime
    hours: dict[str, float]          # room id -> hours today (hygiene excluded)
    shared_h: float
    private_h: float
    shared_normal_h: float           # average full day in shared rooms, own mission days 7-14
    shared_so_far_normal_h: float    # the same normal, scaled to the time of day so far
    shared_7d_avg_h: float           # average full day in shared rooms over the last 7 days
    with_crew_7d_avg_h: Optional[float] = None   # shared room with a crewmate there: the profile input
    with_crew_normal_h: Optional[float] = None
    note: str


@app.get("/habitat")
async def get_habitat() -> list[Room]:
    return [Room(id=r.id, name=r.name, kind=r.kind) for r in location.ROOMS.values()]


def _note_map_view(s: AstronautState, viewer: str, t: datetime) -> None:
    """The crew map is polled every few seconds: keep one line per viewer per day."""
    day = store.iso(t)[:10]
    for e in s.location_seen:
        if e["viewer"] == viewer and e["reason"] == "crew map (safety)" and e["at"][:10] == day:
            e["at"], e["views"] = store.iso(t), e.get("views", 1) + 1
            return
    s.location_seen.append({"viewer": viewer, "at": store.iso(t), "reason": "crew map (safety)", "views": 1})
    del s.location_seen[:-50]


@app.get("/crew/locations")
async def get_crew_locations(viewer: str) -> list[Location]:
    """Where everyone is now: for the commander and Mission Control (safety: fire, depressurisation)."""
    if viewer not in (COMMANDER_ID, "ground"):
        raise HTTPException(403, "Crew locations are for the commander and Mission Control.")
    t = now()
    out = []
    for s in crew.values():
        tracked = s.room is not None and location.ROOMS[s.room].kind != "untracked"
        out.append(Location(astronaut_id=s.id, name=s.name, room=s.room if tracked else None,
                            room_name=location.ROOMS[s.room].name if tracked else "Not tracked",
                            since=s.room_since if tracked else None))
        _note_map_view(s, viewer, t)
    return out


@app.get("/astronauts/{aid}/rooms")
async def get_room_time(aid: str, viewer: str) -> RoomTime:
    """Hours per room today vs the astronaut's own normal. The astronaut and the commander only."""
    get_state(aid)
    if viewer not in (aid, COMMANDER_ID):
        raise HTTPException(403, "Room time is for the astronaut and the commander.")
    s = get_state(aid)
    t = now()
    start = t.replace(hour=0, minute=0, second=0, microsecond=0)
    b0 = datetime.combine(mission_start.date() + timedelta(days=6), datetime.min.time(), tzinfo=timezone.utc)
    visits = await asyncio.to_thread(store.visits_between, store.iso(min(b0, start - timedelta(days=7))),
                                     store.iso(t))
    shared = lambda a, b: location.by_kind(location.hours_by_room(visits, aid, a, b))["shared"]
    hours = location.hours_by_room(visits, aid, start, t)
    kinds = location.by_kind(hours)
    base_days = [b0 + timedelta(days=d) for d in range(8)]
    with_crew = lambda days: [d.crew_h for d in days if d and d.crew_h is not None]
    last7 = with_crew([s.history.days.get(start.date() - timedelta(days=i)) for i in range(1, 8)]) if s.history else []
    base7 = with_crew([s.history.days.get(d.date()) for d in base_days]) if s.history else []
    return RoomTime(
        astronaut_id=aid, day_start=start, hours={r: round(h, 1) for r, h in hours.items() if r != "hygiene"},
        shared_h=kinds["shared"], private_h=kinds["private"],
        shared_normal_h=round(statistics.fmean(shared(d, d + timedelta(days=1)) for d in base_days), 1),
        shared_so_far_normal_h=round(statistics.fmean(shared(d, d + (t - start)) for d in base_days), 1),
        shared_7d_avg_h=round(statistics.fmean(shared(start - timedelta(days=i), start - timedelta(days=i - 1))
                                               for i in range(1, 8)), 1),
        with_crew_7d_avg_h=round(statistics.fmean(last7), 1) if last7 else None,
        with_crew_normal_h=round(statistics.fmean(base7), 1) if base7 else None,
        note="Time with crewmates (a shared room with someone else there, awake hours) is one of the inputs "
             "of the wellbeing profile, compared with your own mission days 7-14; GET /wellbeing/method shows "
             "its weight. Rooms only, never coordinates. The hygiene module has no beacon and is never tracked.")


@app.get("/notifications")
async def get_notifications(viewer: str) -> list[Notice]:
    """Wellbeing notices for this viewer, newest first."""
    if viewer == "ground":
        mine = [n for n in notices if n.target == "ground"]
    elif viewer in crew:
        mine = [n for n in notices
                if (n.target == "self" and n.astronaut_id == viewer)
                or (n.target in ("commander", "deputy") and routed_to(n.astronaut_id) == viewer)]
    else:
        raise HTTPException(403, "Unknown viewer.")
    return list(reversed(mine))


def _psych_text(s: AstronautState, wb: Wellbeing, alerts: list[PsychReportAlert], ctx: list[str],
                dq: dict[str, int], t: datetime) -> str:
    who = {"self": "the astronaut", "commander": "the commander", "deputy": "the deputy",
           "ground": "Mission Control"}[wb.view]
    lines = [f"Psychological report: {s.name} ({s.role}), mission day {wb.mission_day}, {t:%d %b %Y}.",
             f"For {who}. Decision support only, never a diagnosis."]
    if wb.withheld:
        lines.append("Your numbers against your own normal (mission days 7-14):")
        lines += [f"- {x.label}: {x.detail}" for x in wb.signals if x.enough_data]
        return "\n".join(lines)
    lines.append(f"Wellbeing level: {wb.level.upper()} (score {wb.score}/100). Confidence {wb.confidence}: "
                 f"{wb.coverage * 100:.0f}% of the weighted inputs had enough data.")
    if wb.rule:
        lines.append(f"Safety rule: {wb.rule}")
    tr = wb.trend
    if tr and tr.direction != "unknown":
        since = f" First at watch or above on {tr.first_flagged:%d %b}." if tr.first_flagged else ""
        lines.append(f"Trend: {tr.direction} ({tr.points_per_week:+.0f} points a week over the last 2 weeks; "
                     f"7 days ago {tr.score_7_days_ago}).{since}")
        lines.append("Daily score, last 14 days: " +
                     " ".join(f"d{p.mission_day}:{p.score}" for p in tr.timeline[-14:]))
    lines.append("What changed, against your own days 7-14 (biggest first):")
    for x in sorted(wb.signals, key=lambda x: -x.points):
        if not x.enough_data:
            continue
        tail = "" if x.trend == "unknown" else f" Trend: {x.trend}."
        lines.append(f"- {x.label} [{x.points:g} of {x.weight:g} points]: {x.detail}{tail}")
    missing = [x.label for x in wb.signals if not x.enough_data]
    if missing:
        lines.append(f"Not enough data yet: {', '.join(missing)}.")
    if wb.needs_phq9:
        lines.append("Next step: the PHQ-9 follow-up (PHQ-2 was 2 or more).")
    if wb.personal_or_shared and wb.personal_or_shared != "Nothing stands out.":
        lines.append(wb.personal_or_shared)
    lines += ctx
    for a in alerts:
        rel = f"released {a.released_to_crew_at:%d %b %H:%M} by {a.released_by}" if a.released_to_crew_at \
            else "not released yet"
        lines.append(f"Flag: {a.started_at:%d %b %H:%M} {a.profile} ({a.severity}), to {a.routed_to} first, {rel}.")
    total = sum(dq.values())
    if total:
        lines.append(f"Data: {100 * dq.get('ok', 0) / total:.1f}% of {total} readings clean; "
                     f"{dq.get('artifact', 0)} marked as sensor errors and left out.")
    lines.append("Suggested next steps: " + " ".join(wb.suggestions))
    lines.append("Method: score = weight x change from your own normal; watch and station 70, check-ins 30 "
                 "(a team design choice); weights in GET /wellbeing/method.")
    return "\n".join(lines)


@app.get("/astronauts/{aid}/psych-report")
async def psych_report(aid: str, viewer: str, days: int = Query(28, ge=7, le=60)) -> PsychReport:
    """The psychological profile as one report: trend over time, every input, flags and who saw them."""
    s = get_state(aid)
    view = _view_for(s, viewer)
    t = now()
    wb = wellbeing_view(s, view, t)
    since = t - timedelta(days=days)
    alerts = [PsychReportAlert(id=a.id, profile=a.profile, severity=a.severity, started_at=a.started_at,
                               routed_to=a.routed_to, released_to_crew_at=a.released_to_crew_at,
                               released_by=a.released_by, still_active=s.active.get(a.profile) is a)
              for a in psych_alerts(s, active_only=False)
              if a.started_at >= since and (view != "self" or a.released_to_crew_at is not None)]
    ctx = [] if wb.withheld else [f"Crew context: most of the crew ({n} of {len(crew)}) {CREW_WIDE_TEXT[k]}."
                                  for k, n in crew_counts.items()
                                  if n >= behavioral.CREW_WIDE_MIN and k in CREW_WIDE_TEXT]
    dq = await asyncio.to_thread(store.quality_counts, aid, store.iso(since))
    text = _psych_text(s, wb, alerts, ctx, dq, t)
    return PsychReport(profile=wb, alerts=alerts, crew_context=ctx, data_quality=dq, text=text,
                       size_bytes=len(text.encode("utf-8")), method=behavioral.method())


@app.get("/station/rooms")
async def station_rooms() -> list[location.Room]:
    """Rooms and their beacon ids (iBeacon UUID / major / minor), for the watch and a station map."""
    return location.rooms()


@app.post("/astronauts/{aid}/location")
async def post_location(aid: str, body: location.ScanRequest) -> location.ScanResult:
    """PROVISIONAL. A Bluetooth scan from the watch: beacons heard and their signal strength."""
    get_state(aid)
    return location.handle_scan(aid, body, asyncio.get_running_loop().time())


def _emergency(s: AstronautState) -> Optional[str]:
    crit = next((a for a in s.active.values() if a.severity == "critical"), None)
    if crit:
        return f"active critical alert ({crit.profile})"
    if s.profile and s.profile.level == "urgent":
        return "urgent wellbeing level"
    return None


@app.get("/astronauts/{aid}/location")
async def get_location(aid: str, viewer: str) -> LocationView:
    """Only the astronaut sees where they are. The commander, the Crew Medical Officer and Mission
    Control see the current room only during an emergency, and the astronaut can see who looked."""
    s = get_state(aid)
    t = now()
    current = LocationNow(room=s.room, room_name=location.ROOMS[s.room].name if s.room else None,
                          since=s.room_since, source=s.room_source)
    if viewer != aid:
        reason = _emergency(s)
        roles = {COMMANDER_ID: "commander", CMO_ID: "doctor", "ground": "ground"}
        if viewer not in roles or reason is None:
            raise HTTPException(403, "Location history is the astronaut's own. The commander and Mission Control "
                                     "see current rooms on GET /crew/locations; the Crew Medical Officer only "
                                     "in an emergency.")
        s.location_seen.append({"viewer": viewer, "at": store.iso(t), "reason": reason})
        return LocationView(astronaut_id=aid, view=roles[viewer], current=current, reason=reason,
                            today_minutes=None, week=None, seen_by=None,
                            note="Shown because of an emergency. The astronaut can see that you looked.")
    day0 = datetime.combine(t.date(), datetime.min.time(), tzinfo=timezone.utc)
    visits = await asyncio.to_thread(store.visits_between, store.iso(day0), store.iso(t))
    minutes: dict[str, int] = {}
    for vid, room, entered, left in visits:
        if vid != aid:
            continue
        a = max(datetime.fromisoformat(entered.replace("Z", "+00:00")), day0)
        b = datetime.fromisoformat(left.replace("Z", "+00:00"))
        minutes[room] = minutes.get(room, 0) + max(0, round((b - a).total_seconds() / 60))
    social = next((x for x in (s.profile.signals if s.profile else []) if x.name == "social_time"), None)
    week = None
    if s.history:
        last7 = [s.history.days.get(t.date() - timedelta(days=i)) for i in range(1, 8)]
        crew_h = [d.crew_h for d in last7 if d and d.crew_h is not None]
        q_h = [d.quarters_h for d in last7 if d and d.quarters_h is not None]
        week = {"with_crew_h_per_day": round(statistics.fmean(crew_h), 1) if crew_h else None,
                "alone_in_quarters_h_per_day": round(statistics.fmean(q_h), 1) if q_h else None}
    return LocationView(astronaut_id=aid, view="self", current=current, reason=None, today_minutes=minutes,
                        week=week, seen_by=list(s.location_seen),
                        note=(social.detail if social else "") + " Rooms only, never coordinates. The commander "
                             "and Mission Control can see which room you're in now (for safety: fire or "
                             "depressurisation), and seen_by lists who looked. Hygiene is never tracked.")


@app.get("/mission/light-time")
async def get_light_time() -> LightTime:
    live = light_time["live_one_way_delay_s"]
    return LightTime(
        environment=mission.environment, live_one_way_delay_s=live, computed_for=light_time["computed_for"],
        in_use=bool(live) and mission.environment == "mars" and mission.real_one_way_delay_s == live,
        note="Earth-Mars one-way light time today, from NASA JPL Horizons. It ranges from about 3 to 22 "
             "minutes as the planets move. Set AHM_LIVE_LIGHT_TIME=1 to use it for the verdict.",
        source="NASA JPL Horizons (Mars, observer range from Earth)", source_url=horizons.DOCS_URL)


# --- Circadian / lighting (PROVISIONAL) -----------------------------------------
# Shared with ground by default; the ground view gets 403 once the astronaut opts out.

@app.get("/astronauts/{aid}/circadian")
async def get_circadian(aid: str, view: Literal["crew", "ground"] = "crew") -> circadian.Circadian:
    get_state(aid)
    if view == "ground" and not circadian.is_shared(aid):
        raise HTTPException(403, "Not shared: the astronaut has opted out of sharing sleep and lighting data.")
    return circadian.assess(aid, now(), mission.environment)


@app.put("/astronauts/{aid}/circadian/plan")
async def put_circadian_plan(aid: str, body: circadian.PlanRequest) -> circadian.Circadian:
    # The astronaut's own choice to follow (or stop) the suggested lighting plan.
    get_state(aid)
    circadian.set_plan(aid, body.accepted, now())
    return circadian.assess(aid, now(), mission.environment)


@app.put("/astronauts/{aid}/circadian/sharing")
async def put_circadian_sharing(aid: str, body: circadian.SharingRequest) -> circadian.SharingRequest:
    get_state(aid)
    circadian.set_shared(aid, body.share_with_ground)
    return body


@app.put("/astronauts/{aid}/lighting")
async def put_lighting(aid: str, body: circadian.LightingRequest) -> circadian.Lighting:
    # Records the crew's own switch of the SSLA mode; the app never changes it by itself.
    get_state(aid)
    return circadian.set_lighting(aid, body.mode, now())


class CircadianDebugRequest(BaseModel):
    astronaut_id: str
    action: Literal["advance", "reset"]
    nights: int = Field(default=3, ge=1, le=14)


@app.post("/debug/circadian")
async def debug_circadian(body: CircadianDebugRequest) -> circadian.Circadian:
    # Dev only: fast-forward the lighting log so the demo can show the loop close in seconds.
    get_state(body.astronaut_id)
    if body.action == "advance":
        circadian.advance(body.astronaut_id, body.nights)
    else:
        circadian.reset(body.astronaut_id)
    crew[body.astronaut_id].tick()  # refresh last night's sleep in vitals right away
    return circadian.assess(body.astronaut_id, now(), mission.environment)
