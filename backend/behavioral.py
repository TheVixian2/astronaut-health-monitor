"""Behavioral health: a wellbeing profile per astronaut and a crew view (PROVISIONAL).

The team's focus since 2026-11-14. It addresses two NASA HRP risks: "Adverse Cognitive or
Behavioral Conditions and Psychiatric Disorders", and "Inadequate Cooperation, Coordination,
Communication and Psychosocial Adaptation within a Team".

Signals, each against the astronaut's OWN baseline (mission days 7-14), except PHQ-2, which
uses its validated screening cut-off (score >= 3; Kroenke, Spitzer & Williams, Med Care 2003):
  - PHQ-2: two questions in the check-in
  - mood: check-in, 1-5
  - sleep and body clock: the on-board lighting log (circadian.py)
  - reaction time: NASA's 3-minute Reaction Self Test (PVT-B); a lapse is a response slower
    than 355 ms (Basner et al. 2011)
  - resting heart rate: strain also shows in the body

Astronaut first (team decision 2026-11-14):
  - The astronaut sees their profile first and chooses whether the commander and/or ground
    see it.
  - Only at "urgent" are the commander and Mission Control notified automatically, and the
    astronaut is told. Even then they get the level and the areas affected, never the answers.
  - Crew view: strain that hits most of the crew (schedule, CO2, blackout) is told apart from
    strain that is personal. Crew-wide trends never name anyone and need >= 3 people.
Decision support only, never a diagnosis. Thresholds are PLACEHOLDERS.
"""

from dataclasses import dataclass
from statistics import fmean
from typing import Literal, Optional

from pydantic import BaseModel, Field

Level =Literal["steady", "watch", "concern", "urgent"]
LEVELS: list[tuple[int, Level]] = [(75, "urgent"), (50, "concern"), (25, "watch"), (0, "steady")]
PHQ2_POSITIVE = 3          # validated screening cut-off
PHQ2_HIGH = 5              # near the top of the 0-6 scale: weighs more (placeholder)
MOOD_DROP, MOOD_DROP_STRONG = 0.75, 1.5
SLEEP_SHORT_H = 1.0        # 7-night average this far below the astronaut's usual
RT_SLOWER = 0.15           # mean reaction time 15% slower than baseline
LAPSES_MORE = 3            # lapses above the astronaut's usual
HR_UP = 0.08
CREW_WIDE_MIN = 3          # a trend is "crew-wide" (and shown without names) only with >= 3 people

PHQ2_QUESTIONS = {
    "stem": "Over the last 2 weeks, how often have you been bothered by the following problems?",
    "items": [{"key": "little_interest", "text": "Little interest or pleasure in doing things"},
              {"key": "feeling_down", "text": "Feeling down, depressed, or hopeless"}],
    "options": [{"value": 0, "label": "Not at all"}, {"value": 1, "label": "Several days"},
                {"value": 2, "label": "More than half the days"}, {"value": 3, "label": "Nearly every day"}],
    "source": "PHQ-2 (Kroenke, Spitzer & Williams, Medical Care 2003). Screening only, not a diagnosis.",
}
REACTION_TEST = {
    "name": "Reaction Self Test (3-minute PVT-B)",
    "how": "Tap as soon as the counter appears; random waits of 1-4 s for 3 minutes.",
    "lapse_ms": 355,
    "source": "NASA's ISS Reaction Self Test; PVT-B lapse threshold 355 ms (Basner et al. 2011).",
}
SOURCES = [
    "NASA HRP risks: https://www.nasa.gov/hrp/risks",
    "PHQ-2: Kroenke K, Spitzer RL, Williams JB. Medical Care 2003;41(11):1284-92.",
    "PVT-B: Basner M et al. Sleep 2011 (3-min PVT, 355 ms lapse) https://pmc.ncbi.nlm.nih.gov/articles/PMC3197786",
]


class Phq2(BaseModel):
    little_interest: int = Field(ge=0, le=3)
    feeling_down: int = Field(ge=0, le=3)


class ReactionTest(BaseModel):
    mean_rt_ms: float = Field(gt=0, le=5000)
    lapses: int = Field(ge=0)
    false_starts: int = Field(default=0, ge=0)
    duration_s: int = Field(default=180, gt=0)


class Signal(BaseModel):
    name: str        # phq2 | mood | sleep | body_clock | reaction_time | resting_heart_rate
    area: str        # plain-language area shown to the commander/ground if notified
    value: Optional[str]
    baseline: Optional[str]
    points: float
    detail: str
    crew_wide: bool = False


class Phq2Result(BaseModel):
    score: int
    screen_positive: bool
    taken_at: str


class SharingState(BaseModel):
    commander: bool
    ground: bool
    auto_notified: bool  # urgent level reached: commander and ground were told automatically
    note: str


class Wellbeing(BaseModel):
    astronaut_id: str
    view: Literal["self", "commander", "ground"]
    mission_day: int
    level: Level
    score: int
    signals: list[Signal]
    phq2: Optional[Phq2Result]
    personal_or_shared: str
    suggestions: list[str]
    sharing: SharingState
    note: str
    sources: list[str]


class SharingRequest(BaseModel):
    commander: Optional[bool] = None
    ground: Optional[bool] = None


@dataclass
class Inputs:
    phq2: Optional[tuple[int, str]]          # (score, taken_at) of the latest PHQ-2
    mood_7d: Optional[float]
    mood_baseline: Optional[float]
    sleep_avg_7n: Optional[float]
    sleep_baseline: Optional[float]
    body_clock_status: Optional[str]         # circadian summary status
    rt_latest: Optional[tuple[float, int]]   # (mean ms, lapses)
    rt_baseline: Optional[tuple[float, float]]
    hr_7d: Optional[float]
    hr_baseline: Optional[float]


def level_for(score: float) -> Level:
    return next(name for floor, name in LEVELS if score >= floor)


def level_from(signals: list["Signal"], score: float, phq2_score: Optional[int]) -> Level:
    """Score bands, plus one explicit safety rule: a very high PHQ-2 (5-6) together with at
    least one other raised sign is always urgent, however the other points add up."""
    others = [s for s in signals if s.points > 0 and s.name != "phq2"]
    if phq2_score is not None and phq2_score >= PHQ2_HIGH and others:
        return "urgent"
    return level_for(score)


def signals_for(i: Inputs) -> list[Signal]:
    out = []
    if i.phq2:
        score, ts = i.phq2
        pts = (50.0 if score >= PHQ2_HIGH else 35.0 if score >= PHQ2_POSITIVE
               else 10.0 if score >= 1 else 0.0)
        out.append(Signal(name="phq2", area="questionnaire", value=f"{score}/6", baseline=f"screening cut-off {PHQ2_POSITIVE}",
                          points=pts, detail=(f"PHQ-2 score {score} on {ts[:10]}"
                                              + (" (at or above the screening cut-off)." if score >= PHQ2_POSITIVE else "."))))
    if i.mood_7d is not None and i.mood_baseline is not None:
        drop = i.mood_baseline - i.mood_7d
        pts = 20.0 if drop >= MOOD_DROP_STRONG else 10.0 if drop >= MOOD_DROP else 0.0
        out.append(Signal(name="mood", area="mood", value=f"{i.mood_7d:.1f}/5", baseline=f"{i.mood_baseline:.1f}/5",
                          points=pts, detail=f"Mood over the last 7 days averaged {i.mood_7d:.1f}, "
                                             f"vs your usual {i.mood_baseline:.1f}."))
    if i.sleep_avg_7n is not None and i.sleep_baseline is not None:
        short = i.sleep_baseline - i.sleep_avg_7n
        out.append(Signal(name="sleep", area="sleep", value=f"{i.sleep_avg_7n:.1f} h", baseline=f"{i.sleep_baseline:.1f} h",
                          points=15.0 if short >= SLEEP_SHORT_H else 0.0,
                          detail=f"Sleep averaged {i.sleep_avg_7n:.1f} h over 7 nights, vs your usual {i.sleep_baseline:.1f} h."))
    if i.body_clock_status:
        out.append(Signal(name="body_clock", area="sleep", value=i.body_clock_status, baseline=None,
                          points=10.0 if i.body_clock_status == "watch" else 0.0,
                          detail="Bedtimes have been irregular or drifting." if i.body_clock_status == "watch"
                          else "Body clock looks steady."))
    if i.rt_latest and i.rt_baseline:
        (rt, lapses), (brt, blapses) = i.rt_latest, i.rt_baseline
        slower = (rt - brt) / brt if brt else 0.0
        hit = slower >= RT_SLOWER or lapses - blapses >= LAPSES_MORE
        out.append(Signal(name="reaction_time", area="alertness", value=f"{rt:.0f} ms, {lapses} lapses",
                          baseline=f"{brt:.0f} ms, {blapses:.0f} lapses", points=15.0 if hit else 0.0,
                          detail=f"Latest reaction test {rt:.0f} ms ({100 * slower:+.0f}% vs your usual) "
                                 f"with {lapses} lapses."))
    if i.hr_7d is not None and i.hr_baseline:
        up = (i.hr_7d - i.hr_baseline) / i.hr_baseline
        out.append(Signal(name="resting_heart_rate", area="body", value=f"{i.hr_7d:.0f} bpm", baseline=f"{i.hr_baseline:.0f} bpm",
                          points=5.0 if up >= HR_UP else 0.0,
                          detail=f"Average heart rate over 7 days {i.hr_7d:.0f} bpm vs your usual {i.hr_baseline:.0f}."))
    return out


def crew_wide_names(all_signals: dict[str, list[Signal]]) -> set[str]:
    """Signals raised for at least CREW_WIDE_MIN astronauts: likely a shared cause."""
    counts: dict[str, int] = {}
    for sigs in all_signals.values():
        for name in {s.name for s in sigs if s.points > 0}:
            counts[name] = counts.get(name, 0) + 1
    return {name for name, n in counts.items() if n >= CREW_WIDE_MIN}


def suggestions_for(level: Level, signals: list[Signal]) -> list[str]:
    active = {s.name for s in signals if s.points > 0}
    out = []
    if level == "steady":
        return ["Things look steady. Keep your check-ins going so changes are easy to spot."]
    if active & {"sleep", "body_clock"}:
        out.append("You might consider the station's pre-sleep lighting about 1 h before bed (see your sleep plan).")
    if active & {"mood", "phq2"}:
        out.append("A private conference with Mission Control or psychologist is confidential and always an option.")
        out.append("Talking with a crewmate you trust, or a message or call home, can help.")
    if "reaction_time" in active:
        out.append("Slower reactions can come from tiredness; consider protecting sleep before demanding tasks.")
    out.append("Regular exercise is linked to better mood; your daily session counts.")
    if any(s.crew_wide for s in signals if s.points > 0):
        out.insert(0, "Part of this is shared by most of the crew, so it may be the schedule or environment, not you.")
    return out


def personal_or_shared(signals: list[Signal]) -> str:
    raised = [s for s in signals if s.points > 0]
    if not raised:
        return "Nothing stands out."
    shared = [s.area for s in raised if s.crew_wide]
    personal = [s.area for s in raised if not s.crew_wide]
    parts = []
    if shared:
        parts.append(f"Shared with most of the crew: {', '.join(sorted(set(shared)))} (likely schedule or environment).")
    if personal:
        parts.append(f"Personal to you: {', '.join(sorted(set(personal)))}.")
    return " ".join(parts)


def areas(signals: list[Signal]) -> list[str]:
    return sorted({s.area for s in signals if s.points > 0})


def mood_values(checkins: list[tuple[str, dict]]) -> list[float]:
    return [p["mood_1to5"] for _, p in checkins if p.get("mood_1to5") is not None]


def latest_phq2(checkins: list[tuple[str, dict]]) -> Optional[tuple[int, str]]:
    for ts, p in reversed(checkins):
        if p.get("phq2"):
            return int(p["phq2"]["little_interest"]) + int(p["phq2"]["feeling_down"]), ts
    return None


def latest_rt(checkins: list[tuple[str, dict]]) -> Optional[tuple[float, int]]:
    for _, p in reversed(checkins):
        if p.get("reaction_test"):
            return float(p["reaction_test"]["mean_rt_ms"]), int(p["reaction_test"]["lapses"])
    return None


def rt_baseline(checkins: list[tuple[str, dict]]) -> Optional[tuple[float, float]]:
    tests = [p["reaction_test"] for _, p in checkins if p.get("reaction_test")]
    if not tests:
        return None
    return fmean(t["mean_rt_ms"] for t in tests), fmean(t["lapses"] for t in tests)
