"""Condition engine: each astronaut against their OWN baseline, never a population threshold.

This module answers "does a profile match right now?" and
writes the explanation shown when Claude isn't available. The NEW-match gate
(fire once, then wait for it to clear) lives in main.py.

All thresholds are PLACEHOLDERS pending tuning (docs/api-spec.md, condition profiles).
"""

from dataclasses import dataclass
from typing import Optional

# Crew and their configured baselines. Used only until stored mission-day 7-14 data
# exists (tools/simulate_crew.py --seed-baseline); after that the baseline is a SELECT.
CREW = {
    "a1": ("Cmdr. Elena Ionescu", "Commander",
           dict(heart_rate_bpm=58, spo2_pct=98,
                temp_c=36.5, resp_rate_bpm=12, sleep_h_last_night=7.2, mood_1to5=4, hrv_sdnn_ms=55, active_min=45)),
    "a2": ("Mihai Popa", "Flight Engineer",
           dict(heart_rate_bpm=74, spo2_pct=97,
                temp_c=36.8, resp_rate_bpm=15, sleep_h_last_night=6.8, mood_1to5=4, hrv_sdnn_ms=42, active_min=40)),
    "a3": ("Dr. Sara Okafor", "Crew Medical Officer",
           dict(heart_rate_bpm=66, spo2_pct=98,
                temp_c=36.6, resp_rate_bpm=13, sleep_h_last_night=7.5, mood_1to5=5, hrv_sdnn_ms=50, active_min=50)),
    "a4": ("Jonas Berg", "Mission Specialist",
           dict(heart_rate_bpm=62, spo2_pct=98,
                temp_c=36.4, resp_rate_bpm=14, sleep_h_last_night=7.0, mood_1to5=4, hrv_sdnn_ms=47, active_min=35)),
}

# --- Thresholds (placeholders) -----------------------------------------------
SLEEP_DEBT_H, SLEEP_DEBT_NIGHTS, SLEEP_DEBT_MOOD, SLEEP_DEBT_HR_UP = 6.0, 3, 2, 0.05
CLEAR_AFTER_TICKS = 5       # consecutive non-matching ticks before a vitals alert clears

PROFILES = {
    "sleep_debt": dict(severity="watch", hazard="isolation", body_region="head", act_within_s=86400,
                       onboard_action="Consider pre-sleep lighting (2700K) 1 h before bed, screens aside, eye mask."),
}
VITALS_PROFILES = ("sleep_debt",)

# Psychological alerts come from the profile (behavioral.py), not from one tick's vitals.
# They go to the commander first (the deputy if the commander is flagged), who releases them
# to the astronaut; Mission Control always gets them after the light delay (team decision,
# Luca 2026-11-14). act_within_s drives the usual verdict rule.
PROFILES["wellbeing_concern"] = dict(
    severity="alert", hazard="isolation", body_region="head", act_within_s=86400,
    onboard_action="Check in with them privately today, and offer a private conference with Mission Control.")
PROFILES["wellbeing_urgent"] = dict(
    severity="critical", hazard="isolation", body_region="head", act_within_s=1800,
    onboard_action="Talk with them in person now, and don't leave them alone if they seem at risk. "
                   "Tell the Crew Medical Officer and Mission Control.")
PSYCHOLOGICAL = {"sleep_debt", "wellbeing_concern", "wellbeing_urgent"}
CREW_MESSAGE = {  # what the astronaut sees once a psychological alert is released to them
    "sleep_debt": "Your sleep has been short for a few nights. Your sleep plan has a few ideas that may help.",
    "wellbeing_concern": "Your recent wellbeing checks show some changes from your usual. Your commander would "
                         "like to talk, and a private conference with Mission Control is always an option.",
    "wellbeing_urgent": "Several of your recent checks have changed a lot. You don't have to handle this alone: "
                        "your commander and Mission Control know, and someone will be with you.",
}

# Sensors aren't right 100% of the time, so a vitals alert asks whether the astronaut
# actually feels it. "No" marks the readings as a likely sensor error in their history.
CONFIRM_QUESTIONS = {
    "sleep_debt": "Do you feel more tired than usual?",
}

# Suggested on-board steps for when help from Earth is late or unreachable.
# PLACEHOLDERS for the demo: check against the onboard medical checklist. Not medical advice.
PROTOCOLS = {
    "sleep_debt": [
        "Consider pre-sleep lighting (2700K) about 1 hour before bed, and screens aside.",
        "Use the eye mask and earplugs.",
        "A private conference with Mission Control is always an option, even if it's delayed.",
    ],
}

# What POST /debug/scenario does to the simulation: vitals drift toward
# baseline x MULT, so they move together coherently.
SCENARIO_MULT = {
    "sleep_debt": {"heart_rate_bpm": 1.08},
}
SCENARIO_SLEEP_NIGHTS_H = [5.4, 5.1, 5.0]
SCENARIO_SLEEP_MOOD = 2

# The demo story: a2 declines slowly after the mission midpoint (problems tended to emerge after
# the midpoint in HI-SEAS; Frontiers 2022). Used by the live simulation and by the seed, so they
# agree. Watch signals only; the check-in side of the story is in tools/simulate_crew.py and the
# time-with-crew side in location.py. Multipliers on the astronaut's own baseline.
DECLINE_FROM_DAY = 22


def drift(aid: str, mission_day: int) -> dict[str, float]:
    if aid != "a2" or mission_day < DECLINE_FROM_DAY:
        return {}
    ramp = min(1.0, (mission_day - DECLINE_FROM_DAY + 1) / 14)  # builds up over two weeks
    return {"hrv_sdnn_ms": 1 - 0.12 * ramp, "active_min": 1 - 0.2 * ramp}


@dataclass
class Context:
    sleep_last_nights: list[float]  # most recent last
    mood: int


def pct(value: float, base: float) -> float:
    return (value - base) / base if base else 0.0


def matches(profile: str, v: dict, b: dict, ctx: Context) -> bool:
    hr_up = pct(v["heart_rate_bpm"], b["heart_rate_bpm"])
    if profile == "sleep_debt":
        last = ctx.sleep_last_nights[-SLEEP_DEBT_NIGHTS:]
        return (len(last) == SLEEP_DEBT_NIGHTS and all(h < SLEEP_DEBT_H for h in last)
                and ctx.mood <= SLEEP_DEBT_MOOD and hr_up > SLEEP_DEBT_HR_UP)
    return False


# --- Verdict and fallback explanation -------------------------------------------

def acts_on_board(act_within_s: int, real_one_way_delay_s: int) -> bool:
    """docs/api-spec.md verdict rule: always the REAL light time, never the demo value."""
    return 2 * real_one_way_delay_s > act_within_s


def _mins(seconds: float) -> str:
    m = seconds / 60
    return f"{m:.0f}" if m >= 1 else "<1"


def _signed(x: float) -> str:
    return f"{x:+.0f}%"


def fallback_insight(profile: str, v: dict, b: dict, ctx: Context, real_one_way_delay_s: int,
                     blackout_left_s: Optional[float] = None) -> dict:
    """The explanation shown when Claude isn't available, built from the real numbers.

    blackout_left_s: None = Earth reachable; a number = communications blackout, with
    that many seconds left (0 = end unknown).
    """
    act_within = PROFILES[profile]["act_within_s"]
    if blackout_left_s is not None:
        until = (f"for about {blackout_left_s / 86400:.0f} more days" if blackout_left_s >= 86400
                 else f"for about {_mins(blackout_left_s)} more min" if blackout_left_s > 0 else "for now")
        verdict = (f"Earth is out of contact {until} (communications blackout). Follow the on-board steps and "
                   f"tell a crewmate or the Crew Medical Officer. This is saved and will be sent to Mission Control "
                   f"as soon as contact returns.")
    elif acts_on_board(act_within, real_one_way_delay_s):
        verdict = (f"Ground will see this in about {_mins(real_one_way_delay_s)} min, and a reply takes about "
                   f"{_mins(2 * real_one_way_delay_s)} min. That is longer than this can safely wait, so the "
                   f"on-board step comes first.")
    else:
        verdict = (f"This can wait for Mission Control: they will see it in about "
                   f"{_mins(real_one_way_delay_s)} min.")
    hr, bhr = v["heart_rate_bpm"], b["heart_rate_bpm"]

    if profile == "sleep_debt":
        nights = ", ".join(f"{h:.1f}" for h in ctx.sleep_last_nights[-SLEEP_DEBT_NIGHTS:])
        return dict(
            why="Several short nights, a lower mood and a raised resting heart rate together may point to "
                "building sleep debt and strain.",
            trend=f"Last {SLEEP_DEBT_NIGHTS} nights: {nights} h vs your usual {b['sleep_h_last_night']:.1f} h; "
                  f"mood {ctx.mood}/5; heart rate {_signed(100 * pct(hr, bhr))}.",
            recommended_action="You might consider protecting tonight's sleep with the station's pre-sleep "
                               "lighting (2700K) about 1 h before bed. A private conference with Mission "
                               "Control is always an option. " + verdict)
    raise ValueError(profile)
