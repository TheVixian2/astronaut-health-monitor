# CLAUDE.md — Astronaut Health Monitor

NASA Space Apps Challenge 2026, "Create Health Monitoring Software for Astronauts
on Space Missions". We compare each astronaut's vitals to **their own personal
baseline** and flag named condition profiles. Decision support only — never a
diagnosis. The **astronaut is the primary user**: on a Mars mission the ground is
up to ~22 min away one way, so the astronaut is the first responder (NASA's
"Earth-independent medical operations"). Three parts share one API: a standalone
watchOS app, a FastAPI backend, and a no-build-step web app.

**The API contract is `docs/api-spec.md`.** It is the single source of truth for
every endpoint and payload shape.

## Locked decisions

- Data flow: Watch -> `POST /astronauts/{id}/ingest` every ~3 s -> backend updates
  baseline -> checks condition profiles -> on a NEW match calls the Claude insight
  service -> pushes to the web app over **Server-Sent Events** (not polling, not
  WebSockets).
- Only heart rate comes from the watch. Blood pressure, SpO2, temperature,
  respiratory rate, sleep and mood are **simulated server-side**, driven by a
  per-astronaut scenario state (e.g. "fever" raises temp AND heart rate together).
- **There is no physical watch.** All watch data comes from the watchOS Simulator
  via `SimulatedSource`. `HealthKitSource` stays a stub.
- **Baseline window:** mission days ~7-14 (earlier days are distorted by space
  adaptation / fluid shift), tagged with the environment's gravity (0 g ISS,
  1/6 g Moon, 3/8 g Mars). `--seed-baseline` fills this history instantly for demos.
- **Comms delay:** ISS 0 s, Moon ~1.3 s one way, Mars 3-22 min one way
  (configurable). The Ground SSE view is delayed by the one-way light time through
  a queue; the Self-check view and the watch are not. Each condition has
  `act_within_s`: if round-trip time > `act_within_s` the alert says "Act on board
  now" + the protocol, otherwise "Ground will see this in X min".
- **Radiation:** real NOAA GOES proton data from
  `https://services.swpc.noaa.gov/json/goes/primary/integral-protons-6-hour.json`.
  Event threshold >=10 MeV flux >= 10 pfu -> "Shelter now" for the whole crew +
  running dose estimate. GOES measures near Earth: label it a stand-in for
  deep-space scenarios.
- **Watch alert banner:** condition name + severity colour + haptic + ONE
  pre-written action line from the condition profile (not Claude-generated). The
  long Claude explanation is web-app only.
- **Claude insight service** (`backend/insight_service.py`): called only when a
  condition newly matches. `client.messages.parse()` with a Pydantic model
  `Insight(why, trend, recommended_action)`. Reads `ANTHROPIC_API_KEY` from the
  environment. **If the key is missing or the call fails, return a canned fallback
  Insight so the demo never breaks.** (Model id to be confirmed against live
  Anthropic docs before implementation.)
- Watch "Simulate exertion" button (debug builds only) ramps heart rate so the
  presenter can trigger an alert live.
- Demo runs on ONE Mac: backend + watchOS Simulator + web app. The Simulator
  reaches the backend at `http://localhost:8000` (needs `NSAllowsLocalNetworking`
  in the watch app's Info.plist).

## Condition profiles (thresholds are PLACEHOLDERS — tuned later)

| id | Profile | Signals vs. personal baseline | Hazard | act_within_s |
|---|---|---|---|---|
| `orthostatic` | Cardiovascular deconditioning | HR > baseline +25% AND systolic < baseline -15% | gravity | 600 |
| `fever` | Fever / possible infection | temp > baseline +1.0 C AND HR > baseline +15% | environment | 3600 |
| `co2` | CO2 exposure | resp rate > baseline +30% AND HR up AND cabin CO2 (simulated) high OR headache reported | environment | 900 |
| `sleep_debt` | Sleep debt / behavioural strain | < 6 h sleep 3 nights running AND mood <= 2/5 AND resting HR up | isolation | 86400 |
| `spe` | Solar particle event | NOAA >=10 MeV flux >= 10 pfu (external) | radiation | 300 |

Severity levels: `watch` (yellow), `alert` (orange), `critical` (red). Each
profile also stores `onboard_action` (one line for the watch) and `body_region`
(heart, head, lungs, skin, whole_body).

## Lanes

| Lane | Owner | Owns |
|---|---|---|
| Watch + API spec + integration | **Luca** (has the Mac) | `/watch-app`, `docs/api-spec.md`, merging PRs |
| Backend | **S1eevee**, joined by Luca once the watch app is done | `/backend`, `/tools` |
| Web | **NotKaemy** | `/web` (both views) |

## Coordination rules

1. Each person edits only their own folder. Shared decisions go in this file.
2. **Start every Claude Code session by reading `STATUS.md`**, then
   `git pull` and `git log --oneline -15`. Update your own section of
   `STATUS.md` whenever you merge or get blocked — it is the only place a cold
   session learns what the other two have been doing.
3. One branch per feature, small PRs, merge to `main` every 2-3 hours.
   **`main` must always run.**
4. Never edit `docs/api-spec.md` unless the owner asks.
5. This file holds stable decisions only — not progress. Progress lives in the
   team's plan doc checklist.
6. **`/presentation` is shared — everyone writes there** (the one exception to
   rule 1). If an idea belongs in the pitch rather than the code — a framing, a
   number worth quoting, a demo beat — append it to `presentation/ideas.md`
   straight away, in the same session it came up. Ideas left in a Claude Code
   conversation are lost when it's cleared.
