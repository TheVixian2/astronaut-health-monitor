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
import habitat
import horizons
import iss_live
import insight_service
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


class Accepted(BaseModel):
    accepted: bool = True


class Baseline(BaseModel):
    heart_rate_bpm: int
    spo2_pct: int
    temp_c: float
    resp_rate_bpm: int
    sleep_h_last_night: float
    mood_1to5: int


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
    reaction_test: Optional[behavioral.ReactionTest] = None


class ScenarioRequest(BaseModel):
    astronaut_id: str
    # "strain" is PROVISIONAL: injects a behavioral-health check-in that reaches the urgent level
    scenario: Literal["sleep_debt", "strain", "clear"]


# PROVISIONAL additions (not yet in docs/api-spec.md)

Target = Literal["commander", "ground", "self"]


class Notice(BaseModel):
    id: str
    astronaut_id: str          # whose wellbeing this is about
    target: Target
    level: behavioral.Level
    reason: Literal["shared_by_astronaut", "automatic_urgent", "told_astronaut"]
    areas: list[str]           # e.g. ["mood", "sleep"]: never the answers themselves
    created_at: datetime
    ground_eta_s: Optional[int] = None
    message: str


class CrewMemberWellbeing(BaseModel):
    astronaut_id: str
    name: str
    role: str
    level: Optional[behavioral.Level]  # null when the astronaut keeps it private
    visible_because: Literal["shared", "automatic_urgent", "commander_first", "private"]
    areas: list[str] = []              # which areas raised the level; never the answers


class CrewWellbeing(BaseModel):
    view: Literal["commander", "ground"]
    crew_wide: list[str]       # trends shared by >= 3 crew, without names
    members: list[CrewMemberWellbeing]
    suggestions: list[str]
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
WALK_STEP = {"heart_rate_bpm": 1.0, "spo2_pct": 0.2, "temp_c": 0.02, "resp_rate_bpm": 0.3}


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
        # Behavioral health (behavioral.py): astronaut first, nothing shared until they choose.
        self.wb_share = {"commander": False, "ground": False}
        self.wb_auto_notified = False       # urgent level reached in this episode
        self.wb_level: str = "steady"
        self.mood_baseline: Optional[float] = None
        self.rt_baseline: Optional[tuple[float, float]] = None
        self.hr_7d: Optional[float] = None

    def watch_dropout(self) -> bool:
        loop = asyncio.get_running_loop()
        return self.real_hr is not None and loop.time() - self.real_hr[1] >= REAL_HR_FRESH_S

    def target(self, field: str) -> float:
        base = getattr(self.baseline, field)
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

    def snapshot(self) -> Vitals:
        v = self.values
        hr, source = v["heart_rate_bpm"], "simulated"
        loop = asyncio.get_running_loop()
        if self.real_hr and loop.time() - self.real_hr[1] < REAL_HR_FRESH_S:
            hr, source = self.real_hr[0], self.real_hr[2]
        return Vitals(
            timestamp=now(), source=source, baseline=self.baseline,
            heart_rate_bpm=round(hr), spo2_pct=round(v["spo2_pct"]),
            temp_c=round(v["temp_c"], 1), resp_rate_bpm=round(v["resp_rate_bpm"]),
            sleep_h_last_night=round(v["sleep_h_last_night"], 1),
            mood_1to5=max(1, min(5, round(v["mood_1to5"]))), quality=self.quality)

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
    w0, w1 = store.iso(mission_start + timedelta(days=6)), store.iso(mission_start + timedelta(days=14))
    view = {}
    for aid in crew:
        window = store.checkins_between(aid, w0, w1)
        moods = behavioral.mood_values(window)
        view[aid] = dict(
            baseline=store.baseline(aid, w0, w1),
            mood=statistics.median(moods) if moods else None,
            rt=behavioral.rt_baseline(window),
            hr_7d=store.period_stats(aid, store.iso(t - timedelta(days=7)))["heart_rate_bpm"]["avg"],
            checkins=store.checkins_between(aid, store.iso(t - timedelta(days=14))))
    return view


async def refresh_from_store() -> None:
    view = await asyncio.to_thread(_load_store_view, now())
    for aid, d in view.items():
        s = crew[aid]
        s.baseline_stored = d["baseline"] is not None
        s.baseline = Baseline(**_round_baseline(d["baseline"])) if s.baseline_stored else s.configured
        s.mood_baseline, s.rt_baseline, s.hr_7d = d["mood"], d["rt"], d["hr_7d"]
        newest = d["checkins"][-1][0] if d["checkins"] else ""
        s.checkins = d["checkins"] + [c for c in s.checkins if c[0] > newest]  # keep any not yet read back


# --- Behavioral health (behavioral.py) ----------------------------------------------

LEVEL_RANK = {"steady": 0, "watch": 1, "concern": 2, "urgent": 3}
CREW_WIDE_TEXT = {
    "sleep": "is sleeping at least 1 h less than usual",
    "body_clock": "has irregular or drifting bedtimes",
    "mood": "reports a lower mood than usual",
    "reaction_time": "has slower reaction times than usual",
    "resting_heart_rate": "has a higher resting heart rate than usual",
}  # PHQ-2 is never aggregated: too personal even without names


def _signals(s: AstronautState, t: datetime) -> list[behavioral.Signal]:
    week = store.iso(t - timedelta(days=7))
    recent = [c for c in s.checkins if c[0] >= week]
    moods = behavioral.mood_values(recent)
    circ = circadian.assess(s.id, t, mission.environment).summary
    return behavioral.signals_for(behavioral.Inputs(
        phq2=behavioral.latest_phq2(s.checkins), mood_7d=statistics.fmean(moods) if moods else None,
        mood_baseline=s.mood_baseline, sleep_avg_7n=circ.sleep_avg_h,
        sleep_baseline=s.baseline.sleep_h_last_night,
        body_clock_status="watch" if circ.status == "watch" else "steady",
        rt_latest=behavioral.latest_rt(s.checkins), rt_baseline=s.rt_baseline,
        hr_7d=s.hr_7d, hr_baseline=s.baseline.heart_rate_bpm))


def crew_signals(t: datetime) -> tuple[dict[str, list[behavioral.Signal]], dict[str, int]]:
    """Every astronaut's signals, marked crew_wide where >= 3 people share them, plus counts."""
    all_sigs = {aid: _signals(s, t) for aid, s in crew.items()}
    counts: dict[str, int] = {}
    for sigs in all_sigs.values():
        for name in {x.name for x in sigs if x.points > 0}:
            counts[name] = counts.get(name, 0) + 1
    shared = {n for n, k in counts.items() if k >= behavioral.CREW_WIDE_MIN and n != "phq2"}
    for sigs in all_sigs.values():
        for x in sigs:
            x.crew_wide = x.name in shared and x.points > 0
    return all_sigs, counts


def wellbeing(s: AstronautState, t: datetime, view: str,
              all_sigs: Optional[dict[str, list[behavioral.Signal]]] = None) -> behavioral.Wellbeing:
    sigs = (all_sigs or crew_signals(t)[0])[s.id]
    score = min(100, round(sum(x.points for x in sigs)))
    phq = behavioral.latest_phq2(s.checkins)
    level = behavioral.level_from(sigs, score, phq[0] if phq else None)
    if s.wb_auto_notified:
        share_note = ("Because several strong signals added up, your commander and Mission Control were told "
                      "your wellbeing level and which areas are affected, not your answers. This is a wellbeing "
                      "check, not a diagnosis.")
    else:
        share_note = ("Your commander sees your wellbeing level and which areas are affected, never your answers. "
                      "Mission Control sees it only if you share it, or automatically at the urgent level.")
    wb = behavioral.Wellbeing(
        astronaut_id=s.id, view=view, mission_day=mission_day(t), level=level, score=score, signals=sigs,
        phq2=behavioral.Phq2Result(score=phq[0], screen_positive=phq[0] >= behavioral.PHQ2_POSITIVE,
                                   taken_at=phq[1]) if phq else None,
        personal_or_shared=behavioral.personal_or_shared(sigs),
        suggestions=behavioral.suggestions_for(level, sigs),
        sharing=behavioral.SharingState(commander=s.wb_share["commander"], ground=s.wb_share["ground"],
                                        auto_notified=s.wb_auto_notified, note=share_note),
        note="Decision support only, never a diagnosis. Everything except PHQ-2 is compared with your own "
             "mission days 7-14; PHQ-2 uses its validated screening cut-off.",
        sources=behavioral.SOURCES)
    if view != "self" and not s.wb_share["ground" if view == "ground" else "commander"]:
        # Visible only because of the automatic urgent rule: the level and areas, never the answers.
        wb.signals = [behavioral.Signal(name=x.name, area=x.area, value=None, baseline=None, points=x.points,
                                        detail="Kept private by the astronaut.", crew_wide=x.crew_wide)
                      for x in sigs if x.points > 0]
        wb.phq2 = None
        wb.suggestions = (["Consider checking in with them privately; they know you were notified."]
                          if s.wb_auto_notified else
                          ["They have not been told you can see this. Decide whether and how to raise it: "
                           "in person, in private."])
    return wb


def send_notice(s: AstronautState, target: str, level: str, reason: str, areas: list[str]) -> None:
    if target == "commander" and s.id == COMMANDER_ID:
        return  # the commander's own wellbeing goes to ground only
    name = s.name
    area_text = ", ".join(areas) or "general"
    message = {
        "automatic_urgent": f"{name}'s wellbeing check reached the urgent level (areas: {area_text}). They have "
                            f"been told you were notified. Consider checking in with them privately.",
        "shared_by_astronaut": f"{name} chose to share their wellbeing check with you: {level} (areas: {area_text}).",
        "told_astronaut": "Several strong signals added up, so your commander and Mission Control were told your "
                          "wellbeing level and the areas affected, not your answers. This is a wellbeing check, "
                          "not a diagnosis.",
    }[reason]
    n = Notice(id=f"nt-{uuid.uuid4().hex[:8]}", astronaut_id=s.id, target=target, level=level, reason=reason,
               areas=areas, created_at=now(), ground_eta_s=ground_eta_s() if target == "ground" else None,
               message=message)
    notices.append(n)
    store.save_notice(n.model_dump(mode="json"))
    if target == "ground":
        publish(s.id, "notice", n, views={"ground"})          # delayed, and held during a blackout
    elif target == "commander":
        publish(COMMANDER_ID, "notice", n, views={"crew"})    # the commander's own console
    else:
        publish(s.id, "notice", n, views={"crew"})            # the astronaut themselves
    log.info("%s: wellbeing notice to %s (%s, %s)", s.id, target, level, reason)


def save_wb_state(s: AstronautState) -> None:
    store.meta_set_async(f"wb_state:{s.id}", json.dumps({"share": s.wb_share, "auto_notified": s.wb_auto_notified}))


def evaluate_wellbeing(t: datetime) -> None:
    all_sigs, _ = crew_signals(t)
    for s in crew.values():
        wb = wellbeing(s, t, "self", all_sigs)
        areas = behavioral.areas(wb.signals)
        auto_now = False
        if wb.level == "urgent" and not s.wb_auto_notified:
            s.wb_auto_notified = auto_now = True  # the safety exception, once per episode
            for target in ("commander", "ground"):
                send_notice(s, target, wb.level, "automatic_urgent", areas)
            send_notice(s, "self", wb.level, "told_astronaut", areas)
        elif LEVEL_RANK[wb.level] < LEVEL_RANK["concern"] and s.wb_auto_notified:
            s.wb_auto_notified = False  # episode over
            save_wb_state(s)
        if auto_now:
            save_wb_state(s)
        if wb.level != s.wb_level and not auto_now:
            for target in ("commander", "ground"):
                if s.wb_share[target]:
                    send_notice(s, target, wb.level, "shared_by_astronaut", areas)
            s.wb_level = wb.level


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
    publish(s.id, "alert", alert)


def raise_alert(s: AstronautState, profile: str, v: dict, ctx: engine.Context) -> Alert:
    p = engine.PROFILES[profile]
    question = engine.CONFIRM_QUESTIONS.get(profile)
    alert = Alert(
        id=f"al-{uuid.uuid4().hex[:8]}", astronaut_id=s.id, profile=profile,
        severity=p["severity"], hazard=p["hazard"], body_region=p["body_region"],
        started_at=now(), onboard_action=p["onboard_action"], act_within_s=p["act_within_s"],
        ground_eta_s=ground_eta_s(), insight=None,
        data_quality="suspect" if s.quality == "suspect" else "ok",
        confirmation=Confirmation(status="pending", question=question) if question else None)
    s.alerts.append(alert)
    s.active[profile] = alert
    s.misses[profile] = 0
    store.save_alert(alert.model_dump(mode="json"))
    publish(s.id, "alert", alert)
    log.info("%s: %s alert raised", s.id, profile)
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
    # Behavioral health: restore sharing choices and notices; take today's levels silently
    # so a restart never re-sends notifications.
    for n in await asyncio.to_thread(store.load_notices):
        try:
            notices.append(Notice(**n))
        except Exception:
            continue
    all_sigs, _ = crew_signals(t)
    for s in crew.values():
        saved = await asyncio.to_thread(store.meta_get, f"wb_state:{s.id}")
        if saved:
            state = json.loads(saved)
            s.wb_share.update(state.get("share", {}))
            s.wb_auto_notified = bool(state.get("auto_notified"))
        s.wb_level = wellbeing(s, t, "self", all_sigs).level
    spawn(tick_loop())
    spawn(fetch_light_time())
    yield
    for task in list(background):
        task.cancel()
    iss_live.stop()
    store.stop_writer()


app = FastAPI(title="Astronaut Health Monitor backend", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# --- Endpoints -----------------------------------------------------------------

@app.get("/")
async def root() -> dict:
    return {"service": "astronaut-health-monitor backend", "docs": "/docs"}


@app.get("/crew")
async def get_crew() -> list[CrewMember]:
    return [CrewMember(id=s.id, name=s.name, role=s.role, status=s.status()) for s in crew.values()]


@app.post("/astronauts/{aid}/ingest", status_code=202)
async def ingest(aid: str, body: IngestRequest) -> Accepted:
    state = get_state(aid)
    state.real_hr = (body.heart_rate_bpm, asyncio.get_running_loop().time(), body.source)
    state.values["heart_rate_bpm"] = body.heart_rate_bpm
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
async def get_alerts(aid: str) -> list[Alert]:
    return list(reversed(get_state(aid).alerts))  # newest first


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
    evaluate_wellbeing(now())  # a single check-in can change the wellbeing level


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
        evaluate_wellbeing(now())
    elif body.scenario == "strain":
        # Same path as a real check-in, kept PRIVATE: strong PHQ-2, low mood and a slow reaction test,
        # enough to reach "urgent", so the automatic notification can be shown.
        rt, lapses = s.rt_baseline or (260.0, 1.0)
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
                "resp_rate_bpm": "Breathing (/min)", "sleep_h_last_night": "Sleep (h)", "mood_1to5": "Mood (1-5)"}
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


# --- PROVISIONAL: behavioral health (behavioral.py) ---------------------------------
# `viewer` is who is looking: their astronaut id, or "ground". The web login decides it;
# this is a demo-level check, not security (docs/api-spec.md: "Auth: none").

def _view_for(target: AstronautState, viewer: str) -> str:
    if viewer == target.id:
        return "self"
    if viewer == "ground":
        return "ground"
    if viewer == COMMANDER_ID:
        return "commander"
    raise HTTPException(403, "Only the astronaut themselves, the commander or ground can see this.")


def _can_see(target: AstronautState, view: str) -> bool:
    # Commander first (team decision 2026-11-14): the commander always sees the level and the
    # areas (never the answers, see wellbeing()); Mission Control only if shared or urgent.
    return view in ("self", "commander") or target.wb_share[view] or target.wb_auto_notified


@app.get("/checkin/questions")
async def checkin_questions() -> dict:
    """Exact wording for the behavioral check-in: validated PHQ-2 items and the reaction test."""
    return {"phq2": behavioral.PHQ2_QUESTIONS, "reaction_test": behavioral.REACTION_TEST}


@app.get("/astronauts/{aid}/wellbeing")
async def get_wellbeing(aid: str, viewer: str) -> behavioral.Wellbeing:
    s = get_state(aid)
    view = _view_for(s, viewer)
    if not _can_see(s, view):
        raise HTTPException(403, "Kept private by the astronaut.")
    return wellbeing(s, now(), view)


@app.put("/astronauts/{aid}/wellbeing/sharing")
async def put_wellbeing_sharing(aid: str, viewer: str, body: behavioral.SharingRequest) -> behavioral.SharingState:
    """Only the astronaut can choose who sees their wellbeing check."""
    s = get_state(aid)
    if viewer != aid:
        raise HTTPException(403, "Only the astronaut can change who sees their wellbeing check.")
    t = now()
    wb = wellbeing(s, t, "self")
    for target in ("commander", "ground"):
        new = getattr(body, target)
        if new is None or new == s.wb_share[target]:
            continue
        s.wb_share[target] = new
        if new:  # sharing turned on: tell them the current level straight away
            send_notice(s, target, wb.level, "shared_by_astronaut", behavioral.areas(wb.signals))
    save_wb_state(s)
    return wellbeing(s, t, "self").sharing


@app.get("/crew/wellbeing")
async def get_crew_wellbeing(viewer: str) -> CrewWellbeing:
    """For the commander and ground: who shared what, plus crew-wide trends without names."""
    if viewer not in (COMMANDER_ID, "ground"):
        raise HTTPException(403, "The crew view is for the commander and ground.")
    view = "ground" if viewer == "ground" else "commander"
    t = now()
    all_sigs, counts = crew_signals(t)
    members = []
    for s in crew.values():
        if s.id == viewer:
            continue
        shown = ("shared" if s.wb_share[view] else "automatic_urgent" if s.wb_auto_notified
                 else "commander_first" if view == "commander" else "private")
        wb = wellbeing(s, t, "self", all_sigs)
        visible = shown != "private"
        members.append(CrewMemberWellbeing(
            astronaut_id=s.id, name=s.name, role=s.role, visible_because=shown,
            level=wb.level if visible else None,
            areas=behavioral.areas(wb.signals) if visible else []))
    crew_wide = [f"Most of the crew ({n} of {len(crew)}) {CREW_WIDE_TEXT[name]}."
                 for name, n in counts.items() if n >= behavioral.CREW_WIDE_MIN and name in CREW_WIDE_TEXT]
    suggestions = []
    if any(n >= behavioral.CREW_WIDE_MIN for name, n in counts.items() if name in ("sleep", "body_clock")):
        suggestions.append("Consider reviewing the crew schedule and the lighting plan; a crew rest period may help.")
    env = iss_live.snapshot()
    if env["status"] in ("elevated", "above_limit"):
        suggestions.append(f"Cabin CO2 is {env['co2_1h_avg_mmhg'] or env['co2_mmhg']} mmHg (live ISS reading; "
                           f"NASA limit {env['co2_limit_mmhg']:g} mmHg). Headaches and poorer sleep start around this "
                           "level: consider checking the CO2 scrubber and ventilation.")
    if counts.get("mood", 0) >= behavioral.CREW_WIDE_MIN:
        suggestions.append("Consider shared crew time or a lighter day; check the environment (CO2, noise, temperature).")
    if counts.get("reaction_time", 0) >= behavioral.CREW_WIDE_MIN:
        suggestions.append("Consider moving demanding tasks until the crew is better rested.")
    if not suggestions:
        suggestions.append("No crew-wide strain. Individual check-ins stay private unless an astronaut shares them.")
    return CrewWellbeing(
        view=view, crew_wide=crew_wide, members=members, suggestions=suggestions,
        note=f"Crew-wide trends never name anyone and need at least {behavioral.CREW_WIDE_MIN} people. "
             "Questionnaire answers are never aggregated or shown here.")


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


# --- PROVISIONAL: habitat rooms (habitat.py) -----------------------------------------

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
    note: str


@app.get("/habitat")
async def get_habitat() -> list[Room]:
    return [Room(id=r, name=n, kind=k) for r, (n, k) in habitat.ROOMS.items()]


@app.get("/crew/locations")
async def get_crew_locations(viewer: str) -> list[Location]:
    """Where everyone is now: for the commander and Mission Control (safety: fire, depressurisation)."""
    if viewer not in (COMMANDER_ID, "ground"):
        raise HTTPException(403, "Crew locations are for the commander and Mission Control.")
    t = now()
    out = []
    for s in crew.values():
        r = habitat.room_at(s.id, t, mission_start)
        tracked = habitat.ROOMS[r][1] != "untracked"
        out.append(Location(astronaut_id=s.id, name=s.name, room=r if tracked else None,
                            room_name=habitat.ROOMS[r][0] if tracked else "Not tracked",
                            since=habitat.since(s.id, t, mission_start) if tracked else None))
    return out


@app.get("/astronauts/{aid}/rooms")
async def get_room_time(aid: str, viewer: str) -> RoomTime:
    """Hours per room today vs the astronaut's own normal. The astronaut and the commander only."""
    get_state(aid)
    if viewer not in (aid, COMMANDER_ID):
        raise HTTPException(403, "Room time is for the astronaut and the commander.")
    t = now()
    start = t.replace(hour=0, minute=0, second=0, microsecond=0)
    hours = habitat.hours_by_room(aid, start, t, mission_start)
    kinds = habitat.by_kind(hours)
    normal = habitat.waking_shared_normal(aid, mission_start)
    so_far = habitat.by_kind(habitat.hours_by_room(aid, mission_start + timedelta(days=6),
                                                   mission_start + timedelta(days=6) + (t - start), mission_start))
    return RoomTime(
        astronaut_id=aid, day_start=start, hours={r: h for r, h in hours.items() if r != "hygiene"},
        shared_h=kinds["shared"], private_h=kinds["private"], shared_normal_h=normal,
        shared_so_far_normal_h=so_far["shared"],
        shared_7d_avg_h=round(sum(habitat.by_kind(habitat.hours_by_room(
            aid, start - timedelta(days=d), start - timedelta(days=d - 1), mission_start))["shared"]
            for d in range(1, 8)) / 7, 1),
        note="Supporting signal only: time in shared rooms is shown, never added to the wellbeing score. "
             "The hygiene module has no beacon and is never tracked.")


@app.get("/notifications")
async def get_notifications(viewer: str) -> list[Notice]:
    """Wellbeing notices for this viewer, newest first: the commander, ground, or the astronaut themselves."""
    if viewer == "ground":
        mine = [n for n in notices if n.target == "ground"]
    elif viewer == COMMANDER_ID:
        mine = [n for n in notices if n.target == "commander" or (n.target == "self" and n.astronaut_id == viewer)]
    elif viewer in crew:
        mine = [n for n in notices if n.target == "self" and n.astronaut_id == viewer]
    else:
        raise HTTPException(403, "Unknown viewer.")
    return list(reversed(mine))


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
