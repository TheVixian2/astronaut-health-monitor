# Written with AI assistance (Claude Code, Anthropic) and reviewed by the team. See README "Use of AI".
"""Psychological profile: every input, weighted, against each astronaut's own normal (PROVISIONAL).

Focus of the project since 2026-11-14. Addresses two NASA HRP risks: "Adverse Cognitive or
Behavioral Conditions and Psychiatric Disorders", and "Inadequate Cooperation, Coordination,
Communication and Psychosocial Adaptation within a Team".

How the score works (all constants below, one place to tune):
  1. Personal baseline per input: mean and spread (SD) over mission days 7-14.
  2. Recent value: last 7 complete days (daily inputs), last 7 days of check-ins (mood),
     14 days for PHQ (its recall window), the latest reaction test.
  3. z = how many SDs the recent value is from the baseline, in the worrying direction.
     severity = 0 at z <= 0.5, rising to 1 at z >= 2.
  4. score = sum(weight x severity), 0-100. Watch and station inputs carry 70, check-ins 30
     (team decision, Luca 2026-11-14: "a design choice, not a published value").
  5. Safety rules on top of the score (PHQ, validated screen): see level_from().
  6. Inputs with too little data are left out and their weight is shared within the group;
     confidence says how much of the weight had data.

Accuracy notes:
  - PHQ-2 >= 3: sensitivity 0.72, specificity 0.85; PHQ-2 >= 2 then PHQ-9 >= 10 is more
    specific (Levis et al., JAMA 2020, IPD meta-analysis, n = 44,318). So PHQ-2 >= 2 asks for
    the PHQ-9 next. Neither can confirm a diagnosis (Mitchell et al., BJPsych Open 2016).
  - Passive signals are compared within-person, as in the studies they come from (time at home
    relative to one's own average: Stamatis et al., npj Ment Health Res 2024).
  - More contact is not automatically better (Cantisani et al., PNAS 2026), so only a CHANGE
    from the astronaut's own normal counts, never "too little" in absolute terms.
  - Readings flagged as sensor errors are excluded upstream (quality = 'ok' only).
Decision support only, never a diagnosis. Weights and bands are PLACEHOLDERS, calibrated with
tools/check_profile.py on simulated crews, not on real astronauts.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from statistics import fmean, linear_regression, stdev
from typing import Annotated, Literal, Optional

from pydantic import BaseModel, Field

Level = Literal["steady", "watch", "concern", "urgent"]
LEVEL_RANK = {"steady": 0, "watch": 1, "concern": 2, "urgent": 3}
BANDS: list[tuple[float, Level]] = [(60, "urgent"), (40, "concern"), (20, "watch"), (0, "steady")]

GROUP_WEIGHT = {"watch": 70.0, "checkin": 30.0}

# name: (group, weight within the 100, direction, SD floor, unit, label, evidence)
INPUTS = {
    "sleep": ("watch", 15, "down", 0.3, "h", "Sleep",
              "Sleep loss is linked to mood; ISS crews average ~6 h (Barger et al., Lancet Neurol 2014)."),
    "hrv": ("watch", 12, "down", 3.0, "ms", "Heart-rate variability (night)",
            "Lower HRV is associated with depression (Kemp et al., Biol Psychiatry 2010, meta-analysis)."),
    "social_time": ("watch", 12, "down", 0.5, "h/day", "Time with crewmates",
                    "More time at home than one's own average predicted depression 2 weeks ahead "
                    "(Stamatis et al. 2024, n=1,013); proximity tracked crew cohesion in Mars-500 "
                    "(Johannes et al., PLoS ONE 2015) and Antarctic winter-overs (Basner et al. 2026)."),
    "activity": ("watch", 11, "down", 5.0, "min/day", "Activity",
                 "Crews grew more sedentary over Mars-500 (Basner et al., PNAS 2013); lower step counts "
                 "relative to one's own level went with higher depression (Wallace et al. 2024)."),
    "body_clock": ("watch", 10, "up", 0.0, "", "Body-clock regularity",
                   "More variable wake-up times went with higher depression scores (Wallace et al. 2024)."),
    "resting_heart_rate": ("watch", 10, "up", 2.0, "bpm", "Resting heart rate (night)",
                           "Supporting signal only: stress raises resting heart rate."),
    "phq": ("checkin", 15, "up", 0.0, "", "PHQ-2 / PHQ-9 questionnaire",
            "Validated depression screen (Kroenke et al. 2003; Levis et al., JAMA 2020)."),
    "mood": ("checkin", 8, "down", 0.5, "/5", "Mood", "Self-report, 1-5."),
    "reaction_time": ("checkin", 7, "up", 10.0, "ms", "Reaction test",
                      "NASA's 3-min Reaction Self Test (PVT-B, 355 ms lapse; Basner et al. 2011). "
                      "Tracks fatigue and alertness, not mood itself."),
}
# Spread floor relative to the astronaut's own level. Eight baseline days can give a spread that is
# too small by chance, and then an ordinary week looks like a big change. Night-to-night HRV
# fluctuation is normal and measurable (Grosicki et al., Am J Physiol Heart 2025, >21,000 wearable
# users), and daily activity varies even more. PLACEHOLDERS, tuned with tools/check_profile.py.
REL_FLOOR = {"hrv": 0.10, "activity": 0.20, "social_time": 0.10, "reaction_time": 0.05}

# Optional check-in tags: a known reason why some inputs may change for a few days. Those days
# are left out of those inputs (baseline, last 7 days and trend), so the score doesn't read them
# as a change in wellbeing. Mood and the PHQ are never left out and the safety rules always
# apply, so a tag can't hide a warning. Which tag was chosen is never shown to anyone else:
# others only see "left out, marked in a check-in". Day windows are relative to the check-in
# day. PLACEHOLDERS (windows and inputs), except where a source is named.
ContextTag = Literal["ill", "new_medication", "period"]
CONTEXT_TAGS: dict[str, dict] = {
    "ill": dict(
        label="I'm feeling ill or injured", days=(-1, 2),
        inputs=("sleep", "hrv", "resting_heart_rate", "activity", "social_time", "reaction_time"),
        why="Being ill changes heart rate, HRV, sleep and activity, and keeps people in their quarters."),
    "new_medication": dict(
        label="I started a new medication", days=(0, 6),
        inputs=("sleep", "hrv", "resting_heart_rate", "reaction_time"),
        why="Sleep medication is common in spaceflight (71-78% of crew members in low-Earth orbit; "
            "Albornoz-Miranda et al., Sleep Med X 2023), and some medicines lower HRV (Kemp et al. 2010)."),
    "period": dict(
        label="My period started", days=(-5, 2),
        inputs=("hrv", "resting_heart_rate"),   # resting HR: placeholder, it tends to move with HRV
        why="HRV is lower late in the menstrual cycle, by about 3-9% (de Jager et al., Sports Med 2026)."),
}

AREA = {"sleep": "sleep", "hrv": "body", "social_time": "time with crew", "activity": "activity",
        "body_clock": "sleep", "resting_heart_rate": "body", "phq": "questionnaire", "mood": "mood",
        "reaction_time": "alertness"}

MIN_DAYS = 4                 # of 7, for a daily input to count; also for the baseline
MIN_CHECKINS = 3             # check-ins in days 7-14 needed for a mood / reaction-test baseline
PHQ_WINDOW_DAYS = 14         # PHQ asks about "the last 2 weeks"
PHQ2_ASK_PHQ9 = 2            # two-step screening (Levis 2020)
PHQ2_POSITIVE, PHQ2_HIGH = 3, 5
PHQ9_POSITIVE, PHQ9_SEVERE = 10, 20
CREW_WIDE_MIN = 3            # a trend is "crew-wide" (shown without names) only with >= 3 people
TREND_DAYS = 14

PHQ2_QUESTIONS = {
    "stem": "Over the last 2 weeks, how often have you been bothered by the following problems?",
    "items": [{"key": "little_interest", "text": "Little interest or pleasure in doing things"},
              {"key": "feeling_down", "text": "Feeling down, depressed, or hopeless"}],
    "options": [{"value": 0, "label": "Not at all"}, {"value": 1, "label": "Several days"},
                {"value": 2, "label": "More than half the days"}, {"value": 3, "label": "Nearly every day"}],
    "source": "PHQ-2 (Kroenke, Spitzer & Williams, Medical Care 2003). Screening only, not a diagnosis.",
}
PHQ9_QUESTIONS = {
    "stem": PHQ2_QUESTIONS["stem"],
    "items": [
        "Little interest or pleasure in doing things",
        "Feeling down, depressed, or hopeless",
        "Trouble falling or staying asleep, or sleeping too much",
        "Feeling tired or having little energy",
        "Poor appetite or overeating",
        "Feeling bad about yourself, or that you are a failure or have let yourself or your family down",
        "Trouble concentrating on things, such as reading or watching a video",
        "Moving or speaking so slowly that other people could have noticed, or the opposite: being so "
        "fidgety or restless that you have been moving around a lot more than usual",
        "Thoughts that you would be better off dead, or of hurting yourself in some way",
    ],
    "options": PHQ2_QUESTIONS["options"],
    "when": "Asked when PHQ-2 is 2 or more (two-step screening, Levis et al. 2020).",
    "safety": "Any answer above 0 on the last question is treated as urgent: a person is told straight away.",
    "source": "PHQ-9 (Kroenke, Spitzer & Williams, J Gen Intern Med 2001). Free to use. Screening only.",
}
REACTION_TEST = {
    "name": "Reaction Self Test (3-minute PVT-B)",
    "how": "Tap as soon as the counter appears; random waits of 1-4 s for 3 minutes.",
    "lapse_ms": 355,
    "source": "NASA's ISS Reaction Self Test; PVT-B lapse threshold 355 ms (Basner et al. 2011).",
}
SOURCES = [
    "NASA HRP risks: https://www.nasa.gov/hrp/risks",
    "PHQ-2 accuracy: Levis B et al. JAMA 2020 (IPD meta-analysis, n=44,318) "
    "https://consensus.app/papers/details/w:157a9876-8a4a-412c-9cf2-afaf86faf638/",
    "PHQ-2: Kroenke K, Spitzer RL, Williams JB. Medical Care 2003;41(11):1284-92.",
    "Home stay and depression: Stamatis CA et al. npj Mental Health Research 2024 "
    "https://consensus.app/papers/details/w:910d0bc5-13b9-4246-a043-89e2ad1fbba6/",
    "Crew proximity in Mars-500: Johannes BW et al. PLoS ONE 2015 "
    "https://consensus.app/papers/details/w:77011ac3-e893-47f9-aac4-9969a4700723/",
    "PVT-B: Basner M et al. Sleep 2011 https://pmc.ncbi.nlm.nih.gov/articles/PMC3197786",
]


# --- Request / response models ---------------------------------------------------

class Phq2(BaseModel):
    little_interest: int = Field(ge=0, le=3)
    feeling_down: int = Field(ge=0, le=3)


class Phq9(BaseModel):
    answers: list[Annotated[int, Field(ge=0, le=3)]] = Field(min_length=9, max_length=9)  # items 1-9


class ReactionTest(BaseModel):
    mean_rt_ms: float = Field(gt=0, le=5000)
    lapses: int = Field(ge=0)
    false_starts: int = Field(default=0, ge=0)
    duration_s: int = Field(default=180, gt=0)


class Signal(BaseModel):
    name: str
    label: str
    group: Literal["watch", "checkin"]
    area: str
    weight: float                 # share of the 100 (after sharing out missing inputs' weight)
    value: Optional[str]
    baseline: Optional[str]
    z: Optional[float]            # SDs from the astronaut's own normal, worrying direction positive
    severity: float               # 0-1
    points: float                 # weight x severity: its contribution to the score
    trend: Literal["worsening", "stable", "improving", "unknown"]
    enough_data: bool
    detail: str
    evidence: str
    crew_wide: bool = False
    left_out_days: int = 0        # of the last 7 days, left out because of a check-in tag


class PhqResult(BaseModel):
    instrument: Literal["PHQ-2", "PHQ-9"]
    score: int
    max_score: int
    screen_positive: bool
    taken_at: str
    item9_positive: bool = False
    item9_at: Optional[str] = None   # set when an earlier PHQ-9 in the window had it


class DayScore(BaseModel):
    day: date
    mission_day: int
    score: int
    level: Level


class Trend(BaseModel):
    direction: Literal["worsening", "stable", "improving", "unknown"]
    points_per_week: Optional[float]
    score_7_days_ago: Optional[int]
    first_flagged: Optional[date]          # first day of the current run at watch or above
    timeline: list[DayScore]               # daily score since the baseline window ended


@dataclass
class DayData:
    """One complete mission day for one astronaut (sensor errors already excluded)."""
    rhr: Optional[float] = None
    hrv: Optional[float] = None
    active: Optional[float] = None
    sleep: Optional[float] = None
    crew_h: Optional[float] = None
    quarters_h: Optional[float] = None


@dataclass
class History:
    days: dict[date, DayData]
    checkins: list[tuple[str, dict]]       # (iso ts, payload), oldest first
    mission_start: date
    body_clock_status: Optional[str] = None  # today's circadian status, live only


@dataclass
class Result:
    score: int
    level: Level
    rule: Optional[str]
    signals: list[Signal]
    phq: Optional[PhqResult]
    needs_phq9: bool
    confidence: Literal["high", "medium", "low"]
    coverage: float
    group_points: dict[str, float] = field(default_factory=dict)


# --- Scoring ----------------------------------------------------------------------

def severity_from_z(z: Optional[float]) -> float:
    if z is None:
        return 0.0
    return max(0.0, min(1.0, (z - 0.5) / 1.5))


def _mean_sd(values: list[float], floor: float, need: int = 0, rel: float = 0.0) -> Optional[tuple[float, float]]:
    """Baseline mean and spread: the sample SD, never below `floor` or `rel` x the mean."""
    if len(values) < (need or MIN_DAYS):
        return None
    m = fmean(values)
    return m, max(stdev(values), floor, rel * abs(m))


def _z(recent: Optional[float], base: Optional[tuple[float, float]], direction: str) -> Optional[float]:
    if recent is None or base is None:
        return None
    z = (recent - base[0]) / base[1]
    return round(z if direction == "up" else -z, 2)


def _day_values(h: History, attr: str, start: date, end: date, skip: frozenset = frozenset()) -> list[float]:
    out = []
    d = start
    while d <= end:
        v = getattr(h.days.get(d, DayData()), attr)
        if v is not None and d not in skip:
            out.append(v)
        d += timedelta(days=1)
    return out


def left_out(h: History) -> dict[str, frozenset]:
    """Input name -> the days its check-in tags leave out."""
    out: dict[str, set] = {}
    for ts, p in h.checkins:
        for tag in p.get("context") or []:
            spec = CONTEXT_TAGS.get(tag)
            if spec is None:
                continue
            d0 = date.fromisoformat(ts[:10])
            lo, hi = spec["days"]
            days = {d0 + timedelta(days=i) for i in range(lo, hi + 1)}
            for name in spec["inputs"]:
                out.setdefault(name, set()).update(days)
    return {k: frozenset(v) for k, v in out.items()}


def _left_note(n: int) -> str:
    return f" {n} of the last 7 days left out (marked in a check-in)." if n else ""


def _ck_day(p: dict) -> Optional[date]:
    ts = p.get("timestamp")
    return date.fromisoformat(ts[:10]) if ts else None


def _checkins_in(h: History, start: date, end: date) -> list[dict]:
    lo, hi = start.isoformat(), (end + timedelta(days=1)).isoformat()
    return [p for ts, p in h.checkins if lo <= ts[:10] < hi]


def _baseline_window(h: History) -> tuple[date, date]:
    return h.mission_start + timedelta(days=6), h.mission_start + timedelta(days=13)


def _latest_phq(h: History, end: date) -> Optional[PhqResult]:
    """The newest PHQ in the 14-day window. A PHQ-9 with question 9 above 0 anywhere in the window
    keeps item9_positive: a later short PHQ-2 must not quietly clear a self-harm answer."""
    r = _newest_phq(h, end)
    if r is not None and not r.item9_positive:
        start = end - timedelta(days=PHQ_WINDOW_DAYS - 1)
        lo, hi = start.isoformat(), (end + timedelta(days=1)).isoformat()
        flagged = next((ts for ts, p in reversed(h.checkins)
                        if lo <= ts[:10] < hi and p.get("phq9") and p["phq9"]["answers"][8] > 0), None)
        if flagged:
            r = r.model_copy(update={"item9_positive": True, "item9_at": flagged})
    return r


def _newest_phq(h: History, end: date) -> Optional[PhqResult]:
    start = end - timedelta(days=PHQ_WINDOW_DAYS - 1)
    lo, hi = start.isoformat(), (end + timedelta(days=1)).isoformat()
    for ts, p in reversed(h.checkins):
        if not lo <= ts[:10] < hi:
            continue
        if p.get("phq9"):
            a = p["phq9"]["answers"]
            score = sum(a)
            return PhqResult(instrument="PHQ-9", score=score, max_score=27, taken_at=ts,
                             screen_positive=score >= PHQ9_POSITIVE, item9_positive=a[8] > 0)
        if p.get("phq2"):
            score = int(p["phq2"]["little_interest"]) + int(p["phq2"]["feeling_down"])
            return PhqResult(instrument="PHQ-2", score=score, max_score=6, taken_at=ts,
                             screen_positive=score >= PHQ2_POSITIVE)
    return None


def _phq_severity(r: Optional[PhqResult]) -> float:
    if r is None:
        return 0.0
    if r.instrument == "PHQ-9":
        s = r.score
        return 1.0 if s >= PHQ9_SEVERE else 0.9 if s >= 15 else 0.7 if s >= PHQ9_POSITIVE else 0.35 if s >= 5 else 0.0
    return {0: 0.0, 1: 0.2, 2: 0.4, 3: 0.75, 4: 0.75}.get(r.score, 1.0)


def _trend_of(h: History, attr: str, end: date, base: Optional[tuple[float, float]], direction: str,
              skip: frozenset = frozenset()) -> str:
    if base is None:
        return "unknown"
    now_vals = _day_values(h, attr, end - timedelta(days=6), end, skip)
    prev_vals = _day_values(h, attr, end - timedelta(days=13), end - timedelta(days=7), skip)
    if len(now_vals) < MIN_DAYS or len(prev_vals) < MIN_DAYS:
        return "unknown"
    change = (fmean(now_vals) - fmean(prev_vals)) / base[1]
    change = change if direction == "up" else -change
    return "worsening" if change >= 0.5 else "improving" if change <= -0.5 else "stable"


def _fmt(v: Optional[float], unit: str, nd: int = 1) -> Optional[str]:
    return None if v is None else f"{v:.{nd}f} {unit}".strip()


def compute(h: History, end: date, live: bool = False) -> Result:
    """The profile for the window ending on `end` (a complete day). `live` adds today's body clock."""
    b0, b1 = _baseline_window(h)
    w0 = end - timedelta(days=6)
    ck_end = end + timedelta(days=1) if live else end   # live: today's check-ins count straight away
    raw: list[dict] = []
    skips = left_out(h)
    in_week = lambda sk: sum(1 for i in range(7) if w0 + timedelta(days=i) in sk)

    def daily(name: str, attr: str, nd: int = 1, extra: str = "") -> None:
        group, weight, direction, floor, unit, label, ev = INPUTS[name]
        sk = skips.get(name, frozenset())
        n_out = in_week(sk)
        extra += _left_note(n_out)
        base = _mean_sd(_day_values(h, attr, b0, b1, sk), floor, rel=REL_FLOOR.get(name, 0.0))
        vals = _day_values(h, attr, w0, end, sk)
        recent = fmean(vals) if len(vals) >= MIN_DAYS else None
        z = _z(recent, base, direction)
        trend = _trend_of(h, attr, end, base, direction, sk)
        if recent is None or base is None:
            detail = f"Not enough {label.lower()} data yet ({len(vals)} of 7 days).{_left_note(n_out)}"
        else:
            word = ("higher" if recent > base[0] else "lower") if abs(z) >= 0.5 else "about the same as"
            detail = (f"{label}: {_fmt(recent, unit, nd)} over the last 7 days, {word} than your usual "
                      f"{_fmt(base[0], unit, nd)} (normal spread ±{base[1]:.{nd}f}).{extra}")
            if word == "about the same as":
                detail = (f"{label}: {_fmt(recent, unit, nd)} over the last 7 days, about the same as your usual "
                          f"{_fmt(base[0], unit, nd)}.{extra}")
        raw.append(dict(name=name, value=_fmt(recent, unit, nd), baseline=_fmt(base[0], unit, nd) if base else None,
                        z=z, severity=severity_from_z(z), trend=trend,
                        enough=recent is not None and base is not None, detail=detail, left_out=n_out))

    daily("sleep", "sleep")
    daily("hrv", "hrv", 0)
    daily("activity", "active", 0)
    daily("resting_heart_rate", "rhr", 0)

    # Time with crewmates: crew time down OR time alone in own quarters up, whichever is worse.
    g, w, _, floor, unit, label, ev = INPUTS["social_time"]
    sk = skips.get("social_time", frozenset())
    n_out_s = in_week(sk)
    base_c = _mean_sd(_day_values(h, "crew_h", b0, b1, sk), floor, rel=REL_FLOOR["social_time"])
    base_q = _mean_sd(_day_values(h, "quarters_h", b0, b1, sk), floor, rel=REL_FLOOR["social_time"])
    vc, vq = _day_values(h, "crew_h", w0, end, sk), _day_values(h, "quarters_h", w0, end, sk)
    rc = fmean(vc) if len(vc) >= MIN_DAYS else None
    rq = fmean(vq) if len(vq) >= MIN_DAYS else None
    zc, zq = _z(rc, base_c, "down"), _z(rq, base_q, "up")
    zs = max([z for z in (zc, zq) if z is not None], default=None)
    if zs is None:
        social_detail = f"Not enough location data yet ({len(vc)} of 7 days)."
    else:
        social_detail = (f"While awake: {rc:.1f} h a day with crewmates (usual {base_c[0]:.1f} h) and "
                         f"{rq:.1f} h alone in your quarters (usual {base_q[0]:.1f} h), last 7 days.")
    social_detail += _left_note(n_out_s)
    trend_s = _trend_of(h, "crew_h", end, base_c, "down", sk)
    raw.append(dict(name="social_time", value=_fmt(rc, unit), baseline=_fmt(base_c[0], unit) if base_c else None,
                    z=zs, severity=severity_from_z(zs), trend=trend_s, enough=zs is not None, detail=social_detail,
                    left_out=n_out_s))

    # Body clock: today's lighting-log assessment (circadian.py), live only.
    if live and h.body_clock_status is not None:
        irregular = h.body_clock_status == "watch"
        raw.append(dict(name="body_clock", value="irregular" if irregular else "steady", baseline=None,
                        z=None, severity=0.67 if irregular else 0.0, trend="unknown", enough=True,
                        detail="Bedtimes have been irregular or drifting (lighting log)." if irregular
                        else "Bedtimes look regular (lighting log)."))
    else:
        raw.append(dict(name="body_clock", value=None, baseline=None, z=None, severity=0.0, trend="unknown",
                        enough=False, detail="Body clock is only assessed for today."))

    # Check-ins: mood (7 days), reaction test (latest within 7 days), PHQ (14 days).
    base_ck = _checkins_in(h, b0, b1)
    mood_base = _mean_sd([p["mood_1to5"] for p in base_ck if p.get("mood_1to5") is not None], 0.5,
                         MIN_CHECKINS)
    moods = [p["mood_1to5"] for p in _checkins_in(h, w0, ck_end) if p.get("mood_1to5") is not None]
    recent_mood = fmean(moods) if moods else None
    zm = _z(recent_mood, mood_base, "down")
    raw.append(dict(name="mood", value=_fmt(recent_mood, "/5"), baseline=_fmt(mood_base[0], "/5") if mood_base else None,
                    z=zm, severity=severity_from_z(zm), trend="unknown", enough=zm is not None,
                    detail=(f"Mood averaged {recent_mood:.1f}/5 over the last 7 days, vs your usual "
                            f"{mood_base[0]:.1f}." if zm is not None else "Not enough mood check-ins yet.")))

    sk_rt = skips.get("reaction_time", frozenset())
    n_out_rt = in_week(sk_rt)
    rts = [p["reaction_test"] for p in base_ck if p.get("reaction_test") and _ck_day(p) not in sk_rt]
    rt_base = _mean_sd([t["mean_rt_ms"] for t in rts], INPUTS["reaction_time"][3], MIN_CHECKINS,
                       REL_FLOOR["reaction_time"])
    lapse_base = _mean_sd([t["lapses"] for t in rts], 1.0, MIN_CHECKINS)
    latest_rt = next((p["reaction_test"] for p in reversed(_checkins_in(h, w0, ck_end))
                      if p.get("reaction_test") and _ck_day(p) not in sk_rt), None)
    if latest_rt and rt_base:
        z_rt = max(_z(latest_rt["mean_rt_ms"], rt_base, "up"), _z(latest_rt["lapses"], lapse_base, "up"))
        rt_detail = (f"Latest reaction test {latest_rt['mean_rt_ms']:.0f} ms with {latest_rt['lapses']} lapses, "
                     f"vs your usual {rt_base[0]:.0f} ms and {lapse_base[0]:.1f} lapses.")
    else:
        z_rt, rt_detail = None, "No reaction test in the last 7 days."
    rt_detail += _left_note(n_out_rt)
    raw.append(dict(name="reaction_time", value=f"{latest_rt['mean_rt_ms']:.0f} ms" if latest_rt else None,
                    baseline=f"{rt_base[0]:.0f} ms" if rt_base else None, z=z_rt, severity=severity_from_z(z_rt),
                    trend="unknown", enough=z_rt is not None, detail=rt_detail, left_out=n_out_rt))

    phq = _latest_phq(h, ck_end)
    phq_detail = ("No PHQ questionnaire in the last 14 days." if phq is None else
                  f"{phq.instrument} score {phq.score}/{phq.max_score} on {phq.taken_at[:10]}"
                  + (" (at or above the screening cut-off)." if phq.screen_positive else ".")
                  + (f" The PHQ-9 on {phq.item9_at[:10]} had question 9 above 0, so this stays urgent for "
                     f"{PHQ_WINDOW_DAYS} days." if phq and phq.item9_at else ""))
    raw.append(dict(name="phq", value=f"{phq.score}/{phq.max_score}" if phq else None, baseline=None, z=None,
                    severity=_phq_severity(phq), trend="unknown", enough=phq is not None, detail=phq_detail))

    # Weights: share out the weight of inputs without enough data, within their group.
    signals, group_points = [], {"watch": 0.0, "checkin": 0.0}
    covered = 0.0
    for grp, gw in GROUP_WEIGHT.items():
        members = [r for r in raw if INPUTS[r["name"]][0] == grp]
        have = sum(INPUTS[r["name"]][1] for r in members if r["enough"])
        covered += have
        for r in members:
            _, base_w, _, _, _, label, ev = INPUTS[r["name"]]
            wgt = base_w * gw / have if r["enough"] and have else 0.0
            pts = round(wgt * r["severity"], 1)
            group_points[grp] += pts
            signals.append(Signal(name=r["name"], label=label, group=grp, area=AREA[r["name"]], weight=round(wgt, 1),
                                  value=r["value"], baseline=r["baseline"], z=r["z"],
                                  severity=round(r["severity"], 2), points=pts, trend=r["trend"],
                                  enough_data=r["enough"], detail=r["detail"], evidence=ev,
                                  left_out_days=r.get("left_out", 0)))
    if not any(INPUTS[r["name"]][0] == "watch" and r["enough"] for r in raw):
        group_points["checkin"] *= 100 / GROUP_WEIGHT["checkin"]   # only check-ins have data
    elif not any(INPUTS[r["name"]][0] == "checkin" and r["enough"] for r in raw):
        group_points["watch"] *= 100 / GROUP_WEIGHT["watch"]
    score = min(100, round(sum(group_points.values())))
    level, rule = level_from(signals, score, phq)
    coverage = covered / 100
    recent_phq = phq is not None
    confidence = "high" if coverage >= 0.8 and recent_phq else "medium" if coverage >= 0.5 else "low"
    needs_phq9 = phq is not None and phq.instrument == "PHQ-2" and phq.score >= PHQ2_ASK_PHQ9
    return Result(score=score, level=level, rule=rule, signals=signals, phq=phq, needs_phq9=needs_phq9,
                  confidence=confidence, coverage=round(coverage, 2),
                  group_points={k: round(v, 1) for k, v in group_points.items()})


def level_from(signals: list[Signal], score: float, phq: Optional[PhqResult]) -> tuple[Level, Optional[str]]:
    """Score bands, with the validated questionnaire's safety rules on top."""
    level = next(name for floor, name in BANDS if score >= floor)
    others = [s for s in signals if s.name != "phq" and s.severity >= 0.5]
    if phq is not None:
        if phq.item9_positive:
            return "urgent", "PHQ-9 question 9 answered above 0: a person should talk with them now."
        if (phq.instrument == "PHQ-9" and phq.score >= PHQ9_SEVERE) or \
                (phq.instrument == "PHQ-2" and phq.score >= PHQ2_HIGH and others):
            return "urgent", f"{phq.instrument} {phq.score} together with other warning signs."
        if phq.screen_positive and LEVEL_RANK[level] < LEVEL_RANK["concern"]:
            return "concern", f"{phq.instrument} {phq.score} is a positive screen: it calls for a follow-up."
    return level, None


def trend(h: History, today: date, current: Result) -> Trend:
    """Daily score since the baseline window, slope over the last 14 days, first day flagged."""
    _, b1 = _baseline_window(h)
    yesterday = today - timedelta(days=1)
    timeline = []
    d = b1 + timedelta(days=1)
    while d <= yesterday:
        r = compute(h, d)
        timeline.append(DayScore(day=d, mission_day=(d - h.mission_start).days + 1, score=r.score, level=r.level))
        d += timedelta(days=1)
    timeline.append(DayScore(day=today, mission_day=(today - h.mission_start).days + 1,
                             score=current.score, level=current.level))
    recent = timeline[-TREND_DAYS:]
    slope = None
    direction = "unknown"
    if len(recent) >= 7:
        slope = linear_regression(range(len(recent)), [p.score for p in recent]).slope * 7
        direction = "worsening" if slope >= 5 else "improving" if slope <= -5 else "stable"
        slope = round(slope, 1)
    week_ago = timeline[-8].score if len(timeline) >= 8 else None
    first = None
    for p in reversed(timeline):
        if LEVEL_RANK[p.level] >= LEVEL_RANK["watch"]:
            first = p.day
        else:
            break
    return Trend(direction=direction, points_per_week=slope, score_7_days_ago=week_ago,
                 first_flagged=first, timeline=timeline)


def mark_crew_wide(results: dict[str, Result]) -> dict[str, int]:
    """Mark inputs raised (severity >= 0.5) for >= 3 crew as crew-wide. PHQ is never aggregated."""
    counts: dict[str, int] = {}
    for r in results.values():
        for s in r.signals:
            if s.severity >= 0.5 and s.name != "phq":
                counts[s.name] = counts.get(s.name, 0) + 1
    for r in results.values():
        for s in r.signals:
            s.crew_wide = s.severity >= 0.5 and counts.get(s.name, 0) >= CREW_WIDE_MIN
    return counts


def suggestions_for(r: Result) -> list[str]:
    active = {s.name for s in r.signals if s.severity >= 0.5}
    out = []
    if r.level == "steady" and not r.needs_phq9:
        return ["Things look steady. Keep your check-ins going so changes are easy to spot."]
    if r.needs_phq9:
        out.append("Your last check-in suggests a few more questions (PHQ-9) would give a clearer picture.")
    if active & {"sleep", "body_clock"}:
        out.append("You might consider the station's pre-sleep lighting about 1 h before bed (see your sleep plan).")
    if "social_time" in active:
        out.append("Shared meals and evening time with the crew can help; joining the next meal in the galley is a small step.")
    if active & {"mood", "phq"}:
        out.append("A private conference with Mission Control's psychologist is confidential and always an option.")
        out.append("Talking with a crewmate you trust, or a message or call home, can help.")
    if "activity" in active:
        out.append("Regular exercise is linked to better mood; your daily session counts.")
    if "reaction_time" in active:
        out.append("Slower reactions can come from tiredness; consider protecting sleep before demanding tasks.")
    if any(s.crew_wide for s in r.signals if s.severity >= 0.5):
        out.insert(0, "Part of this is shared by most of the crew, so it may be the schedule or environment, not you.")
    return out or ["Keep your check-ins going so changes are easy to spot."]


def method() -> dict:
    """The weights and rules, as shown to anyone who asks how the score is made."""
    return {
        "score": "sum of weight x severity, 0-100; severity 0 at <= 0.5 SD from your own days 7-14, 1 at >= 2 SD",
        "groups": GROUP_WEIGHT,
        "inputs": [{"name": n, "label": v[5], "group": v[0], "weight": v[1], "direction": v[2],
                    "evidence": v[6]} for n, v in INPUTS.items()],
        "bands": {"steady": "< 20", "watch": "20-39", "concern": "40-59", "urgent": ">= 60"},
        "rules": [
            f"PHQ-2 >= {PHQ2_POSITIVE} or PHQ-9 >= {PHQ9_POSITIVE}: at least concern (positive screen, follow-up)",
            f"PHQ-2 >= {PHQ2_HIGH} with another warning sign, or PHQ-9 >= {PHQ9_SEVERE}: urgent",
            "PHQ-9 question 9 above 0: urgent, a person is told straight away",
            f"PHQ-2 >= {PHQ2_ASK_PHQ9}: ask for the PHQ-9 next (two-step screening)",
        ],
        "missing_data": f"an input needs {MIN_DAYS} of 7 days; otherwise its weight is shared within its group",
        "context_tags": [{"id": k, "label": v["label"], "days": list(v["days"]), "leaves_out": list(v["inputs"]),
                          "why": v["why"]} for k, v in CONTEXT_TAGS.items()],
        "context_note": "Optional check-in tags leave those days out of the inputs listed. Mood and the PHQ "
                        "always count and the safety rules always apply. Others never see which tag was chosen.",
        "note": "The 70/30 split is a team design choice and the weights within groups are our reading of the "
                "evidence, not published values. Calibrated on simulated crews (tools/check_profile.py).",
        "sources": SOURCES,
    }
