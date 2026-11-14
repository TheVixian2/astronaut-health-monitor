"""Circadian rhythm from the on-board lighting log (provisional, not yet in docs/api-spec.md).

Instead of asking the astronaut about light before bed, we read the station's
lighting system. The ISS Solid-State Lighting Assembly (SSLA) runs General
(4500K), Pre-sleep (2700K, blue-depleted) and Phase-shift (6500K, blue-enriched)
modes (NTRS 20160005080, 20200011570). Here each crew member's quarters' SSLA
log is simulated, with different habits per astronaut.

Why it matters: blue light at the wrong time suppresses melatonin and shifts the
body clock, and circadian disruption is linked to immune dysregulation
(PMC8564795) and to latent-virus reactivation in ISS crew (Frontiers Microbiol
2019). Linked, not proven, so all wording stays suggestive.

Ethics rules for this module (sleeping-quarters data is personal):
- Private by default: only the astronaut sees it. The ground view gets it only
  if the astronaut turns sharing on, and can turn it off again.
- Suggest, never instruct: no orders, no diagnosis, no alarming claims, and
  every claim links to its source.
- The app never changes the lighting itself; the crew does.
- No comparison between crew members, and it never feeds crew status or alerts.
"""

import datetime as dt
import random
from typing import Literal, Optional

from pydantic import BaseModel

LightingMode = Literal["general", "pre_sleep", "phase_shift", "off"]
CCT_K = {"general": 4500, "pre_sleep": 2700, "phase_shift": 6500, "off": 0}

SSLA_SOURCE = "NASA ISS Solid-State Lighting Assembly: pre-sleep mode (2700K, blue-depleted)"
SSLA_URL = "https://ntrs.nasa.gov/citations/20160005080"
IMMUNE_SOURCE = "Light at night disrupts biological clocks, calendars, and immune function (2021)"
IMMUNE_URL = "https://pmc.ncbi.nlm.nih.gov/articles/PMC8564795"

# Thresholds are PLACEHOLDERS pending tuning.
NIGHTS = 7
PRE_SLEEP_TARGET_MIN = 60     # SSLA pre-sleep mode on for ~1 h before lights off
PRE_SLEEP_MIN_OK = 30         # less than this counts as "bright light before sleep"
BEDTIME_SPREAD_WATCH_MIN = 60
NIGHTS_BRIGHT_WATCH = 3

# Per-astronaut habits: usual bedtime (UTC hour), bedtime jitter (min),
# usual sleep (h), chance the pre-sleep mode is used on a given night.
HABITS = {
    "a1": (22.0, 15, 7.2, 0.9),   # disciplined
    "a2": (23.0, 40, 6.6, 0.4),   # irregular: the demo story
    "a3": (22.5, 12, 7.5, 0.85),
    "a4": (22.5, 18, 7.0, 0.95),
}


class Lighting(BaseModel):
    mode: LightingMode
    cct_k: int
    since: dt.datetime


class LightingRequest(BaseModel):
    mode: LightingMode


class Night(BaseModel):
    night_of: dt.date
    bedtime: dt.datetime
    wake_time: dt.datetime
    sleep_h: float
    pre_sleep_lighting_min: int
    bright_light_last_hour: bool


class CircadianSummary(BaseModel):
    status: Literal["nominal", "watch"]
    nights: int
    bedtime_spread_min: int
    nights_bright_before_sleep: int


class Recommendation(BaseModel):
    text: str
    source: str
    source_url: str


class SharingRequest(BaseModel):
    share_with_ground: bool


class Circadian(BaseModel):
    astronaut_id: str
    share_with_ground: bool  # astronaut's choice; False by default
    lighting: Lighting
    nights: list[Night]
    summary: CircadianSummary
    card: Optional[str]  # Self-check message; null when nothing stands out
    recommendation: Recommendation
    evidence: Recommendation


def _utc_midnight(day: dt.date) -> dt.datetime:
    return dt.datetime.combine(day, dt.time(0), tzinfo=dt.timezone.utc)


def _build_log(aid: str, today: dt.date) -> list[Night]:
    bed_hour, jitter_min, sleep_h, p_pre_sleep = HABITS[aid]
    rng = random.Random(f"circadian-{aid}")  # same history on every restart
    nights = []
    for back in range(NIGHTS, 0, -1):
        day = today - dt.timedelta(days=back)
        late_min = rng.gauss(0, jitter_min)
        bedtime = _utc_midnight(day) + dt.timedelta(hours=bed_hour, minutes=late_min)
        # Late nights cost sleep: a fixed wake-up schedule doesn't move.
        hours = rng.gauss(sleep_h, 0.35) - max(0.0, late_min) / 60 * 0.5
        hours = round(min(9.0, max(4.0, hours)), 1)
        used = rng.random() < p_pre_sleep
        pre_min = max(0, round(rng.gauss(PRE_SLEEP_TARGET_MIN, 10))) if used else round(rng.uniform(0, 15))
        nights.append(Night(
            night_of=day, bedtime=bedtime.replace(second=0, microsecond=0),
            wake_time=(bedtime + dt.timedelta(hours=hours)).replace(second=0, microsecond=0),
            sleep_h=hours, pre_sleep_lighting_min=pre_min,
            bright_light_last_hour=pre_min < PRE_SLEEP_MIN_OK))
    return nights


_today = dt.datetime.now(dt.timezone.utc).date()
LOG: dict[str, list[Night]] = {aid: _build_log(aid, _today) for aid in HABITS}
_override: dict[str, Lighting] = {}  # set when the crew switches the SSLA mode
_shared: dict[str, bool] = {aid: False for aid in HABITS}  # private by default


def is_shared(aid: str) -> bool:
    return _shared[aid]


def set_shared(aid: str, share: bool) -> None:
    _shared[aid] = share


def last_sleep_h(aid: str) -> float:
    return LOG[aid][-1].sleep_h


def _tonight_bedtime(aid: str, now: dt.datetime) -> dt.datetime:
    return _utc_midnight(now.date()) + dt.timedelta(hours=HABITS[aid][0])


def current_lighting(aid: str, now: dt.datetime) -> Lighting:
    if aid in _override:
        return _override[aid]
    bed_hour, _, _, p_pre_sleep = HABITS[aid]
    last_wake = LOG[aid][-1].wake_time
    tonight = _tonight_bedtime(aid, now)
    if now < last_wake:
        mode, since = "off", LOG[aid][-1].bedtime
    elif now >= tonight:
        mode, since = "off", tonight
    elif now >= tonight - dt.timedelta(minutes=PRE_SLEEP_TARGET_MIN) and p_pre_sleep >= 0.5:
        mode, since = "pre_sleep", tonight - dt.timedelta(minutes=PRE_SLEEP_TARGET_MIN)
    else:
        mode, since = "general", last_wake
    return Lighting(mode=mode, cct_k=CCT_K[mode], since=since)


def set_lighting(aid: str, mode: str, now: dt.datetime) -> Lighting:
    _override[aid] = Lighting(mode=mode, cct_k=CCT_K[mode], since=now.replace(microsecond=0))
    return _override[aid]


def _bedtime_spread_min(nights: list[Night]) -> int:
    # Minutes after 18:00 UTC, so bedtimes either side of midnight compare correctly.
    mins = [((n.bedtime.hour - 18) % 24) * 60 + n.bedtime.minute for n in nights]
    return max(mins) - min(mins)


def assess(aid: str, now: dt.datetime) -> Circadian:
    nights = LOG[aid]
    spread = _bedtime_spread_min(nights)
    bright = sum(n.bright_light_last_hour for n in nights)
    irregular = spread > BEDTIME_SPREAD_WATCH_MIN
    too_bright = bright >= NIGHTS_BRIGHT_WATCH
    lighting = current_lighting(aid, now)

    card = None
    if irregular or too_bright:
        parts = []
        if irregular:
            parts.append(f"Your bedtime varied by about {spread / 60:.1f} h over the last {len(nights)} nights.")
        if too_bright:
            parts.append(f"On {bright} of {len(nights)} nights your quarters were still in bright light "
                         f"shortly before sleep.")
        parts.append("Irregular sleep timing and blue-rich light before bed may shift your body clock, "
                     "and body-clock disruption has been linked to changes in immune function.")
        card = " ".join(parts)

    tonight = _tonight_bedtime(aid, now)
    minutes_to_bed = (tonight - now).total_seconds() / 60
    if lighting.mode in ("general", "phase_shift") and 0 < minutes_to_bed <= 120:
        text = (f"Your usual bedtime is in about {round(minutes_to_bed)} min. You might consider switching "
                f"your quarters to pre-sleep lighting and setting screens aside.")
    else:
        text = ("You might consider switching your quarters to pre-sleep lighting about 1 h before bed "
                "and setting screens aside.")
    if irregular:
        text += " A similar bedtime each night, within about 30 min, may also help."

    return Circadian(
        astronaut_id=aid, share_with_ground=is_shared(aid), lighting=lighting, nights=nights,
        summary=CircadianSummary(
            status="watch" if card else "nominal", nights=len(nights),
            bedtime_spread_min=spread, nights_bright_before_sleep=bright),
        card=card,
        recommendation=Recommendation(text=text, source=SSLA_SOURCE, source_url=SSLA_URL),
        evidence=Recommendation(
            text="Circadian disruption is associated with immune changes; most evidence is from animal studies.",
            source=IMMUNE_SOURCE, source_url=IMMUNE_URL))
