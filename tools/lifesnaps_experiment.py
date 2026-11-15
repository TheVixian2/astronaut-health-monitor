# Written with AI assistance (Claude Code, Anthropic) and reviewed by the team. See README "Use of AI".
"""Can watch signals predict mood? XGBoost on real wearable data (LifeSnaps, CC BY 4.0).

Data: LifeSnaps (Yfantidou et al., Scientific Data 2022), https://zenodo.org/records/7229547,
daily CSV `daily_fitbit_sema_df_unprocessed.csv` from the archive. Mood per day as in
tools/build_demo_csvs.py. Features are each person's deviation from their own median (our
personal-baseline idea): resting HR, HRV (RMSSD), sleep, active minutes.

For every person with >= 30 usable days: train on their first 70 % of days, test on the last 30 %.
  - "own average": predict their training-period mean mood (no model);
  - "general": XGBoost trained on everyone else;
  - "personal": XGBoost trained on their own first 70 %.
Daily mood and 7-day average mood. Result on 2026-11-15 (general / personal vs own average):
daily MAE 1.13 / 1.22 vs 1.11, low-mood-day AUC 0.53; weekly MAE 0.54 / 0.57 vs 0.54, low-mood-week
AUC 0.61. Neither model beats the person's own average; sleep has the only real link (r 0.11 daily, 0.21 weekly).

Run: backend/.venv/bin/python tools/lifesnaps_experiment.py <daily_fitbit_sema_df_unprocessed.csv>
Needs xgboost, scikit-learn, pandas (not backend requirements: an offline experiment).
"""
import sys

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import roc_auc_score

POS, NEG, NEU = ["HAPPY", "RESTED/RELAXED", "ALERT"], ["SAD", "TENSE/ANXIOUS", "TIRED"], ["NEUTRAL"]
PARAMS = dict(n_estimators=150, max_depth=2, learning_rate=0.05, subsample=0.8, random_state=0)
SIGNALS = {"rhr": "resting_hr", "hrv": "rmssd", "sleep": "sleep_h", "act": "active"}


def load(path: str) -> pd.DataFrame:
    d = pd.read_csv(path)
    for c in POS + NEG + NEU:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    tot = d[POS + NEG + NEU].sum(axis=1)
    d["mood"] = 3 + 2 * (d[POS].sum(axis=1) - d[NEG].sum(axis=1)) / tot.where(tot > 0)
    d["sleep_h"] = d["minutesAsleep"] / 60
    d["active"] = d["very_active_minutes"] + d["moderately_active_minutes"]
    d.loc[d["sleep_h"] < 2, "sleep_h"] = np.nan
    d.loc[d["rmssd"] < 5, "rmssd"] = np.nan
    d["date"] = pd.to_datetime(d["date"])
    return d


def weekly(d: pd.DataFrame) -> pd.DataFrame:
    out = []
    for pid, g in d.groupby("id"):
        g = g.set_index("date").sort_index()
        g = g[~g.index.duplicated()].asfreq("D")
        for c in list(SIGNALS.values()):
            g[c] = g[c].rolling(7, min_periods=4).mean()
        g["mood"] = g["mood"].rolling(7, min_periods=3).mean()
        g["id"] = pid
        out.append(g.reset_index())
    return pd.concat(out)


def feats(g: pd.DataFrame, ref: pd.DataFrame) -> pd.DataFrame:
    m = {k: ref[c].median() for k, c in SIGNALS.items()}
    return pd.DataFrame({"rhr": g.resting_hr - m["rhr"], "hrv": (g.rmssd / m["hrv"] - 1) * 100,
                         "sleep": g.sleep_h - m["sleep"], "act": g.active - m["act"]})


def run(d: pd.DataFrame, label: str) -> None:
    d = d.dropna(subset=list(SIGNALS.values()) + ["mood"]).reset_index(drop=True)
    X = pd.concat(feats(g, g) for _, g in d.groupby("id")).sort_index()
    y = pd.concat(g.mood - g.mood.mean() for _, g in d.groupby("id")).sort_index()
    ids = d["id"]
    people = [p for p, n in d.groupby("id").size().items() if n >= 30]
    res, aucs = [], []
    for p in people:
        g = d[d.id == p].sort_values("date")
        k = int(len(g) * 0.7)
        tr, te = g.iloc[:k], g.iloc[k:]
        own = np.abs(te.mood - tr.mood.mean()).mean()
        gm = xgb.XGBRegressor(**PARAMS).fit(X[ids != p], y[ids != p])
        pg = gm.predict(feats(te, tr)) + tr.mood.mean()
        pm = xgb.XGBRegressor(**PARAMS).fit(feats(tr, tr), tr.mood - tr.mood.mean())
        pp = pm.predict(feats(te, tr)) + tr.mood.mean()
        res.append((own, np.abs(te.mood - pg).mean(), np.abs(te.mood - pp).mean()))
        low = (te.mood < tr.mood.mean() - 0.5).astype(int)
        if low.nunique() == 2:
            aucs.append(roc_auc_score(low, -(pg - tr.mood.mean())))
    r = np.array(res).mean(axis=0)
    print(f"{label}: {len(people)} people | mean abs error: own average {r[0]:.2f}, "
          f"general {r[1]:.2f}, personal {r[2]:.2f} | low-mood AUC {np.mean(aucs):.2f} (0.5 = chance)")
    print("   correlation of each signal with mood (own-normal deviations):",
          {k: round(v, 3) for k, v in X.corrwith(y).items()})


if __name__ == "__main__":
    data = load(sys.argv[1])
    run(data, "Daily mood")
    run(weekly(data), "7-day mood")
