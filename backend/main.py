"""Mock backend: every endpoint in docs/api-spec.md, returning live-looking data.

Vitals are a mean-reverting random walk around each astronaut's own baseline,
and a fake alert fires on a1 every ~60 s (insight canned, re-sent ~2 s later).
Per STATUS.md Phase 2 scope: no /space-weather (spe is being cut) and
/debug/scenario is a stub until the scenario enum settles. The real baseline,
condition engine and insight_service.py replace the mock parts later.

Run:  uvicorn main:app --reload   ->  http://localhost:8000/docs
"""

import asyncio
import os
import random
import uuid
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import circadian

TICK_S = 3
AUTO_ALERT_EVERY_S = int(os.getenv("MOCK_AUTO_ALERT_S", "60"))  # 0 turns it off
INSIGHT_DELAY_S = 2  # mock "Claude is thinking" delay before insight arrives
REAL_HR_FRESH_S = 10  # watch HR older than this falls back to simulated

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
    one_way_delay_s: int


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
    scenario: str  # enum is changing with the SANS pivot; free string until then


# --- Mock data ---------------------------------------------------------------

# Every astronaut gets a genuinely different baseline (docs/monitored-signals.md).
CREW = {
    "a1": ("Cmdr. Elena Ionescu", "Commander",
           Baseline(heart_rate_bpm=58, systolic_mmhg=112, diastolic_mmhg=72, spo2_pct=98,
                    temp_c=36.5, resp_rate_bpm=12, sleep_h_last_night=7.2, mood_1to5=4)),
    "a2": ("Mihai Popa", "Flight Engineer",
           Baseline(heart_rate_bpm=74, systolic_mmhg=124, diastolic_mmhg=80, spo2_pct=97,
                    temp_c=36.8, resp_rate_bpm=15, sleep_h_last_night=6.8, mood_1to5=4)),
    "a3": ("Dr. Sara Okafor", "Crew Medical Officer",
           Baseline(heart_rate_bpm=66, systolic_mmhg=118, diastolic_mmhg=76, spo2_pct=98,
                    temp_c=36.6, resp_rate_bpm=13, sleep_h_last_night=7.5, mood_1to5=5)),
    "a4": ("Jonas Berg", "Mission Specialist",
           Baseline(heart_rate_bpm=62, systolic_mmhg=116, diastolic_mmhg=74, spo2_pct=98,
                    temp_c=36.4, resp_rate_bpm=14, sleep_h_last_night=7.0, mood_1to5=4)),
}

# Canned alert content for the mock only, NOT the condition engine (that waits
# for the post-pivot spec). Wording is placeholder. `sans` is provisional.
PROFILES = {
    "orthostatic": dict(
        severity="alert", hazard="gravity", body_region="heart", act_within_s=600,
        onboard_action="Lie flat, legs raised. Drink 500 ml with salt tablets, re-measure in 10 min.",
        insight=Insight(
            why="Heart rate is well above your own baseline while systolic pressure is below it, "
                "a pattern that can point to cardiovascular deconditioning in low gravity.",
            trend="Heart rate up ~30% and systolic down ~18% versus your mission-day 7-14 baseline.",
            recommended_action="Lie down with legs raised, take fluids with salt, and re-check in 10 minutes. "
                               "If it persists, tell the Crew Medical Officer.")),
    "fever": dict(
        severity="alert", hazard="environment", body_region="skin", act_within_s=3600,
        onboard_action="Rest, drink fluids, log temperature every hour.",
        insight=Insight(
            why="Temperature and heart rate are rising together above your baseline, which may suggest "
                "an infection. Immune function can change in spaceflight.",
            trend="Temperature about 1.3 C over baseline, heart rate up ~18% over the last few minutes.",
            recommended_action="Rest, hydrate and log your temperature hourly. Consider limiting close "
                               "contact with crewmates until it settles.")),
    "co2": dict(
        severity="alert", hazard="environment", body_region="lungs", act_within_s=900,
        onboard_action="Move to a well-ventilated module and check the CO2 scrubber reading.",
        insight=Insight(
            why="Breathing rate is up together with heart rate, which can happen when cabin CO2 builds up.",
            trend="Respiratory rate about 35% above your baseline, heart rate up ~10%.",
            recommended_action="Move to a better-ventilated module, check the CO2 readout and report "
                               "a headache if you have one.")),
    "sleep_debt": dict(
        severity="watch", hazard="isolation", body_region="head", act_within_s=86400,
        onboard_action="Consider pre-sleep lighting (2700K) 1 h before bed, screens aside, eye mask.",
        insight=Insight(
            why="Short sleep for several nights, lower mood and a raised resting heart rate together "
                "may indicate accumulating sleep debt and strain.",
            trend="Sleep about 30% under your usual, mood down to 2/5, resting heart rate up ~8%.",
            recommended_action="You might consider protecting tonight's sleep: the station's pre-sleep "
                               "lighting mode (2700K, less blue light) about 1 h before bed can help. "
                               "A private conference with the flight surgeon or a talk with a crewmate "
                               "is always an option.")),
    "sans": dict(
        severity="watch", hazard="gravity", body_region="head", act_within_s=86400,
        onboard_action="Do an Amsler grid and acuity check today; log any headache.",
        insight=Insight(
            why="Your SANS risk score is rising: vision check results, cabin CO2 and headache reports "
                "together are worth a closer look. This is a risk score, not a diagnosis.",
            trend="Risk score up over the last mission days.",
            recommended_action="Repeat the vision check and consider asking for an OCT scan.")),
}

AUTO_CYCLE = ["fever", "co2", "orthostatic", "sleep_debt", "sans"]
SEVERITY_RANK = {"watch": 1, "alert": 2, "critical": 3}
WALK_STEP = {"heart_rate_bpm": 1.0, "systolic_mmhg": 1.0, "diastolic_mmhg": 0.7,
             "spo2_pct": 0.2, "temp_c": 0.02, "resp_rate_bpm": 0.3}


class AstronautState:
    def __init__(self, aid: str):
        self.id = aid
        self.name, self.role, self.baseline = CREW[aid]
        self.values = {k: float(v) for k, v in self.baseline.model_dump().items()}
        self.values["sleep_h_last_night"] = circadian.last_sleep_h(aid)
        self.real_hr: Optional[tuple[float, float, str]] = None  # watch (bpm, loop time, source)
        self.alerts: list[Alert] = []
        self.active: dict[str, Alert] = {}  # profile -> alert
        self.checkins: list[CheckinRequest] = []
        self.manual: dict[str, float] = {}  # sleep/mood from the latest check-in

    def tick(self) -> None:
        for field, step in WALK_STEP.items():
            v = self.values[field]
            self.values[field] = v + random.gauss(0, step) + (getattr(self.baseline, field) - v) * 0.1
        self.values["spo2_pct"] = min(self.values["spo2_pct"], 100.0)
        # Last night's sleep comes from the on-board lighting log unless the check-in says otherwise.
        self.values["sleep_h_last_night"] = self.manual.get("sleep_h_last_night", circadian.last_sleep_h(self.id))
        self.values["mood_1to5"] = self.manual.get("mood_1to5", self.baseline.mood_1to5)

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

    def status(self) -> Status:
        if not self.active:
            return "nominal"
        return max((a.severity for a in self.active.values()), key=SEVERITY_RANK.get)


crew = {aid: AstronautState(aid) for aid in CREW}
# Demo default: Mars, compressed to ~20 s one way (real Mars is 180-1320 s).
mission = Mission(environment="mars", one_way_delay_s=20)
subscribers: dict[str, set[asyncio.Queue]] = {aid: set() for aid in CREW}
background: set[asyncio.Task] = set()


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


async def attach_insight(aid: str, alert: Alert) -> None:
    # Mock of the Claude call: the same alert id is re-sent with insight filled in.
    await asyncio.sleep(INSIGHT_DELAY_S)
    alert.insight = PROFILES[alert.profile]["insight"]
    publish(aid, "alert", alert)


def raise_alert(aid: str, profile: str) -> Alert:
    p = PROFILES[profile]
    alert = Alert(
        id=f"al-{uuid.uuid4().hex[:8]}", astronaut_id=aid, profile=profile,
        severity=p["severity"], hazard=p["hazard"], body_region=p["body_region"],
        started_at=now(), onboard_action=p["onboard_action"], act_within_s=p["act_within_s"],
        ground_eta_s=mission.one_way_delay_s, insight=None)
    state = crew[aid]
    state.alerts.append(alert)
    state.active[profile] = alert
    publish(aid, "alert", alert)
    spawn(attach_insight(aid, alert))
    return alert


async def tick_loop() -> None:
    auto_i, since_auto = 0, 0
    while True:
        await asyncio.sleep(TICK_S)
        for aid, state in crew.items():
            state.tick()
            publish(aid, "vitals", state.snapshot())
        since_auto += TICK_S
        if AUTO_ALERT_EVERY_S and since_auto >= AUTO_ALERT_EVERY_S:
            since_auto = 0
            crew["a1"].active.clear()
            raise_alert("a1", AUTO_CYCLE[auto_i % len(AUTO_CYCLE)])
            auto_i += 1


@asynccontextmanager
async def lifespan(app: FastAPI):
    spawn(tick_loop())
    yield
    for task in list(background):
        task.cancel()


app = FastAPI(title="Astronaut Health Monitor — mock backend", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# --- Endpoints -----------------------------------------------------------------

@app.get("/")
async def root() -> dict:
    return {"service": "astronaut-health-monitor backend (mock)", "docs": "/docs"}


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


@app.post("/astronauts/{aid}/checkin", status_code=202)
async def checkin(aid: str, body: CheckinRequest) -> Accepted:
    state = get_state(aid)
    state.checkins.append(body)
    if body.mood_1to5 is not None:
        state.manual["mood_1to5"] = body.mood_1to5
    if body.sleep_h is not None:
        state.manual["sleep_h_last_night"] = body.sleep_h
    return Accepted()


@app.post("/debug/scenario", status_code=202)
async def debug_scenario(body: ScenarioRequest) -> Accepted:
    # Stub: accepted and ignored until the post-pivot scenario enum is in the spec.
    get_state(body.astronaut_id)
    return Accepted()


# --- Circadian / lighting (PROVISIONAL, not yet in docs/api-spec.md) ------------
# Private by default: the ground view gets 403 unless the astronaut shares it.

@app.get("/astronauts/{aid}/circadian")
async def get_circadian(aid: str, view: Literal["crew", "ground"] = "crew") -> circadian.Circadian:
    get_state(aid)
    if view == "ground" and not circadian.is_shared(aid):
        raise HTTPException(403, "Not shared: the astronaut keeps sleep and lighting data private.")
    return circadian.assess(aid, now())


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
