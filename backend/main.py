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

import circadian
import engine
import horizons
import insight_service
import store

logging.basicConfig(level=logging.INFO, format="%(levelname)s:     %(name)s: %(message)s")
log = logging.getLogger("ahm")

TICK_S = 3
REFRESH_EVERY_TICKS = 20  # baselines, CO2 averages and SANS every ~60 s
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
    systolic_mmhg: int
    diastolic_mmhg: int
    spo2_pct: int
    temp_c: float
    resp_rate_bpm: int
    sleep_h_last_night: float
    mood_1to5: int


class Vitals(Baseline):
    timestamp: datetime
    source: Source
    baseline: Baseline


class Insight(BaseModel):
    why: str
    trend: str
    recommended_action: str


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


class Mission(BaseModel):
    environment: Environment
    one_way_delay_s: int                         # how long the Ground stream waits (demo-compressed)
    real_one_way_delay_s: Optional[int] = None   # true light time; the verdict uses this

    @model_validator(mode="after")
    def _default_real_delay(self):
        if self.real_one_way_delay_s is None:
            self.real_one_way_delay_s = self.one_way_delay_s
        return self


class Vision(BaseModel):
    amsler_distortion: Optional[bool] = None
    acuity_line: Optional[int] = None


class CheckinRequest(BaseModel):
    timestamp: datetime
    mood_1to5: Optional[int] = None
    sleep_h: Optional[float] = None
    symptoms: Optional[list[str]] = None
    vision: Optional[Vision] = None
    share_with_ground: bool


class ScenarioRequest(BaseModel):
    astronaut_id: str
    scenario: Literal["fever", "co2", "orthostatic", "sans", "sleep_debt", "clear"]


# PROVISIONAL additions (not yet in docs/api-spec.md)

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
    systolic_mmhg: Optional[float] = None
    diastolic_mmhg: Optional[float] = None
    spo2_pct: Optional[float] = None
    temp_c: Optional[float] = None
    resp_rate_bpm: Optional[float] = None
    sleep_h_last_night: Optional[float] = None
    mood_1to5: Optional[float] = None
    cabin_co2_mmhg: Optional[float] = None


class SansComponent(BaseModel):
    name: str
    points: float
    detail: str


class VisionCheck(BaseModel):
    ts: datetime
    acuity_line: Optional[int] = None
    amsler_distortion: Optional[bool] = None
    headache: bool


class SansRisk(BaseModel):
    astronaut_id: str
    mission_day: int
    score: int
    trigger_at: int
    status: Literal["nominal", "watch"]
    baseline_acuity: Optional[float]
    components: list[SansComponent]
    vision_checks: list[VisionCheck]
    note: str
    source_url: str


# --- State -----------------------------------------------------------------------

SEVERITY_RANK = {"watch": 1, "alert": 2, "critical": 3}
WALK_STEP = {"heart_rate_bpm": 1.0, "systolic_mmhg": 1.0, "diastolic_mmhg": 0.7,
             "spo2_pct": 0.2, "temp_c": 0.02, "resp_rate_bpm": 0.3}
PRIVATE_DETAIL = "Based on check-ins the astronaut keeps private."


class AstronautState:
    def __init__(self, aid: str):
        self.id = aid
        self.name, self.role, cfg = engine.CREW[aid]
        self.configured = Baseline(**cfg)
        self.baseline = self.configured
        self.baseline_stored = False  # True once days 7-14 come from the database
        self.values = {k: float(v) for k, v in cfg.items()}
        self.values["sleep_h_last_night"] = circadian.last_sleep_h(aid)
        self.cabin_co2 = engine.CABIN_CO2_NOMINAL_MMHG
        self.scenario: Optional[str] = None
        self.real_hr: Optional[tuple[float, float, str]] = None  # watch (bpm, loop time, source)
        self.alerts: list[Alert] = []
        self.active: dict[str, Alert] = {}  # profile -> alert
        self.misses: dict[str, int] = {}    # profile -> consecutive non-matching ticks
        self.manual: dict[str, float] = {}  # sleep/mood from the latest check-in
        self.checkins: list[tuple[str, dict]] = []  # last 14 days, oldest first
        self.baseline_acuity: Optional[float] = None
        self.co2_avg_7d: Optional[float] = None

    def target(self, field: str) -> float:
        base = getattr(self.baseline, field)
        mult = engine.SCENARIO_MULT.get(self.scenario, {}).get(field, 1.0)
        return base * mult + engine.SCENARIO_ADD.get(self.scenario, {}).get(field, 0.0)

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
        co2_target = engine.SCENARIO_CABIN_CO2_MMHG.get(self.scenario, engine.CABIN_CO2_NOMINAL_MMHG)
        self.cabin_co2 = max(0.0, self.cabin_co2 + random.gauss(0, 0.03) + (co2_target - self.cabin_co2) * rate)
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
            heart_rate_bpm=round(hr), systolic_mmhg=round(v["systolic_mmhg"]),
            diastolic_mmhg=round(v["diastolic_mmhg"]), spo2_pct=round(v["spo2_pct"]),
            temp_c=round(v["temp_c"], 1), resp_rate_bpm=round(v["resp_rate_bpm"]),
            sleep_h_last_night=round(v["sleep_h_last_night"], 1),
            mood_1to5=max(1, min(5, round(v["mood_1to5"]))))

    def context(self, t: datetime) -> engine.Context:
        cutoff = store.iso(t - timedelta(hours=24))
        headache = any(ts >= cutoff and "headache" in (p.get("symptoms") or []) for ts, p in self.checkins)
        return engine.Context(cabin_co2_mmhg=self.cabin_co2, headache_24h=headache,
                              sleep_last_nights=self.sleep_nights(),
                              mood=max(1, min(5, round(self.values["mood_1to5"]))))

    def sans(self, t: datetime) -> tuple[int, list[engine.SansComponent]]:
        d7, d14 = store.iso(t - timedelta(days=7)), store.iso(t - timedelta(days=14))
        vision = [(ts, p["vision"]) for ts, p in self.checkins if p.get("vision")]
        latest_acuity = next((vis["acuity_line"] for _, vis in reversed(vision)
                              if vis.get("acuity_line") is not None), None)
        amsler = any(ts >= d14 and vis.get("amsler_distortion") for ts, vis in vision)
        headaches = sum(1 for ts, p in self.checkins if ts >= d7 and "headache" in (p.get("symptoms") or []))
        return engine.sans_score(mission_day(t), self.baseline_acuity, latest_acuity, amsler,
                                 headaches, self.co2_avg_7d)

    def status(self) -> Status:
        if not self.active:
            return "nominal"
        return max((a.severity for a in self.active.values()), key=SEVERITY_RANK.get)


crew = {aid: AstronautState(aid) for aid in engine.CREW}
# Demo default: Mars, Ground stream compressed to 20 s; the verdict uses the real 22 min.
mission = Mission(environment="mars", one_way_delay_s=20, real_one_way_delay_s=1320)
mission_start = now() - timedelta(days=DEFAULT_MISSION_DAY - 1)
seeded_until: Optional[str] = None
light_time: dict = {"live_one_way_delay_s": None, "computed_for": None}
subscribers: dict[str, set[asyncio.Queue]] = {aid: set() for aid in crew}
background: set[asyncio.Task] = set()


def mission_day(t: datetime) -> int:
    return (t - mission_start).days + 1


def get_state(aid: str) -> AstronautState:
    if aid not in crew:
        raise HTTPException(404, f"Unknown astronaut id '{aid}'")
    return crew[aid]


def publish(aid: str, event: str, model: BaseModel) -> None:
    data = model.model_dump_json()
    for q in subscribers[aid]:
        try:
            q.put_nowait((event, data))
        except asyncio.QueueFull:
            pass  # slow client: drop rather than block the server


def spawn(coro) -> None:
    task = asyncio.create_task(coro)
    background.add(task)
    task.add_done_callback(background.discard)


# --- Store view (baselines, CO2, check-ins) ----------------------------------------

def _round_baseline(b: dict) -> dict:
    return {f: (round(v, 1) if f in ("temp_c", "sleep_h_last_night") else round(v)) for f, v in b.items()}


def _load_store_view(t: datetime) -> dict:
    w0, w1 = store.iso(mission_start + timedelta(days=6)), store.iso(mission_start + timedelta(days=14))
    view = {}
    for aid in crew:
        acuity = [p["vision"]["acuity_line"] for _, p in store.checkins_between(aid, w0, w1)
                  if (p.get("vision") or {}).get("acuity_line") is not None]
        view[aid] = dict(
            baseline=store.baseline(aid, w0, w1),
            acuity=statistics.median(acuity) if acuity else None,
            co2=store.co2_avg(aid, store.iso(t - timedelta(days=7))),
            checkins=store.checkins_between(aid, store.iso(t - timedelta(days=14))))
    return view


async def refresh_from_store() -> None:
    view = await asyncio.to_thread(_load_store_view, now())
    for aid, d in view.items():
        s = crew[aid]
        s.baseline_stored = d["baseline"] is not None
        s.baseline = Baseline(**_round_baseline(d["baseline"])) if s.baseline_stored else s.configured
        s.baseline_acuity, s.co2_avg_7d = d["acuity"], d["co2"]
        newest = d["checkins"][-1][0] if d["checkins"] else ""
        s.checkins = d["checkins"] + [c for c in s.checkins if c[0] > newest]  # keep any not yet read back


# --- Alerts ------------------------------------------------------------------------

async def attach_insight(s: AstronautState, alert: Alert, v: dict, ctx: engine.Context,
                         sans_parts: Optional[list[engine.SansComponent]]) -> None:
    # The same alert id is re-sent with insight filled in (null until then).
    b = s.baseline.model_dump()
    fallback = insight_service.Insight(**engine.fallback_insight(
        alert.profile, v, b, ctx, mission.real_one_way_delay_s, sans_parts))
    case_vitals = dict(v)
    if sans_parts:
        case_vitals["sans_risk_components"] = [p.__dict__ for p in sans_parts]
    result = await insight_service.generate_insight(
        alert.profile, case_vitals, b, onboard_action=alert.onboard_action,
        act_within_s=alert.act_within_s, one_way_delay_s=mission.real_one_way_delay_s, fallback=fallback)
    alert.insight = Insight(**result.model_dump())
    store.set_insight(alert.model_dump(mode="json"))
    publish(s.id, "alert", alert)


def raise_alert(s: AstronautState, profile: str, v: dict, ctx: engine.Context,
                sans_parts: Optional[list[engine.SansComponent]] = None) -> Alert:
    p = engine.PROFILES[profile]
    alert = Alert(
        id=f"al-{uuid.uuid4().hex[:8]}", astronaut_id=s.id, profile=profile,
        severity=p["severity"], hazard=p["hazard"], body_region=p["body_region"],
        started_at=now(), onboard_action=p["onboard_action"], act_within_s=p["act_within_s"],
        ground_eta_s=mission.real_one_way_delay_s, insight=None)
    s.alerts.append(alert)
    s.active[profile] = alert
    s.misses[profile] = 0
    store.save_alert(alert.model_dump(mode="json"))
    publish(s.id, "alert", alert)
    log.info("%s: %s alert raised", s.id, profile)
    spawn(attach_insight(s, alert, v, ctx, sans_parts))
    return alert


def clear_alert(s: AstronautState, profile: str) -> None:
    alert = s.active.pop(profile, None)
    s.misses.pop(profile, None)
    if alert:
        store.clear_alert(alert.id, store.iso(now()))
        log.info("%s: %s alert cleared", s.id, profile)


def evaluate_vitals(s: AstronautState, snap: Vitals, t: datetime) -> None:
    v = snap.model_dump(include=set(store.VITAL_FIELDS))
    b = s.baseline.model_dump()
    ctx = s.context(t)
    for profile in engine.VITALS_PROFILES:
        if engine.matches(profile, v, b, ctx):
            s.misses[profile] = 0
            if profile not in s.active:  # the NEW-match gate
                raise_alert(s, profile, v, ctx)
        elif profile in s.active:
            s.misses[profile] = s.misses.get(profile, 0) + 1
            if s.misses[profile] >= engine.CLEAR_AFTER_TICKS:
                clear_alert(s, profile)


def evaluate_sans(s: AstronautState, t: datetime) -> None:
    score, parts = s.sans(t)
    if score >= engine.SANS_TRIGGER and "sans" not in s.active:
        v = s.snapshot().model_dump(include=set(store.VITAL_FIELDS))
        raise_alert(s, "sans", v, s.context(t), parts)
    elif score < engine.SANS_CLEAR and "sans" in s.active:
        clear_alert(s, "sans")


# --- Background loops ------------------------------------------------------------

async def tick_loop() -> None:
    ticks = 0
    while True:
        await asyncio.sleep(TICK_S)
        try:
            t = now()
            for aid, s in crew.items():
                s.tick()
                snap = s.snapshot()
                store.add_sample(aid, store.iso(t), snap.model_dump(include=set(store.VITAL_FIELDS)),
                                 round(s.cabin_co2, 2), snap.source)
                publish(aid, "vitals", snap)
                evaluate_vitals(s, snap, t)
            ticks += 1
            if ticks % REFRESH_EVERY_TICKS == 0:
                await refresh_from_store()
                for s in crew.values():
                    evaluate_sans(s, t)
        except Exception:
            log.exception("tick failed; carrying on")  # the demo must keep running


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
    for s in crew.values():
        evaluate_sans(s, t)
    spawn(tick_loop())
    spawn(fetch_light_time())
    yield
    for task in list(background):
        task.cancel()
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
    subscribers[aid].add(q)
    pending: deque = deque()  # (release_at, event, data); ground view holds events back
    try:
        yield f": connected view={view} one_way_delay_s={mission.one_way_delay_s}\n\n"
        if view == "crew":
            yield sse("vitals", crew[aid].snapshot().model_dump_json())
        while not await request.is_disconnected():
            timeout = 15.0
            if pending:
                timeout = max(0.0, min(timeout, pending[0][0] - loop.time()))
            try:
                event, data = await asyncio.wait_for(q.get(), timeout)
                delay = mission.one_way_delay_s if view == "ground" else 0
                pending.append((loop.time() + delay, event, data))
            except asyncio.TimeoutError:
                if not pending:
                    yield ": keepalive\n\n"
            while pending and pending[0][0] <= loop.time():
                _, event, data = pending.popleft()
                yield sse(event, data)
    finally:
        subscribers[aid].discard(q)


@app.get("/astronauts/{aid}/stream")
async def stream(aid: str, request: Request, view: Literal["crew", "ground"] = "crew"):
    get_state(aid)
    return StreamingResponse(
        event_stream(request, aid, view), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/astronauts/{aid}/alerts")
async def get_alerts(aid: str) -> list[Alert]:
    return list(reversed(get_state(aid).alerts))  # newest first


@app.get("/mission")
async def get_mission() -> Mission:
    return mission


@app.put("/mission")
async def put_mission(body: Mission) -> Mission:
    global mission
    mission = body
    return mission


async def record_checkin(s: AstronautState, body: CheckinRequest) -> None:
    ts = store.iso(body.timestamp)
    payload = body.model_dump(mode="json", exclude_none=True)
    await asyncio.to_thread(store.add_checkin, s.id, ts, payload)
    s.checkins = sorted(s.checkins + [(ts, payload)], key=lambda c: c[0])
    if body.mood_1to5 is not None:
        s.manual["mood_1to5"] = body.mood_1to5
    if body.sleep_h is not None:
        s.manual["sleep_h_last_night"] = body.sleep_h
    evaluate_sans(s, now())  # a single check-in can tip the SANS score over


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
        for profile in list(s.active):
            clear_alert(s, profile)
        if seeded_until:  # drop live check-ins so the SANS demo can run again
            await asyncio.to_thread(store.delete_checkins_after, s.id, seeded_until)
            s.checkins = [c for c in s.checkins if c[0] <= seeded_until]
    elif body.scenario == "sans":
        # Same path as a real astronaut's check-in: headache + Amsler distortion + acuity one line down.
        acuity = round(s.baseline_acuity or 9) - 1
        await record_checkin(s, CheckinRequest(
            timestamp=now(), symptoms=["headache"], share_with_ground=True,
            vision=Vision(amsler_distortion=True, acuity_line=acuity)))
    else:
        s.scenario = body.scenario
        s.manual.clear()
    return Accepted()


# --- PROVISIONAL: SANS risk, history, live light time (not yet in docs/api-spec.md) ---

@app.get("/astronauts/{aid}/sans")
async def get_sans(aid: str, view: Literal["crew", "ground"] = "crew") -> SansRisk:
    s = get_state(aid)
    t = now()
    score, parts = s.sans(t)
    checks = await asyncio.to_thread(store.checkins_between, aid, store.iso(mission_start))
    private_recent = any(not p.get("share_with_ground") for ts, p in checks
                         if ts >= store.iso(t - timedelta(days=14)))
    if view == "ground":
        checks = [c for c in checks if c[1].get("share_with_ground")]
    components = [SansComponent(name=p.name, points=p.points,
                                detail=PRIVATE_DETAIL if view == "ground" and private_recent
                                and p.name in ("vision_acuity", "amsler_grid", "headaches") else p.detail)
                  for p in parts]
    vision_checks = [
        VisionCheck(ts=ts, acuity_line=(p.get("vision") or {}).get("acuity_line"),
                    amsler_distortion=(p.get("vision") or {}).get("amsler_distortion"),
                    headache="headache" in (p.get("symptoms") or []))
        for ts, p in checks if p.get("vision") or "headache" in (p.get("symptoms") or [])]
    return SansRisk(
        astronaut_id=aid, mission_day=mission_day(t), score=score, trigger_at=engine.SANS_TRIGGER,
        status="watch" if score >= engine.SANS_TRIGGER else "nominal",
        baseline_acuity=s.baseline_acuity, components=components, vision_checks=vision_checks,
        note="A between-scans risk score, never a diagnosis: it suggests when an OCT scan or a talk with "
             "the flight surgeon may be worthwhile.",
        source_url=engine.SANS_URL)


@app.get("/astronauts/{aid}/history")
async def get_history(aid: str, hours: float = Query(24, gt=0, le=24 * 60)) -> list[HistoryPoint]:
    get_state(aid)
    bucket_s = max(TICK_S, int(hours * 3600 / 300))  # at most ~300 points per chart
    rows = await asyncio.to_thread(store.history, aid, store.iso(now() - timedelta(hours=hours)), bucket_s)
    return [HistoryPoint(**r) for r in rows]


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
# Private by default: the ground view gets 403 unless the astronaut shares it.

@app.get("/astronauts/{aid}/circadian")
async def get_circadian(aid: str, view: Literal["crew", "ground"] = "crew") -> circadian.Circadian:
    get_state(aid)
    if view == "ground" and not circadian.is_shared(aid):
        raise HTTPException(403, "Not shared: the astronaut keeps sleep and lighting data private.")
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
