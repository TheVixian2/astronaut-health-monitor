# Astronaut Health Monitor

NASA Space Apps Challenge 2026 — *Create Health Monitoring Software for
Astronauts on Space Missions*.

A health monitor that compares each astronaut's vitals to **their own personal
baseline** rather than to population averages, and flags named condition
profiles. Decision support only — it never issues a diagnosis.

The astronaut is the primary user. On a Mars mission the ground is up to ~22
minutes away one way, so the crew member is the first responder. Every alert
answers the question "can this wait for Houston, or do I act now?" by comparing
the round-trip light time against the condition's own `act_within_s`.

## The three parts

| Part | Folder | Stack |
|---|---|---|
| **Watch app** | `/watch-app` | Native SwiftUI, standalone watchOS app, no iPhone companion. Shows the wearer's vitals and alert banners. |
| **Backend** | `/backend` | Python FastAPI. Vitals store, personal baseline, condition engine, Claude insight service, SSE streams. |
| **Web app** | `/web` | Plain HTML/CSS/JS, no build step, Chart.js via CDN. A Self-check view for the astronaut and a light-time-delayed Ground view for the flight surgeon. |

Only heart rate is real (from the watchOS Simulator — there is no physical
watch). The other vitals are simulated server-side from a per-astronaut scenario
so they move together coherently. Radiation uses live NOAA GOES proton data.

## Condition profiles

Cardiovascular deconditioning, fever / possible infection, CO2 exposure, sleep
debt / behavioural strain, and solar particle events. Each one maps to a space
hazard (gravity, environment, isolation, radiation, distance), a body region, a
severity, and one pre-written on-board action line.

Thresholds are placeholders pending tuning — see `CLAUDE.md`.

## Running it

All three run on one Mac. **Start the backend first.**

**Backend** — `http://localhost:8000`:
```sh
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env     # paste your ANTHROPIC_API_KEY into .env
uvicorn main:app --reload
```
The insight service falls back to canned text if the key is missing, so the demo
still runs without one.

**Web** — open `web/index.html` in a browser. If `file://` gives you trouble,
`python3 -m http.server 5500` from `web/` and visit `http://localhost:5500`.

**Watch** — open the Xcode project in `watch-app/` and run it on the **watchOS
Simulator**. Requires Xcode 16+. The Simulator reaches the backend over
`localhost`, which needs `NSAllowsLocalNetworking` in the app's Info settings.

Optionally, `tools/simulate_crew.py` drives the other three crew members and can
seed baseline history (`--seed-baseline`) for an instant demo.

## Docs

- `CLAUDE.md` — locked decisions, condition profiles, team lanes, coordination rules.
- `docs/api-spec.md` — **the API contract.** The single source of truth.
- `docs/kickoff.md` — the original project brief.
