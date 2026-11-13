# API spec

**Owner: Luca.** Nobody else edits this file — open a PR and ask.

Base URL (dev): `http://localhost:8000`. Auth: none (local hackathon demo).
Crew ids: `a1`-`a4` (`a1` is the watch wearer). All timestamps ISO 8601 UTC.

## Crew

### `GET /crew`
```json
[{ "id": "a1", "name": "...", "role": "...", "status": "nominal|watch|alert|critical" }]
```

## Vitals

### `POST /astronauts/{id}/ingest`
Request:
```json
{ "timestamp": "2026-11-14T10:00:00Z", "heart_rate_bpm": 72, "source": "real|simulated" }
```
Response `202`:
```json
{ "accepted": true }
```

### `GET /astronauts/{id}/vitals`
Latest snapshot. `baseline` carries the same vitals fields.
```json
{
  "timestamp": "2026-11-14T10:00:00Z",
  "heart_rate_bpm": 72,
  "systolic_mmhg": 118,
  "diastolic_mmhg": 76,
  "spo2_pct": 98,
  "temp_c": 36.8,
  "resp_rate_bpm": 14,
  "sleep_h_last_night": 7.2,
  "mood_1to5": 4,
  "source": "real|simulated",
  "baseline": { "heart_rate_bpm": 65, "systolic_mmhg": 120, "diastolic_mmhg": 78,
                "spo2_pct": 98, "temp_c": 36.6, "resp_rate_bpm": 13,
                "sleep_h_last_night": 7.5, "mood_1to5": 4 }
}
```

### `GET /astronauts/{id}/stream?view=crew|ground`
Server-Sent Events. Event names:

- `vitals` — a vitals snapshot (same shape as above), every ~3 s.
- `alert` — an Alert object (below).

`view=ground` is delayed by the mission's one-way light time. `view=crew` is not
delayed.

## Alerts

### `GET /astronauts/{id}/alerts`
Returns `[Alert]`.

### Alert object
```json
{
  "id": "...",
  "astronaut_id": "a1",
  "profile": "fever",
  "severity": "watch|alert|critical",
  "hazard": "radiation|isolation|distance|gravity|environment",
  "body_region": "heart|head|lungs|skin|whole_body",
  "started_at": "2026-11-14T10:00:00Z",
  "onboard_action": "one pre-written line, shown on the watch",
  "act_within_s": 3600,
  "ground_eta_s": 780,
  "insight": { "why": "...", "trend": "...", "recommended_action": "..." }
}
```
`insight` is `null` until the Claude insight service returns.

## Mission

### `GET /mission`
```json
{ "environment": "iss|moon|mars", "one_way_delay_s": 780 }
```

### `PUT /mission`
Same shape as the `GET` response.

## Space weather

### `GET /space-weather`
```json
{ "flux_10mev_pfu": 0.21, "observed_at": "2026-11-14T10:00:00Z",
  "event_active": false,
  "source_url": "https://services.swpc.noaa.gov/json/goes/primary/integral-protons-6-hour.json" }
```

## Check-in

### `POST /astronauts/{id}/checkin`
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
Every field but `timestamp` and `share_with_ground` is optional.

## Debug (dev only)

### `POST /debug/scenario`
```json
{ "astronaut_id": "a1",
  "scenario": "fever|co2|orthostatic|sleep_debt|spe|clear" }
```
Drives the server-side simulation so the demo can trigger conditions on cue.
