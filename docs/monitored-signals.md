# What we monitor

Everything the system measures, where it comes from, and what it feeds.
Companion to `docs/api-spec.md` — the spec defines the shapes, this explains
the meaning.

> **Scope note (2026-11-14):** the SANS pivot is agreed in principle but
> `api-spec.md` has not been updated yet. Rows marked **[NEW]** don't exist in
> the spec; rows marked **[CUT?]** are candidates for removal. Confirm with Luca
> before building those.

## 1. Real measured signal — one only

| Signal | Field | Units | Source | Rate |
|---|---|---|---|---|
| Heart rate | `heart_rate_bpm` | bpm | **Watch** (`a1` only), via `POST /astronauts/{id}/ingest` | ~3 s |

That's it. Everything else in the system is simulated server-side. `a2`–`a4`
have no device at all.

## 2. Simulated vitals — all astronauts

Driven by a per-astronaut scenario state so they move together coherently
(fever raises temperature **and** heart rate). Use a **random walk with mean
reversion**, not independent random values and not linear ramps:

```python
value += random.gauss(0, step) + (baseline - value) * 0.05
```

| Signal | Field | Units | Typical |
|---|---|---|---|
| Systolic BP | `systolic_mmhg` | mmHg | ~110–125 |
| Diastolic BP | `diastolic_mmhg` | mmHg | ~70–82 |
| Blood oxygen | `spo2_pct` | % | 96–99 |
| Core temperature | `temp_c` | °C | ~36.4–37.0 |
| Respiratory rate | `resp_rate_bpm` | breaths/min | 12–16 |
| Sleep last night | `sleep_h_last_night` | hours | 5–8 |
| Mood | `mood_1to5` | 1–5 | 3–5 |

**Give every astronaut a genuinely different baseline.** If all four share one,
the personal-baseline idea is doing no work and a judge will notice. e.g. `a1`
low-HR endurance type (~58 bpm), `a2` higher (~74).

## 3. Astronaut-entered — `POST /astronauts/{id}/checkin`

| Signal | Field | Type | Notes |
|---|---|---|---|
| Mood | `mood_1to5` | int 1–5 | optional |
| Sleep | `sleep_h` | float | optional |
| Symptoms | `symptoms` | list[str] | `headache` matters — feeds both `co2` and SANS risk |
| Amsler distortion | `vision.amsler_distortion` | bool | grid lines wavy/missing |
| Visual acuity | `vision.acuity_line` | int | chart line reached |
| Share with ground | `share_with_ground` | bool | astronaut controls what the flight surgeon sees |

## 4. Environment / mission state

| Signal | Field | Source | Notes |
|---|---|---|---|
| Mission environment | `environment` | `GET/PUT /mission` | `iss` \| `moon` \| `mars` |
| One-way light delay | `one_way_delay_s` | `GET/PUT /mission` | ISS 0, Moon ~1.3 s, Mars 180–1320 s. **Demo runs compressed to ~20 s** |
| Mission day | **[NEW]** | server | needed for the baseline window and SANS risk accumulation |
| Cabin CO2 | simulated | server | input to `co2` and to SANS risk |
| Proton flux | `flux_10mev_pfu` | NOAA GOES | **[CUT?]** only if `spe` survives |

## 5. Personal baseline — the core idea

Per astronaut, same fields as the vitals snapshot, computed from **mission days
7–14** (earlier days are distorted by space adaptation and fluid shift), tagged
with the environment's gravity (0 g ISS, 1/6 g Moon, 3/8 g Mars).

`--seed-baseline` fills this history instantly so the demo doesn't wait.

**Nothing is compared to a population threshold.** Every condition below is
expressed as a deviation from that astronaut's own normal.

## 6. Conditions evaluated

Checked every tick. **Fire only on a NEW match** — not on every tick while the
condition persists. That gate is what stops repeat Claude API calls.

| id | Trigger (vs. personal baseline) | Region | act_within_s | Status |
|---|---|---|---|---|
| `orthostatic` | HR > +25% **AND** systolic < −15% | heart | 600 | **keep** |
| `sans` | vision trend + CO2 + headache + mission day → **risk score** | head | ~86400 | **[NEW] keep** |
| `co2` | resp rate > +30% **AND** HR up **AND** (cabin CO2 high **OR** headache) | lungs | 900 | **[CUT?]** may survive as a SANS input only |
| `fever` | temp > +1.0 °C **AND** HR > +15% | skin | 3600 | **[CUT?]** |
| `sleep_debt` | <6 h × 3 nights **AND** mood ≤2 **AND** resting HR up | head | 86400 | **[CUT?]** 24 h window, undemoable |
| `spe` | NOAA ≥10 MeV flux ≥ 10 pfu | whole_body | 300 | **[CUT?]** external, whole-crew |

All thresholds are **placeholders** pending tuning.

`sans` is a **risk score, never a diagnosis** — it's the between-scans
early-warning layer that says "worth doing an OCT scan / escalating", not a
finding.

## 7. Computed per alert

| Value | Meaning |
|---|---|
| `severity` | `watch` (yellow) / `alert` (orange) / `critical` (red) |
| `body_region` | `heart` \| `head` \| `lungs` \| `skin` \| `whole_body` |
| `onboard_action` | one pre-written line — the only text the watch shows |
| `act_within_s` | how long this can safely wait |
| `ground_eta_s` | when the flight surgeon will see it |
| **verdict** | round-trip > `act_within_s` → "Act on board now" + protocol; else "Ground will see this in X min" |
| `insight` | Claude's `{why, trend, recommended_action}`, or `null` until it returns. **Web app only.** |
