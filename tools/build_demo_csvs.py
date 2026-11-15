# Written with AI assistance (Claude Code, Anthropic) and reviewed by the team. See README "Use of AI".
"""Build the demo CSVs (web/demo-data/a1..a4.csv) from real wearable data plus synthetic fill.

Real part: LifeSnaps (Yfantidou et al., Scientific Data 2022, doi:10.1038/s41597-022-01764-x),
71 people wearing a Fitbit Sense for ~9 weeks, CC BY 4.0, https://zenodo.org/records/7229547.
We take the 4 people with the most complete days (2 women, 2 men, matching our crew) and keep
their real resting heart rate, HRV (RMSSD), sleep, active minutes, SpO2, breathing rate, steps,
Fitbit stress score and mood (from the 3-a-day mood check-ins).

Synthetic part (column `filled` names it on every row):
  - a missing day of a real column: that person's own median + noise of their own spread;
  - core temperature: Fitbit measures skin, not core, so 36.6 +/- 0.15 C (Earth, pre-flight);
  - SpO2 / breathing rate when the person has none: 97.5 +/- 0.7 % / 14 +/- 1 /min.
Mood 1-5 per day = 3 + 2 x (positive - negative) / all check-ins that day
(positive: happy, rested/relaxed, alert; negative: sad, tense/anxious, tired). Our mapping.

Dates are moved to the 9 weeks before our mission start (pre-flight baseline).
Run (needs the LifeSnaps archive's daily CSV, ~2 MB, not committed):
    backend/.venv/bin/python tools/build_demo_csvs.py <daily_fitbit_sema_df_unprocessed.csv>
"""
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

MISSION_START = date(2026, 10, 5)          # tools/simulate_crew.py seeds the mission from here
CREW = [("a1", "FEMALE"), ("a2", "MALE"), ("a3", "FEMALE"), ("a4", "MALE")]
POS, NEG, NEU = ["HAPPY", "RESTED/RELAXED", "ALERT"], ["SAD", "TENSE/ANXIOUS", "TIRED"], ["NEUTRAL"]
OUT = Path(__file__).resolve().parent.parent / "web" / "demo-data"
HEADER = """# Written with AI assistance (Claude Code, Anthropic) and reviewed by the team. See README "Use of AI".
# DEMO DATA for {aid}: REAL wearable days from LifeSnaps participant ...{pid} (Fitbit Sense), CC BY 4.0,
# Yfantidou et al., Scientific Data 2022, https://zenodo.org/records/7229547 - dates moved to before our mission.
# Values named in the `filled` column are SYNTHETIC (gap fill; core temperature is never measured by Fitbit).
# hrv_rmssd is Fitbit's nightly RMSSD. mood_1to5 is derived from the day's mood check-ins (see tools/build_demo_csvs.py).
"""


def load(path: str) -> pd.DataFrame:
    d = pd.read_csv(path)
    for c in POS + NEG + NEU:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    tot = d[POS + NEG + NEU].sum(axis=1)
    d["mood_1to5"] = (3 + 2 * (d[POS].sum(axis=1) - d[NEG].sum(axis=1)) / tot.where(tot > 0)).round(1)
    d["sleep_hours"] = (d["minutesAsleep"] / 60).round(2)
    d["active_minutes"] = d["very_active_minutes"] + d["moderately_active_minutes"]
    d = d.rename(columns={"resting_hr": "resting_heart_rate", "rmssd": "hrv_rmssd", "spo2": "spo2_pct",
                          "full_sleep_breathing_rate": "resp_rate"})
    d.loc[d["sleep_hours"] < 2, "sleep_hours"] = np.nan        # watch off at night, not a real 0 h
    d.loc[d["hrv_rmssd"] < 5, "hrv_rmssd"] = np.nan
    d.loc[d["resp_rate"] < 5, "resp_rate"] = np.nan
    d.loc[d["stress_score"] <= 0, "stress_score"] = np.nan    # Fitbit writes 0 when it has no score
    d["date"] = pd.to_datetime(d["date"])
    return d


REAL = ["resting_heart_rate", "hrv_rmssd", "sleep_hours", "active_minutes", "steps", "stress_score",
        "spo2_pct", "resp_rate", "mood_1to5"]
ROUND = {"resting_heart_rate": 1, "hrv_rmssd": 1, "sleep_hours": 2, "active_minutes": 0, "steps": 0,
         "stress_score": 0, "spo2_pct": 1, "resp_rate": 1, "mood_1to5": 1}
DEFAULT = {"spo2_pct": (97.5, 0.7), "resp_rate": (14.0, 1.0)}


def pick(d: pd.DataFrame) -> list[str]:
    core = d.dropna(subset=["resting_heart_rate", "hrv_rmssd", "sleep_hours", "mood_1to5"])
    counts = core.groupby("id").size().sort_values(ascending=False)
    gender = d.groupby("id")["gender"].first()
    chosen, used = [], set()
    for _, g in CREW:
        pid = next(p for p in counts.index if gender.get(p) == g and p not in used)
        chosen.append(pid)
        used.add(pid)
    return chosen


def build(d: pd.DataFrame, pid: str, aid: str, rng: np.random.Generator) -> pd.DataFrame:
    g = d[d["id"] == pid].set_index("date").sort_index()
    g = g[~g.index.duplicated()].asfreq("D")
    # keep the 63-day stretch with the most real mood days
    best = max(range(max(1, len(g) - 62)), key=lambda i: g["mood_1to5"].iloc[i:i + 63].notna().sum())
    g = g.iloc[best:best + 63].copy()
    filled = [[] for _ in range(len(g))]
    for col in REAL:
        s = g[col].astype(float)
        if s.notna().sum() >= 5:
            mu, sd = s.median(), max(s.std(), 1e-6)
        elif col in DEFAULT:
            mu, sd = DEFAULT[col]
        else:
            continue
        for i in np.where(s.isna())[0]:
            v = rng.normal(mu, sd * 0.6)
            if col == "mood_1to5":
                v = min(5, max(1, v))
            s.iloc[i] = max(0, v)
            filled[i].append(col)
        g[col] = s.round(ROUND[col])
    g["temp_c"] = rng.normal(36.6, 0.15, len(g)).round(1)
    for f in filled:
        f.append("temp_c")
    out = pd.DataFrame({"date": [MISSION_START - timedelta(days=len(g) - i) for i in range(len(g))]})
    for col in REAL + ["temp_c"]:
        if col in g:
            out[col] = g[col].to_numpy()
    out["filled"] = [" ".join(f) for f in filled]
    return out


def main() -> None:
    d = load(sys.argv[1])
    rng = np.random.default_rng(2026)
    OUT.mkdir(parents=True, exist_ok=True)
    for (aid, _), pid in zip(CREW, pick(d)):
        out = build(d, pid, aid, rng)
        real = 1 - out["filled"].str.split().str.len().sum() / (len(out) * (len(out.columns) - 2))
        path = OUT / f"{aid}.csv"
        path.write_text(HEADER.format(aid=aid, pid=pid[-6:]) + out.to_csv(index=False), encoding="utf-8")
        print(f"{aid}: LifeSnaps ...{pid[-6:]}, {len(out)} days, {real:.0%} of values real -> {path}")


if __name__ == "__main__":
    main()
