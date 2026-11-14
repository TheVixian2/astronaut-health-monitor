# What we monitor

Everything the system measures, where it comes from, and what it feeds.
Companion to `docs/api-spec.md`: the spec defines the shapes, this explains the
meaning. **Focus since 2026-11-14: behavioral (mental) health** of a crew of four
on NASA's 850-day Mars reference mission. Every signal below has published
evidence behind it; anything without evidence was cut.

## 1. Measured by the watch

| Signal | Field | Units | Source | Status |
|---|---|---|---|---|
| Heart rate | `heart_rate_bpm` | bpm | **Watch** (`a1`), `POST /astronauts/{id}/ingest`, ~3 s | live |
| Heart-rate variability (SDNN) | `hrv_sdnn_ms` | ms | watch | **planned** — lower HRV tracks depression (Kemp 2010 meta-analysis) |
| Activity | `active_min` | min/day | watch | **planned** — crews grew more sedentary in Mars-500 (Basner 2013) |

`a2`–`a4` have no device: their vitals are simulated (section 2).

## 2. Simulated vitals — all astronauts

Random walk with mean reversion around **each astronaut's own baseline**, shifted
coherently by a scenario (`sleep_debt`, `strain`).

| Signal | Field | Units | Typical |
|---|---|---|---|
| Blood oxygen | `spo2_pct` | % | 96–99 |
| Temperature | `temp_c` | °C | ~36.4–37.0 |
| Respiratory rate | `resp_rate_bpm` | breaths/min | 12–16 |
| Sleep last night | `sleep_h_last_night` | hours | from the on-board lighting log (`circadian.py`) |
| Mood | `mood_1to5` | 1–5 | from the latest check-in |

**Blood pressure was removed** (2026-11-14): no consumer watch can measure it.

## 3. Astronaut-entered — `POST /astronauts/{id}/checkin`

| Signal | Field | Type | Evidence |
|---|---|---|---|
| Mood | `mood_1to5` | int 1–5 | self-report |
| Sleep | `sleep_h` | float | overrides the lighting-log estimate |
| PHQ-2 | `phq2.{little_interest, feeling_down}` | 0–3 each | validated depression screen; ≥ 3 is positive (Kroenke 2003) |
| Reaction test | `reaction_test.{mean_rt_ms, lapses, ...}` | 3-min PVT-B | NASA's fatigue test on ISS; lapse = > 355 ms |
| Symptoms | `symptoms` | list[str] | free context, e.g. `headache` |
| Share with ground | `share_with_ground` | bool | the astronaut's control over what Mission Control sees |

## 4. Mission state

| Signal | Field | Source | Notes |
|---|---|---|---|
| Environment | `environment` | `GET/PUT /mission` | `iss` \| `moon` \| `mars` |
| One-way light delay | `one_way_delay_s` / `real_one_way_delay_s` | `/mission` | demo 20 s / real 1320 s; live Mars value from NASA JPL Horizons |
| Mission day | server | for the baseline window and the third-quarter morale dip (Stuster 2010) |
| Lighting mode | `circadian` | on-board lighting log | ISS SSLA modes |

## 5. Personal baseline — the core idea

Per astronaut, computed from **mission days 7–14** of stored history (earlier
days are distorted by space adaptation). Nothing is compared to a population
threshold.

## 6. What is evaluated

- **Wellbeing level** (`backend/behavioral.py`): `steady / watch / concern / urgent`
  from PHQ-2, mood, sleep and body clock, reaction time and resting HR, each vs the
  astronaut's own baseline. Decided, not built yet: watch signals (HRV, resting HR,
  sleep, activity) carry 60–80 % of the score.
- **`sleep_debt` alert:** < 6 h × 3 nights **and** mood ≤ 2 **and** resting HR up.
- **Who is told:** commander first, who releases it to the astronaut; the deputy if
  the commander is the one flagged; Mission Control after the light delay.

Thresholds are placeholders pending tuning. Decision support only, never a diagnosis.

## 7. Cut, with reasons

`orthostatic`, `fever`, `co2`, `sans`, `spe`, blood pressure and the vision check
(pivot to mental health); peer ratings, music, plant care, window time and Earth
photos (no published evidence that they track mood).
