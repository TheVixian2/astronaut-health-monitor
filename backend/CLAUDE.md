# backend — CLAUDE.md

**Owner: stefanalbu2010-byte**, joined by Luca once the watch app is done. Only the backend owner edits this folder.

## Stack

Python 3 + **FastAPI** (locked). `uvicorn` to serve, `httpx` for JPL Horizons,
`pydantic` for every request/response model, `anthropic` for the insight service,
**SQLite** (`sqlite3`, stdlib) for history. No other database.

## Run it

```sh
python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                 # optional: ANTHROPIC_API_KEY; without it the built-in explanations are used
python ../tools/simulate_crew.py --reset-db --seed-baseline   # six weeks of history; do this before every demo
uvicorn main:app --reload
```

Serves on `http://localhost:8000` (`/docs` lists every endpoint). CORS stays open
for local dev: the web app is opened as a `file://` page and the watchOS
Simulator talks to `localhost`.

Env vars: `AHM_DB` (database path, default `data/ahm.db`), `AHM_LIVE_LIGHT_TIME=1`
(the verdict uses today's JPL Horizons Earth-Mars light time instead of 1320 s),
`AHM_MISSION_DAY` (mission day used only when the database has no mission start).

## Conventions

- **`docs/api-spec.md` is the contract.** Match it exactly. If something needs to
  change, ask Luca; don't change the shape unilaterally. New endpoints are marked
  PROVISIONAL in code until the spec has them.
- Every endpoint gets a pydantic model. No bare dicts in responses.
- **Everything is compared to the astronaut's own baseline**: the median of stored
  mission days 7-14. Never a population threshold.
- Vitals other than a1's heart rate are **simulated server-side**, shifted together
  by a scenario (`sleep_debt`, `strain`). Scenario shifts live in `engine.py`.
- The condition engine fires an alert only on a **new** match and clears it after
  5 calm ticks. That gate is what limits Claude calls; insights are cached in SQLite.
- `insight_service.py` must **never** raise into the request path. No key or a failed
  call returns the fallback, which `engine.fallback_insight()` builds from the real
  numbers and the verdict.
- Verdict: **always `real_one_way_delay_s`**, never the compressed demo delay.
- Database writes go through the background writer (`store.py`); never block the
  request path or the tick loop on disk.
- Wording shown to the astronaut suggests, never orders, and never diagnoses.
  Check-ins and circadian data the astronaut hasn't shared stay out of the ground view.

## Layout

- `main.py` — FastAPI app, state, tick loop, alert gate, endpoints.
- `engine.py` — crew baselines, the `sleep_debt` profile, thresholds,
  scenario shifts, "do you feel this?" questions, on-board protocols, fallback
  explanations (blackout-aware).
- `behavioral.py` — **the team's main focus (2026-11-14):** wellbeing profile from PHQ-2,
  mood, sleep/body clock, reaction test and resting HR, each vs the astronaut's own baseline
  (PHQ-2 uses its validated cut-off). Astronaut first: nothing is shared until they choose;
  only "urgent" notifies the commander and ground automatically (level + areas, never answers).
  Crew-wide trends never name anyone and need >= 3 people.
- `quality.py` — sensor checks per reading: impossible values, spikes, stuck sensor,
  watch dropout. Sensor errors the astronaut reports are flagged `artifact`, never deleted.
- `store.py` — SQLite schema, background writer, reads (baseline, history, check-ins).
- `circadian.py` — lighting log and the circadian countermeasure loop.
- `horizons.py` — live Earth-Mars light time from NASA JPL Horizons.
- `insight_service.py` — the Claude call plus its fallback.
- `/tools` (sibling folder, same owner) — `simulate_crew.py` (`--reset-db`,
  `--seed-baseline`, `--run`).
