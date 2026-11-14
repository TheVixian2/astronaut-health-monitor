# Written with AI assistance (Claude Code, Anthropic) and reviewed by the team. See README "Use of AI".
"""Circadian rhythm: a countermeasure loop built on the on-board lighting (PROVISIONAL).

The loop: detect body-clock drift -> suggest a lighting plan -> verify sleep improved.

Detect: instead of asking the astronaut, we read the station's lighting log. The ISS
Solid-State Lighting Assembly (SSLA) runs General (4500K), Pre-sleep (2700K,
blue-depleted) and Phase-shift (6500K, blue-enriched) modes (NTRS 20160005080,
20200011570). Here each crew member's quarters' log is simulated, with different habits.

Suggest: a lighting plan made of those same three modes. Morning blue-enriched light
pulls a late-drifting clock earlier; warm light before bed lets melatonin rise.

Verify: compare the nights before and after the astronaut chose to follow the plan.

Why it matters: blue light at the wrong time suppresses melatonin and shifts the body
clock, and circadian disruption is linked to immune dysregulation (PMC8564795) and to
latent-virus reactivation in ISS crew (Frontiers Microbiol 2019). On the way to Mars
there is no day or night at all, so the lighting is the only cue left. Linked, not
proven, so all wording stays suggestive.

Ethics rules for this module (sleeping-quarters data is personal):
- Shared with Mission Control by default, like a doctor would see it (team
  decision, NotKaemy 2026-11-14). The astronaut can opt out at any time, and the
  ground view then gets 403. On the shared ship console the web app keeps it
  hidden until the astronaut taps to show it.
- Suggest, never instruct: no orders, no diagnosis, no alarming claims, and
  every claim links to its source. The astronaut chooses whether to follow a plan.
- The app never changes the lighting itself; the crew does.
- No comparison between crew members, and it never feeds crew status or alerts.
"""

import datetime as dt
import random
import statistics
from typing import Literal, Optional

from pydantic import BaseModel

LightingMode = Literal["general", "pre_sleep", "phase_shift", "off"]
CCT_K = {"general": 4500, "pre_sleep": 2700, "phase_shift": 6500, "off": 0}

SSLA_SOURCE = "NASA ISS Solid-State Lighting Assembly: general 4500K, pre-sleep 2700K, phase-shift 6500K"
SSLA_URL = "https://ntrs.nasa.gov/citations/20160005080"
IMMUNE_SOURCE = "Light at night disrupts biological clocks, calendars, and immune function (2021)"
IMMUNE_URL = "https://pmc.ncbi.nlm.nih.gov/articles/PMC8564795"

# Thresholds are PLACEHOLDERS pending tuning.
NIGHTS = 7
PRE_SLEEP_TARGET_MIN = 60     # SSLA pre-sleep mode on for ~1 h before lights off
PRE_SLEEP_MIN_OK = 30         # less than this counts as "bright light before sleep"
BEDTIME_SPREAD_WATCH_MIN = 60
NIGHTS_BRIGHT_WATCH = 3
DRIFT_WATCH_MIN = 10          # body clock sliding >= 10 min per night
MIN_NIGHTS_TO_VERIFY = 2

# Per-astronaut habits: planned bedtime (UTC hour), bedtime jitter (min), usual sleep (h),
# chance the pre-sleep mode is used, drift (min later per night).
HABITS = {
    "a1": (22.0, 12, 7.2, 0.9, 0),
    "a2": (22.5, 15, 6.6, 0.4, 15),   # drifting later and irregular: the demo story
    "a3": (22.5, 12, 7.5, 0.85, 0),
    "a4": (22.5, 18, 7.0, 0.95, 0),
}

ENVIRONMENT_NOTE = {
    "iss": "Outside, the station sees about 16 sunrises a day, so the station lighting is your "
           "steadiest day-night cue.",
    "moon": "A lunar day lasts about 29.5 Earth days, so outside light gives no 24-hour cue. The "
            "lighting schedule is what keeps your body on Earth time.",
    "mars": "On the way to Mars there is no day or night at all, and on the surface a day (sol) "
            "lasts 24 h 39 min. The lighting system is the only cue keeping your body on an "
            "Earth-like rhythm.",
}


class Lighting(BaseModel):
    mode: LightingMode
    cct_k: int
    since: dt.datetime


class LightingRequest(BaseModel):
    mode: LightingMode


class SharingRequest(BaseModel):
    share_with_ground: bool


class PlanRequest(BaseModel):
    accepted: bool


class Night(BaseModel):
    night_of: dt.date
    bedtime: dt.datetime
    wake_time: dt.datetime
    sleep_h: float
    pre_sleep_lighting_min: int
    bright_light_last_hour: bool
    following_plan: bool


class CircadianSummary(BaseModel):
    status: Literal["nominal", "watch", "improving"]  # improving = plan followed and it's working
    nights: int
    bedtime_spread_min: int
    nights_bright_before_sleep: int
    drift_min_per_night: float  # + later each night, - earlier
    sleep_avg_h: float
    target_bedtime: str         # station time (UTC), "HH:MM"


class PlanStep(BaseModel):
    start: str  # "HH:MM" station time (UTC)
    end: str
    mode: LightingMode
    cct_k: int
    why: str


class Plan(BaseModel):
    goal: str
    steps: list[PlanStep]
    accepted: bool
    accepted_on: Optional[dt.date]
    note: str
    source: str
    source_url: str


class Stats(BaseModel):
    nights: int
    bedtime_spread_min: int
    drift_min_per_night: float
    sleep_avg_h: float
    nights_bright_before_sleep: int


class Verification(BaseModel):
    nights_since_plan: int
    before: Stats
    after: Optional[Stats]
    improved: Optional[bool]  # null until there are enough nights to tell
    message: str


class Recommendation(BaseModel):
    text: str
    source: str
    source_url: str


class Circadian(BaseModel):
    astronaut_id: str
    share_with_ground: bool  # astronaut's choice; True by default, opt-out any time
    environment_note: str
    lighting: Lighting
    nights: list[Night]      # the last 7 nights
    summary: CircadianSummary
    card: Optional[str]      # Self-check message; null when nothing stands out
    recommendation: Recommendation
    plan: Plan
    verification: Optional[Verification]  # present once a plan has been accepted
    evidence: Recommendation


def _utc_midnight(day: dt.date) -> dt.datetime:
    return dt.datetime.combine(day, dt.time(0), tzinfo=dt.timezone.utc)


def _hhmm(minutes: float) -> str:
    m = round(minutes) % (24 * 60)
    return f"{m // 60:02d}:{m % 60:02d}"


def _after_18(t: dt.datetime) -> int:
    # Minutes after 18:00, so times either side of midnight compare correctly.
    return ((t.hour - 18) % 24) * 60 + t.minute


class _Astronaut:
    def __init__(self, aid: str, today: dt.date):
        self.id = aid
        self.today = today
        self.reset()

    def reset(self) -> None:
        self.rng = random.Random(f"circadian-{self.id}")  # same history on every restart
        self.nights: list[Night] = []
        self.plan_from: Optional[int] = None  # index of the first night on the plan
        self.plan_accepted_on: Optional[dt.date] = None
        self.plan_drift: Optional[float] = None  # drift when accepted, so the plan stays fixed
        self.override: Optional[Lighting] = None
        start = self.today - dt.timedelta(days=NIGHTS)
        for i in range(NIGHTS):
            self.add_night(start + dt.timedelta(days=i))

    def add_night(self, day: dt.date) -> None:
        bed_hour, jitter, sleep_h, p_pre, drift = HABITS[self.id]
        i = len(self.nights)
        following = self.plan_from is not None and i >= self.plan_from
        rng = self.rng
        if following:
            # Lighting plan followed: bedtime back near target, more consistent sleep.
            late = rng.gauss(0, 10)
            hours = rng.gauss(sleep_h + 0.5, 0.25)
            used = rng.random() < 0.95
        else:
            late = drift * i + rng.gauss(0, jitter)
            hours = rng.gauss(sleep_h, 0.35) - max(0.0, late) / 60 * 0.5  # fixed wake-up schedule
            used = rng.random() < p_pre
        hours = round(min(9.0, max(4.0, hours)), 1)
        pre_min = max(0, round(rng.gauss(PRE_SLEEP_TARGET_MIN, 10))) if used else round(rng.uniform(0, 15))
        bedtime = (_utc_midnight(day) + dt.timedelta(hours=bed_hour, minutes=late)).replace(second=0, microsecond=0)
        self.nights.append(Night(
            night_of=day, bedtime=bedtime,
            wake_time=(bedtime + dt.timedelta(hours=hours)).replace(second=0, microsecond=0),
            sleep_h=hours, pre_sleep_lighting_min=pre_min,
            bright_light_last_hour=pre_min < PRE_SLEEP_MIN_OK, following_plan=following))


_today = dt.datetime.now(dt.timezone.utc).date()
_crew: dict[str, _Astronaut] = {aid: _Astronaut(aid, _today) for aid in HABITS}
_shared: dict[str, bool] = {aid: True for aid in HABITS}  # shared by default; astronaut can opt out


def is_shared(aid: str) -> bool:
    return _shared[aid]


def set_shared(aid: str, share: bool) -> None:
    _shared[aid] = share


def last_sleep_h(aid: str) -> float:
    return _crew[aid].nights[-1].sleep_h


def recent_sleep_h(aid: str, n: int) -> list[float]:
    """Sleep of the last n nights, most recent last (feeds the sleep_debt profile)."""
    return [night.sleep_h for night in _crew[aid].nights[-n:]]


def _stats(nights: list[Night]) -> Stats:
    beds = [_after_18(n.bedtime) for n in nights]
    mids = [_after_18(n.bedtime) + n.sleep_h * 30 for n in nights]  # mid-sleep
    drift = statistics.linear_regression(range(len(mids)), mids).slope if len(mids) >= 2 else 0.0
    return Stats(
        nights=len(nights), bedtime_spread_min=max(beds) - min(beds),
        drift_min_per_night=round(drift, 1),
        sleep_avg_h=round(statistics.fmean(n.sleep_h for n in nights), 1),
        nights_bright_before_sleep=sum(n.bright_light_last_hour for n in nights))


def _sim_now(a: _Astronaut, now: dt.datetime) -> dt.datetime:
    # After a demo fast-forward the log runs ahead of the clock; read it from there.
    return max(now, a.nights[-1].wake_time + dt.timedelta(hours=1))


def current_lighting(aid: str, now: dt.datetime) -> Lighting:
    a = _crew[aid]
    if a.override:
        return a.override
    now = _sim_now(a, now)
    bed_hour, _, _, p_pre, _ = HABITS[aid]
    tonight = _utc_midnight(now.date()) + dt.timedelta(hours=bed_hour)
    if now >= tonight:
        mode, since = "off", tonight
    elif now >= tonight - dt.timedelta(minutes=PRE_SLEEP_TARGET_MIN) and p_pre >= 0.5:
        mode, since = "pre_sleep", tonight - dt.timedelta(minutes=PRE_SLEEP_TARGET_MIN)
    else:
        mode, since = "general", a.nights[-1].wake_time
    return Lighting(mode=mode, cct_k=CCT_K[mode], since=since)


def set_lighting(aid: str, mode: str, now: dt.datetime) -> Lighting:
    _crew[aid].override = Lighting(mode=mode, cct_k=CCT_K[mode], since=now.replace(microsecond=0))
    return _crew[aid].override


def set_plan(aid: str, accepted: bool, now: dt.datetime) -> None:
    a = _crew[aid]
    if accepted and a.plan_from is None:
        a.plan_from = len(a.nights)  # applies from tonight
        a.plan_accepted_on = _sim_now(a, now).date()
        a.plan_drift = _stats(a.nights[-NIGHTS:]).drift_min_per_night
    elif not accepted:
        a.plan_from, a.plan_accepted_on, a.plan_drift = None, None, None


def advance(aid: str, nights: int) -> None:
    """Demo only: fast-forward the lighting log by n nights."""
    a = _crew[aid]
    for _ in range(nights):
        a.add_night(a.nights[-1].night_of + dt.timedelta(days=1))
    a.override = None


def reset(aid: str) -> None:
    _crew[aid].reset()


def _plan(a: _Astronaut, s: Stats, accepted: bool) -> Plan:
    bed_hour, _, sleep_h, _, _ = HABITS[a.id]
    bed = bed_hour * 60
    wake = bed + round(sleep_h * 60 / 15) * 15

    def step(start, end, mode, why):
        return PlanStep(start=_hhmm(start), end=_hhmm(end), mode=mode, cct_k=CCT_K[mode], why=why)

    drift = a.plan_drift if accepted else s.drift_min_per_night
    if drift >= DRIFT_WATCH_MIN:
        goal = f"Bring your body clock back toward a {_hhmm(bed)} bedtime."
        steps = [
            step(wake, wake + 60, "phase_shift",
                 "Bright, blue-enriched light soon after waking may help move a late-drifting body clock earlier."),
            step(wake + 60, bed - 60, "general", "Neutral daytime light."),
        ]
    elif drift <= -DRIFT_WATCH_MIN:
        goal = f"Ease your body clock back toward a {_hhmm(bed)} bedtime."
        steps = [
            step(wake, bed - 180, "general", "Neutral daytime light."),
            step(bed - 180, bed - 120, "phase_shift",
                 "Bright light in the early evening may help move an early-drifting body clock later."),
            step(bed - 120, bed - 60, "general", "Neutral light."),
        ]
    else:
        goal = f"Keep a steady rhythm around a {_hhmm(bed)} bedtime."
        steps = [step(wake, bed - 60, "general", "Neutral daytime light.")]
    steps += [
        step(bed - 60, bed, "pre_sleep", "Warm light with less blue lets melatonin rise before sleep."),
        step(bed, wake, "off", "Dark for sleep."),
    ]
    note = ("This is a suggestion, and you choose whether to follow it. The app never changes the lights "
            "itself. Phase-shift lighting is normally used with Mission Control guidance, so it may be "
            "worth mentioning at your next private medical conference.")
    return Plan(goal=goal, steps=steps, accepted=accepted, accepted_on=a.plan_accepted_on,
                note=note, source=SSLA_SOURCE, source_url=SSLA_URL)


def _verification(a: _Astronaut) -> Optional[Verification]:
    if a.plan_from is None:
        return None
    before = _stats(a.nights[max(0, a.plan_from - NIGHTS):a.plan_from])
    since = a.nights[a.plan_from:]
    if len(since) < MIN_NIGHTS_TO_VERIFY:
        return Verification(
            nights_since_plan=len(since), before=before, after=None, improved=None,
            message="Too early to tell. Your sleep will be compared with the week before after a couple of nights.")
    after = _stats(since)
    improved = (after.bedtime_spread_min < before.bedtime_spread_min and after.sleep_avg_h >= before.sleep_avg_h)
    if improved:
        message = (f"Since you started the lighting plan {len(since)} nights ago, your bedtime varied by "
                   f"{after.bedtime_spread_min / 60:.1f} h (was {before.bedtime_spread_min / 60:.1f} h) and "
                   f"you slept {after.sleep_avg_h} h on average (was {before.sleep_avg_h} h).")
    else:
        message = (f"After {len(since)} nights on the lighting plan there is no clear change yet. "
                   f"It may need more time, or a different plan could suit you better.")
    return Verification(nights_since_plan=len(since), before=before, after=after,
                        improved=improved, message=message)


def assess(aid: str, now: dt.datetime, environment: str = "mars") -> Circadian:
    a = _crew[aid]
    nights = a.nights[-NIGHTS:]
    s = _stats(nights)
    irregular = s.bedtime_spread_min > BEDTIME_SPREAD_WATCH_MIN
    too_bright = s.nights_bright_before_sleep >= NIGHTS_BRIGHT_WATCH
    drifting = abs(s.drift_min_per_night) >= DRIFT_WATCH_MIN
    accepted = a.plan_from is not None
    verification = _verification(a)
    lighting = current_lighting(aid, now)
    bed_hour = HABITS[aid][0]

    card = None
    if verification and verification.improved:
        card = verification.message
    elif irregular or too_bright or drifting:
        parts = []
        if drifting:
            direction = "later" if s.drift_min_per_night > 0 else "earlier"
            parts.append(f"Your sleep has been shifting about {abs(s.drift_min_per_night):.0f} min "
                         f"{direction} each night.")
        if irregular:
            parts.append(f"Your bedtime varied by about {s.bedtime_spread_min / 60:.1f} h over the last "
                         f"{len(nights)} nights.")
        if too_bright:
            parts.append(f"On {s.nights_bright_before_sleep} of {len(nights)} nights your quarters were "
                         f"still in bright light shortly before sleep.")
        parts.append("Irregular sleep timing and blue-rich light before bed may shift your body clock, "
                     "and body-clock disruption has been linked to changes in immune function.")
        card = " ".join(parts)

    sim_now = _sim_now(a, now)
    minutes_to_bed = (_utc_midnight(sim_now.date()) + dt.timedelta(hours=bed_hour) - sim_now).total_seconds() / 60
    if lighting.mode in ("general", "phase_shift") and 0 < minutes_to_bed <= 120:
        text = (f"Your usual bedtime is in about {round(minutes_to_bed)} min. You might consider switching "
                f"your quarters to pre-sleep lighting and setting screens aside.")
    else:
        text = ("You might consider switching your quarters to pre-sleep lighting about 1 h before bed "
                "and setting screens aside.")
    if (irregular or drifting) and not accepted:
        text += " A lighting plan built on the station's own lighting modes is ready if you'd like to try it."

    return Circadian(
        astronaut_id=aid, share_with_ground=is_shared(aid),
        environment_note=ENVIRONMENT_NOTE.get(environment, ENVIRONMENT_NOTE["mars"]),
        lighting=lighting, nights=nights,
        summary=CircadianSummary(
            status=("improving" if verification and verification.improved
                    else "watch" if (irregular or too_bright or drifting) else "nominal"),
            nights=s.nights, bedtime_spread_min=s.bedtime_spread_min,
            nights_bright_before_sleep=s.nights_bright_before_sleep,
            drift_min_per_night=s.drift_min_per_night, sleep_avg_h=s.sleep_avg_h,
            target_bedtime=_hhmm(bed_hour * 60)),
        card=card,
        recommendation=Recommendation(text=text, source=SSLA_SOURCE, source_url=SSLA_URL),
        plan=_plan(a, s, accepted),
        verification=verification,
        evidence=Recommendation(
            text="Circadian disruption is associated with immune changes; most evidence is from animal studies.",
            source=IMMUNE_SOURCE, source_url=IMMUNE_URL))
