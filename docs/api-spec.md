# API spec

**Owner: Luca.** Nobody else edits this file — open a PR and ask.
**Last reconciled with the running backend: 2026-11-14.**

Base URL (dev): `http://localhost:8000`. Auth: none (local hackathon demo).
Crew ids: `a1`–`a4` (`a1` is the watch wearer). All timestamps ISO 8601 UTC.
CORS is open for local dev.

> **How to read this:** sections marked **PROVISIONAL** are implemented and live
> but not yet locked — they may still change shape. Everything else is settled.

---

## Mission

### `GET /mission`
```json
{ "environment": "iss|moon|mars", "one_way_delay_s": 20, "real_one_way_delay_s": 1320 }
```

**Two delays, and the difference matters.**

| Field | Meaning |
|---|---|
| `one_way_delay_s` | How long the **Ground stream actually waits**. Compressed to ~20 s for the demo so nobody watches a blank screen. |
| `real_one_way_delay_s` | The **true** light time for this environment. Drives the verdict (below). Mars default `1320` (22 min). |

Optional on `PUT`; defaults to `one_way_delay_s`.

### `PUT /mission`
Same shape as the `GET` response.

### The verdict rule

```
2 × real_one_way_delay_s  >  act_within_s   →  "Act on board now" + protocol
otherwise                                   →  "Ground will see this in X min"
```

**Always `real_one_way_delay_s`, never the compressed demo value.** Using the
compressed delay makes every condition resolve to "ground will advise" and
destroys the point of the product.

With the Mars defaults the round trip is 44 min, so anything that cannot wait
that long is handled on board (by the astronaut and the commander) first.

---

## Crew

### `GET /crew`
```json
[{ "id": "a1", "name": "Cmdr. Elena Ionescu", "role": "Commander",
   "status": "nominal|watch|alert|critical" }]
```

---

## Vitals

Only `heart_rate_bpm` for `a1` is real (from the watch). Every other vital, and
all of `a2`–`a4`, is simulated server-side — see `docs/monitored-signals.md`.

### `POST /astronauts/{id}/ingest`
Request:
```json
{ "timestamp": "2026-11-14T10:00:00Z", "heart_rate_bpm": 72, "source": "real|simulated" }
```
Response `202`: `{ "accepted": true }`

### `GET /astronauts/{id}/vitals`
```json
{
  "heart_rate_bpm": 62,
  "spo2_pct": 98, "temp_c": 36.5, "resp_rate_bpm": 12,
  "sleep_h_last_night": 7.2, "mood_1to5": 4,
  "timestamp": "2026-11-14T10:31:42Z", "source": "simulated",
  "baseline": { "heart_rate_bpm": 58,
                "spo2_pct": 98, "temp_c": 36.5, "resp_rate_bpm": 12,
                "sleep_h_last_night": 7.2, "mood_1to5": 4 }
}
```

`baseline` carries the same vitals fields, computed over mission days 7–14.
**Everything is compared to the astronaut's own baseline, never to a population
threshold.**

`sleep_h_last_night` is derived from the on-board lighting log unless a check-in
overrides it.

### `GET /astronauts/{id}/stream?view=crew|ground`
Server-Sent Events. Named events:

- `vitals` — a vitals snapshot, every ~3 s
- `alert` — an Alert object

`view=ground` is held back by `one_way_delay_s`. `view=crew` is not delayed.
The stream opens with a comment line: `: connected view=crew one_way_delay_s=20`.

---

## Alerts

### `GET /astronauts/{id}/alerts` → `[Alert]`

### Alert object
```json
{
  "id": "...", "astronaut_id": "a1", "profile": "sleep_debt",
  "severity": "watch|alert|critical",
  "hazard": "radiation|isolation|distance|gravity|environment",
  "body_region": "heart|head|lungs|skin|whole_body",
  "started_at": "2026-11-14T10:00:00Z",
  "onboard_action": "one pre-written line — the only text the watch shows",
  "act_within_s": 600,
  "ground_eta_s": 1320,
  "insight": { "why": "...", "trend": "...", "recommended_action": "..." }
}
```

`insight` is `null` until the Claude call returns, and **null is a valid final
state** — render the alert without it. Web app only; the watch shows
`onboard_action` and nothing else.

Alerts fire **only on a NEW match**, not on every tick while the condition
persists. That gate is what stops repeated Claude calls.

### Condition profiles

Thresholds are **placeholders** pending tuning.

| id | Trigger (vs. personal baseline) | Hazard | Region | act_within_s | Mars verdict |
|---|---|---|---|---|---|
| `sleep_debt` | < 6 h × 3 nights **AND** mood ≤ 2 **AND** resting HR up | isolation | head | 86400 | ground advises |

The physical profiles (`orthostatic`, `co2`, `fever`, `sans`, `spe`) were **removed
2026-11-14** in the pivot to mental health (see Removed below). The main signal is
now the **wellbeing level** (next section); `sleep_debt` is the one remaining alert.

---

## Check-in

### `POST /astronauts/{id}/checkin` → `202`
```json
{
  "timestamp": "2026-11-14T10:00:00Z",
  "mood_1to5": 3,
  "sleep_h": 5.5,
  "symptoms": ["headache"],
  "share_with_ground": true,
  "phq2": { "little_interest": 0, "feeling_down": 1 },
  "reaction_test": { "mean_rt_ms": 262, "lapses": 2, "false_starts": 0, "duration_s": 180 }
}
```
Only `timestamp` and `share_with_ground` are required.

`phq2` answers are 0-3 each (validated wording: `GET /checkin/questions`); a
total of 3 or more is a positive screen. `reaction_test` is the 3-minute PVT-B
(lapse = response over 355 ms). Both feed the wellbeing level.

**`share_with_ground` is the astronaut's control over what Mission Control
sees.** It is a deliberate design position, not a toggle for convenience — see
`presentation/ideas.md` on under-reporting.

---

## Wellbeing — **PROVISIONAL** (live in `backend/behavioral.py`)

`viewer` = the signed-in astronaut's id, or `ground`. Demo-level, not security.

- `GET /astronauts/{id}/wellbeing?viewer=` → `{astronaut_id, view, mission_day, level,
  score, signals[{name, area, value, baseline, points, detail, crew_wide}], ...}`.
  `level` is `steady | watch | concern | urgent`. Signals today: `phq2`, `mood`,
  `sleep`, `body_clock`, `reaction_time`, `resting_heart_rate`, each vs the
  astronaut's own mission days 7-14.
- `PUT /astronauts/{id}/wellbeing/sharing?viewer=` `{commander?, ground?}`
- `GET /crew/wellbeing?viewer=a1|ground` → members + crew-wide trends (only when
  ≥ 3 crew share a trend; PHQ-2 is never aggregated).
- `GET /notifications?viewer=` → `[Notice]`; also pushed live as SSE event `notice`.
- `GET /checkin/questions` → exact PHQ-2 wording + reaction-test instructions.

- **Commander first (live):** the commander (`viewer=a1`) always sees every crew
  member's `level` and `areas` (masked signals, never PHQ-2 answers);
  `GET /crew/wellbeing` members carry `visible_because: commander_first` and `areas`.
  Mission Control still needs sharing or the urgent level.
- `GET /astronauts/{id}/history?hours=&bucket_s=` → each point also has `low{}` and
  `high{}` per field; `bucket_s=3600` = hour by hour.

## Cabin environment — **PROVISIONAL**, real NASA data (`backend/iss_live.py`)

Live from **NASA ISS Live** telemetry (public Lightstreamer feed, adapter `ISSLIVE`):
US Lab + Node 3 ppCO2, Lab ppO2, cabin pressure, cabin air temperature.

- `GET /environment` → `{source, updated_at, ppco2_lab_mmhg, ppco2_node3_mmhg,
  ppo2_lab_mmhg, cabin_pressure_mmhg, cabin_temp_c, co2_mmhg, co2_1h_avg_mmhg,
  co2_limit_mmhg: 3, status: ok|elevated|above_limit|unavailable, note, source_url}`
- SSE event **`environment`** (same shape) on every stream, ~every 30 s.
- NASA-STD-3001 limit: 3 mmHg 1-hour average; `elevated` from 2.5 (OCHMO-TB-004:
  headache risk < 1 % needs a 7-day average below 2.5). Elevated CO2 adds a
  crew-wide suggestion to `GET /crew/wellbeing`.
- `AHM_ISS_LIVE=0` turns the feed off; without network `status` is `unavailable`.
- **Demo only:** `POST /debug/cabin {ppco2_mmhg, minutes}` replaces the live CO2 for a
  few minutes (`{}` ends it) so the on-board alarm can be shown; while active,
  `demo_override: true` and `source` says "DEMO OVERRIDE, not real ISS data".

## Habitat — **PROVISIONAL** (live in `backend/habitat.py`)

Room per astronaut from a Bluetooth beacon per module (simulated by a fixed daily
schedule). **The hygiene module has no beacon and is never tracked.**

- `GET /habitat` → `[{id, name, kind: shared|private|untracked}]`
- `GET /crew/locations?viewer=a1|ground` → `[{astronaut_id, name, room|null,
  room_name, since}]` — safety use (fire, depressurisation).
- `GET /astronauts/{id}/rooms?viewer=<self>|a1` → `{hours{room: h}, shared_h,
  private_h, shared_normal_h, shared_so_far_normal_h, shared_7d_avg_h, note}`.
  Supporting signal only (weak evidence): shown, never added to the wellbeing score.

### Decided 2026-11-14, NOT built yet

1. **Release step (still to build).** A psychological flag reaches the
   **commander** first; the commander releases it to the astronaut.
   `PUT /astronauts/{id}/alerts/{alert_id}/release` (commander, or the deputy) sets
   `released_to_crew_at`; `view=crew` streams withhold unreleased psychological items.
   **If the commander is the one flagged, it goes to the deputy (pilot) instead.**
   Ground always receives it after the light delay. A warning must never stay hidden
   from the astronaut for good: the challenge asks that astronauts can evaluate and
   act on their own health.
2. **Watch-driven stress score.** `POST /ingest` gains optional `hrv_sdnn_ms` and
   `active_min`. Watch signals (HRV, resting HR, sleep, activity) carry **60-80 %**
   of the wellbeing score; check-ins (PHQ-2, mood, reaction test) the rest. The
   weighting is a design choice, not a published value — say so.

---

## Circadian — **PROVISIONAL**

Added 2026-11-14 after a mentor/judge raised it (`events/2026-11-14-mentor-judges.md`).
Live in `backend/circadian.py`. Shapes may still change.

Framing: the lighting system is **the countermeasure, not the signal**. On a Mars
transit there is no external day/night cue — the station lighting is the only
zeitgeber the crew has.

### `GET /astronauts/{id}/circadian?view=crew|ground`
```json
{
  "astronaut_id": "a1",
  "share_with_ground": false,
  "lighting": { "mode": "general|pre_sleep|phase_shift|off", "cct_k": 4500,
                "since": "2026-11-14T05:43:00Z" },
  "nights": [{ "night_of": "2026-11-07", "bedtime": "...", "wake_time": "...",
               "sleep_h": 7.1, "pre_sleep_lighting_min": 10,
               "bright_light_last_hour": true }],
  "summary": { "status": "nominal|watch", "nights": 7,
               "bedtime_spread_min": 42, "nights_bright_before_sleep": 2 },
  "card": { ... },
  "recommendation": { "text": "...", "source": "...", "source_url": "..." },
  "evidence": { ... }
}
```

**`view=ground` returns `403` unless the astronaut has shared** — same privacy
position as the check-in.

`cct_k` values follow the real NASA ISS Solid-State Lighting Assembly: general
4500 K, pre-sleep 2700 K (blue-depleted), phase-shift 6500 K (blue-enriched).

### `PUT /astronauts/{id}/circadian/sharing`
`{ "share_with_ground": true }`

### `PUT /astronauts/{id}/lighting`
`{ "mode": "general|pre_sleep|phase_shift|off" }` → returns the new `Lighting`.

This is the countermeasure actuator — the loop is: detect drift → recommend a
mode → verify sleep improved.

---

## Debug (dev only)

### `POST /debug/scenario` → `202`
```json
{ "astronaut_id": "a1", "scenario": "sleep_debt|strain|clear" }
```
Live. `sleep_debt` shifts vitals and sleep; `strain` injects a private check-in
that reaches `urgent` (commander + ground notified); `clear` resets the astronaut
and drops live check-ins so the demo can run again. Any other value → `422`.

---

## Removed

| Endpoint | Why |
|---|---|
| `GET /space-weather` | `spe` profile cut. Returns `404`. NOAA no longer called. |
| `GET /astronauts/{id}/sans` | Pivot to mental health, 2026-11-14. Returns `404`. |
| profiles `orthostatic`, `co2`, `fever`, `sans` | Same pivot. Tag `pre-mental-health-pivot` has them. |
| vitals `systolic_mmhg`, `diastolic_mmhg`; check-in `vision` | No watch measures blood pressure; vision fed only `sans`. |
