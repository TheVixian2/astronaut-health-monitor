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

With the Mars defaults: `orthostatic` and `co2` → act on board; `fever` and
`sans` → ground will advise. That contrast is the demo.

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
  "heart_rate_bpm": 62, "systolic_mmhg": 112, "diastolic_mmhg": 72,
  "spo2_pct": 98, "temp_c": 36.5, "resp_rate_bpm": 12,
  "sleep_h_last_night": 7.2, "mood_1to5": 4,
  "timestamp": "2026-11-14T10:31:42Z", "source": "simulated",
  "baseline": { "heart_rate_bpm": 58, "systolic_mmhg": 112, "diastolic_mmhg": 72,
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
  "id": "...", "astronaut_id": "a1", "profile": "orthostatic",
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
| `orthostatic` | HR > +25% **AND** systolic < −15% | gravity | heart | 600 | act on board |
| `co2` | resp rate > +30% **AND** HR up **AND** (cabin CO2 high **OR** headache) | environment | lungs | 900 | act on board |
| `fever` | temp > +1.0 °C **AND** HR > +15% | environment | skin | 3600 | ground advises |
| `sans` | vision trend + cabin CO2 + headache + mission day → **risk score** | distance | head | 86400 | ground advises |
| `sleep_debt` | < 6 h × 3 nights **AND** mood ≤ 2 **AND** resting HR up | isolation | head | 86400 | ground advises |

**`spe` (solar particle event) is CUT**, and `GET /space-weather` with it. The
NOAA feed is no longer called. If radiation returns, it comes back as a spec
change here first.

`sans` is a **risk score, never a diagnosis** — the between-scans early-warning
layer that says "worth an OCT scan / escalate", not a finding. See
`presentation/ideas.md`.

---

## Check-in

### `POST /astronauts/{id}/checkin` → `202`
```json
{
  "timestamp": "2026-11-14T10:00:00Z",
  "mood_1to5": 3,
  "sleep_h": 5.5,
  "symptoms": ["headache"],
  "vision": { "amsler_distortion": false, "acuity_line": 8 },
  "share_with_ground": true
}
```
Only `timestamp` and `share_with_ground` are required.

`vision` feeds the `sans` risk score. `symptoms` containing `headache` feeds
both `co2` and `sans`.

**`share_with_ground` is the astronaut's control over what the flight surgeon
sees.** It is a deliberate design position, not a toggle for convenience — see
`presentation/ideas.md` on under-reporting.

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
{ "astronaut_id": "a1", "scenario": "fever|co2|orthostatic|sans|sleep_debt|clear" }
```
**Currently a stub** — accepts and returns `202` without driving the simulation.
Wire it up before the demo; it is the fallback if the watch misbehaves on stage.

---

## Removed

| Endpoint | Why |
|---|---|
| `GET /space-weather` | `spe` profile cut. Returns `404`. NOAA no longer called. |
