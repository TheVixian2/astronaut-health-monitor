"""Condition engine: each astronaut against their OWN baseline, never a population threshold.

This module answers "does a profile match right now?", scores SANS risk, and
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
           dict(heart_rate_bpm=58, systolic_mmhg=112, diastolic_mmhg=72, spo2_pct=98,
                temp_c=36.5, resp_rate_bpm=12, sleep_h_last_night=7.2, mood_1to5=4)),
    "a2": ("Mihai Popa", "Flight Engineer",
           dict(heart_rate_bpm=74, systolic_mmhg=124, diastolic_mmhg=80, spo2_pct=97,
                temp_c=36.8, resp_rate_bpm=15, sleep_h_last_night=6.8, mood_1to5=4)),
    "a3": ("Dr. Sara Okafor", "Crew Medical Officer",
           dict(heart_rate_bpm=66, systolic_mmhg=118, diastolic_mmhg=76, spo2_pct=98,
                temp_c=36.6, resp_rate_bpm=13, sleep_h_last_night=7.5, mood_1to5=5)),
    "a4": ("Jonas Berg", "Mission Specialist",
           dict(heart_rate_bpm=62, systolic_mmhg=116, diastolic_mmhg=74, spo2_pct=98,
                temp_c=36.4, resp_rate_bpm=14, sleep_h_last_night=7.0, mood_1to5=4)),
}

# --- Thresholds (placeholders) -----------------------------------------------
ORTHO_HR_UP, ORTHO_SYS_DOWN = 0.25, 0.15
CO2_RESP_UP, CO2_HR_UP = 0.30, 0.05
CABIN_CO2_NOMINAL_MMHG = 2.6
CABIN_CO2_HIGH_MMHG = 4.0   # placeholder; NASA-STD-3001 / OCHMO CO2 brief set the real limits
FEVER_TEMP_UP_C, FEVER_HR_UP = 1.0, 0.15
SLEEP_DEBT_H, SLEEP_DEBT_NIGHTS, SLEEP_DEBT_MOOD, SLEEP_DEBT_HR_UP = 6.0, 3, 2, 0.05
SANS_TRIGGER, SANS_CLEAR = 50, 40
CLEAR_AFTER_TICKS = 5       # consecutive non-matching ticks before a vitals alert clears

CO2_BRIEF_URL = "https://www.nasa.gov/wp-content/uploads/2023/12/ochmo-tb-004-carbon-dioxide.pdf"
SANS_URL = "https://www.nasa.gov/reference/risk-of-spaceflight-associated-neuro-ocular-syndrome-sans"

PROFILES = {
    "orthostatic": dict(severity="alert", hazard="gravity", body_region="heart", act_within_s=600,
                        onboard_action="Lie flat, legs raised. Drink 500 ml with salt tablets, re-measure in 10 min."),
    "co2": dict(severity="alert", hazard="environment", body_region="lungs", act_within_s=900,
                onboard_action="Move to a well-ventilated module and check the CO2 scrubber reading."),
    "fever": dict(severity="alert", hazard="environment", body_region="skin", act_within_s=3600,
                  onboard_action="Rest, drink fluids, log temperature every hour."),
    # Hazard follows docs/api-spec.md ("distance"); NASA HRP files SANS under altered gravity.
    "sans": dict(severity="watch", hazard="distance", body_region="head", act_within_s=86400,
                 onboard_action="Do an Amsler grid and acuity check today; log any headache."),
    "sleep_debt": dict(severity="watch", hazard="isolation", body_region="head", act_within_s=86400,
                       onboard_action="Consider pre-sleep lighting (2700K) 1 h before bed, screens aside, eye mask."),
}
VITALS_PROFILES = ("orthostatic", "co2", "fever", "sleep_debt")

# Sensors aren't right 100% of the time, so a vitals alert asks whether the astronaut
# actually feels it. "No" marks the readings as a likely sensor error in their history.
CONFIRM_QUESTIONS = {
    "orthostatic": "Do you feel dizzy or light-headed, especially when you move or stand?",
    "co2": "Are you short of breath or do you have a headache?",
    "fever": "Do you feel feverish, hot or shivery?",
    "sleep_debt": "Do you feel more tired than usual?",
}

# Suggested on-board steps for when help from Earth is late or unreachable.
# PLACEHOLDERS for the demo: check against the onboard medical checklist. Not medical advice.
PROTOCOLS = {
    "orthostatic": [
        "Lie down and raise your legs.",
        "Drink about 500 ml of fluid with salt tablets.",
        "Re-measure heart rate and blood pressure after 10 minutes.",
        "If you faint, feel worse, or it doesn't settle: tell a crewmate and the Crew Medical Officer now.",
    ],
    "co2": [
        "Move to a well-ventilated module.",
        "Check the cabin CO2 readout and the scrubber status.",
        "Tell the crew, since CO2 affects everyone in the module.",
        "If breathing or a headache gets worse: alert the Crew Medical Officer now.",
    ],
    "fever": [
        "Rest and drink fluids.",
        "Log your temperature every hour.",
        "Limit close contact with crewmates until it settles.",
        "If temperature keeps rising or you feel very unwell: alert the Crew Medical Officer.",
    ],
    "sleep_debt": [
        "Consider pre-sleep lighting (2700K) about 1 hour before bed, and screens aside.",
        "Use the eye mask and earplugs.",
        "A private conference with the flight surgeon is always an option, even if it's delayed.",
    ],
    "sans": [
        "Do the Amsler grid and visual acuity check today.",
        "Log any headache or blurred vision.",
        "Ask whether an OCT scan is worthwhile at the next opportunity.",
    ],
}

# What POST /debug/scenario does to the simulation: vitals drift toward
# baseline x MULT (+ ADD), so they move together coherently. `sans` instead
# injects a check-in, the same path a real astronaut's check-in takes.
SCENARIO_MULT = {
    "orthostatic": {"heart_rate_bpm": 1.32, "systolic_mmhg": 0.80},
    "fever": {"heart_rate_bpm": 1.20},
    "co2": {"resp_rate_bpm": 1.38, "heart_rate_bpm": 1.10},
    "sleep_debt": {"heart_rate_bpm": 1.08},
}
SCENARIO_ADD = {"fever": {"temp_c": 1.3}}
SCENARIO_CABIN_CO2_MMHG = {"co2": 5.3}
SCENARIO_SLEEP_NIGHTS_H = [5.4, 5.1, 5.0]
SCENARIO_SLEEP_MOOD = 2


@dataclass
class Context:
    cabin_co2_mmhg: float
    headache_24h: bool
    sleep_last_nights: list[float]  # most recent last
    mood: int


def pct(value: float, base: float) -> float:
    return (value - base) / base if base else 0.0


def matches(profile: str, v: dict, b: dict, ctx: Context) -> bool:
    hr_up = pct(v["heart_rate_bpm"], b["heart_rate_bpm"])
    if profile == "orthostatic":
        return hr_up > ORTHO_HR_UP and pct(v["systolic_mmhg"], b["systolic_mmhg"]) < -ORTHO_SYS_DOWN
    if profile == "co2":
        return (pct(v["resp_rate_bpm"], b["resp_rate_bpm"]) > CO2_RESP_UP and hr_up > CO2_HR_UP
                and (ctx.cabin_co2_mmhg > CABIN_CO2_HIGH_MMHG or ctx.headache_24h))
    if profile == "fever":
        return v["temp_c"] - b["temp_c"] > FEVER_TEMP_UP_C and hr_up > FEVER_HR_UP
    if profile == "sleep_debt":
        last = ctx.sleep_last_nights[-SLEEP_DEBT_NIGHTS:]
        return (len(last) == SLEEP_DEBT_NIGHTS and all(h < SLEEP_DEBT_H for h in last)
                and ctx.mood <= SLEEP_DEBT_MOOD and hr_up > SLEEP_DEBT_HR_UP)
    return False


# --- SANS risk score ------------------------------------------------------------

@dataclass
class SansComponent:
    name: str
    points: float
    detail: str


def sans_score(mission_day: int, baseline_acuity: Optional[float], latest_acuity: Optional[int],
               amsler_14d: bool, headaches_7d: int, co2_avg_7d: Optional[float]) -> tuple[int, list[SansComponent]]:
    """0-100 between-scans risk score. A risk score, never a diagnosis."""
    parts = [SansComponent("mission_duration", round(20 * min(1.0, mission_day / 180), 1),
                           f"Mission day {mission_day}: SANS signs become more common the longer the flight.")]
    if baseline_acuity is not None and latest_acuity is not None:
        lines = max(0.0, baseline_acuity - latest_acuity)
        parts.append(SansComponent("vision_acuity", min(30.0, 15 * lines),
                                   f"Visual acuity line {latest_acuity}, your day 7-14 baseline {baseline_acuity:g}."))
    parts.append(SansComponent("amsler_grid", 25.0 if amsler_14d else 0.0,
                               "Amsler grid distortion reported in the last 14 days." if amsler_14d
                               else "No Amsler grid distortion in the last 14 days."))
    parts.append(SansComponent("headaches", float(min(24, 8 * headaches_7d)),
                               f"{headaches_7d} headache report(s) in the last 7 days."))
    if co2_avg_7d is not None:
        parts.append(SansComponent(
            "cabin_co2", round(10 * min(1.0, max(0.0, (co2_avg_7d - 2.5) / 2.0)), 1),
            f"Cabin CO2 7-day average {co2_avg_7d:.1f} mmHg (NASA links CO2 and headaches with SANS)."))
    return min(100, round(sum(p.points for p in parts))), parts


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
                     sans_parts: Optional[list[SansComponent]] = None,
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
                   f"tell a crewmate or the Crew Medical Officer. This is saved and will be sent to the flight "
                   f"surgeon as soon as contact returns.")
    elif acts_on_board(act_within, real_one_way_delay_s):
        verdict = (f"Ground will see this in about {_mins(real_one_way_delay_s)} min, and a reply takes about "
                   f"{_mins(2 * real_one_way_delay_s)} min. That is longer than this can safely wait, so the "
                   f"on-board step comes first.")
    else:
        verdict = (f"This can wait for the flight surgeon: they will see it in about "
                   f"{_mins(real_one_way_delay_s)} min.")
    hr, bhr = v["heart_rate_bpm"], b["heart_rate_bpm"]

    if profile == "orthostatic":
        return dict(
            why="Your heart rate is well above your own baseline while your systolic pressure is below it. "
                "In low gravity the body's blood-pressure control adapts, and this pattern can point to "
                "cardiovascular deconditioning.",
            trend=f"Heart rate {hr:.0f} bpm vs your baseline {bhr:.0f} ({_signed(100 * pct(hr, bhr))}); "
                  f"systolic {v['systolic_mmhg']:.0f} vs {b['systolic_mmhg']:.0f} mmHg "
                  f"({_signed(100 * pct(v['systolic_mmhg'], b['systolic_mmhg']))}).",
            recommended_action="Lie down with your legs raised, take fluids with salt, and re-measure in "
                               "10 minutes. " + verdict)
    if profile == "co2":
        cause = (f"cabin CO2 is high ({ctx.cabin_co2_mmhg:.1f} mmHg)" if ctx.cabin_co2_mmhg > CABIN_CO2_HIGH_MMHG
                 else "you reported a headache")
        return dict(
            why=f"Your breathing rate and heart rate are up together, and {cause}. That can happen when CO2 "
                f"builds up in the cabin.",
            trend=f"Breathing {v['resp_rate_bpm']:.0f}/min vs your baseline {b['resp_rate_bpm']:.0f} "
                  f"({_signed(100 * pct(v['resp_rate_bpm'], b['resp_rate_bpm']))}); heart rate "
                  f"{_signed(100 * pct(hr, bhr))}; cabin CO2 {ctx.cabin_co2_mmhg:.1f} mmHg.",
            recommended_action="Consider moving to a well-ventilated module and checking the CO2 scrubber "
                               "reading. " + verdict)
    if profile == "fever":
        return dict(
            why="Your temperature and heart rate are both above your own baseline, which may suggest an "
                "infection. Immune function can change in spaceflight.",
            trend=f"Temperature {v['temp_c']:.1f} °C vs your baseline {b['temp_c']:.1f} "
                  f"({v['temp_c'] - b['temp_c']:+.1f} °C); heart rate {_signed(100 * pct(hr, bhr))}.",
            recommended_action="Consider resting, drinking fluids and logging your temperature every hour. "
                               + verdict)
    if profile == "sleep_debt":
        nights = ", ".join(f"{h:.1f}" for h in ctx.sleep_last_nights[-SLEEP_DEBT_NIGHTS:])
        return dict(
            why="Several short nights, a lower mood and a raised resting heart rate together may point to "
                "building sleep debt and strain.",
            trend=f"Last {SLEEP_DEBT_NIGHTS} nights: {nights} h vs your usual {b['sleep_h_last_night']:.1f} h; "
                  f"mood {ctx.mood}/5; heart rate {_signed(100 * pct(hr, bhr))}.",
            recommended_action="You might consider protecting tonight's sleep with the station's pre-sleep "
                               "lighting (2700K) about 1 h before bed. A private conference with the flight "
                               "surgeon is always an option. " + verdict)
    if profile == "sans":
        details = "; ".join(p.detail for p in (sans_parts or []) if p.points > 0)
        return dict(
            why="Your SANS risk score has risen. This is a risk score, not a diagnosis: it suggests a closer "
                "look at your eyes may be worthwhile before the next scheduled scan.",
            trend=details or "Several small signals have added up.",
            recommended_action="Consider repeating the Amsler grid and acuity check, and asking whether an OCT "
                               "scan is worthwhile. " + verdict)
    raise ValueError(profile)
