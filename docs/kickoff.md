# KICKOFF — Astronaut Health Monitor (NASA Space Apps 2026)

You are Claude Code, setting up the team repo for a 3-person hackathon project.
Read this whole file before doing anything. It is the single source of truth for
the setup. Work in two phases (below) and stop at each checkpoint marked STOP.

---

## 1. Project in one paragraph

NASA Space Apps Challenge 2026, challenge "Create Health Monitoring Software for
Astronauts on Space Missions". Hackathon: Sat 14 – Sun 15 Nov 2026. We build a
health monitor that compares each astronaut's vitals to **their own personal
baseline** and flags named "condition profiles" (decision support only, never a
diagnosis). The **astronaut is the primary user**: on a Mars mission the ground
is up to ~22 min away one way, so the astronaut is the first responder
(NASA's "Earth-independent medical operations"). Three parts share one API:

- **Watch app** (`/watch-app`): native SwiftUI, standalone watchOS app, no
  iPhone companion. Shows the astronaut's own vitals + alert banners.
  **There is no physical watch** — all watch data comes from the watchOS
  Simulator via `SimulatedSource`.
- **Backend** (`/backend`): Python **FastAPI** (locked). Vitals store,
  personal baseline, condition engine, Claude insight service, SSE streams.
- **Web app** (`/web`): plain HTML/CSS/JS, **no build step**, Chart.js via CDN.
  Two views: **Self-check** (astronaut, on a station tablet; clickable body
  figure) and **Ground** (flight surgeon; whole crew, delayed by light-time).

## 2. Locked decisions

- Data flow: Watch → `POST /astronauts/{id}/ingest` every ~3 s → backend updates
  baseline → checks condition profiles → on a NEW match, calls the Claude insight
  service → pushes to the web app over **Server-Sent Events** (SSE, not polling,
  not WebSockets).
- Only heart rate comes from the watch. Blood pressure, SpO2, temperature,
  respiratory rate, sleep and mood are **simulated server-side**, driven by a
  per-astronaut scenario state (e.g. "fever" raises temp AND heart rate together).
- **Baseline window:** mission days ~7–14 (early days are distorted by space
  adaptation / fluid shift), tagged with the environment's gravity
  (0 g ISS, 1/6 g Moon, 3/8 g Mars). For the demo, a `--seed-baseline` option
  fills this history instantly.
- **Comms delay:** mission environment ISS (0 s), Moon (~1.3 s one way),
  Mars (3–22 min one way, configurable). The Ground SSE view is delayed by the
  one-way light time through a queue; the Self-check view and the watch are not.
  Each condition has `act_within_s`. If round-trip time > `act_within_s`,
  the alert says "Act on board now" + the protocol; otherwise
  "Ground will see this in X min".
- **Radiation:** real NOAA GOES proton data from
  `https://services.swpc.noaa.gov/json/goes/primary/integral-protons-6-hour.json`.
  Event threshold: ≥10 MeV flux ≥ 10 pfu → "Shelter now" alert to the whole crew
  + running dose estimate. GOES measures near Earth: label it a stand-in for
  deep-space scenarios.
- **Watch alert banner:** condition name + severity colour + haptic + ONE
  pre-written action line from the condition profile (not Claude-generated).
  The long Claude explanation is shown on the web app only.
- **Claude insight service** (`backend/insight_service.py`): called only when a
  condition newly matches. Uses `client.messages.parse()` with a Pydantic model
  `Insight(why: str, trend: str, recommended_action: str)`.
  Model `claude-sonnet-5-5` (swap to `claude-haiku-5-5` for speed). Reads
  `ANTHROPIC_API_KEY` from the environment. **If the key is missing or the call
  fails, return a canned fallback Insight so the demo never breaks.**
- Watch "Simulate exertion" button (debug builds only) ramps heart rate so the
  presenter can trigger an alert live.
- Demo runs on ONE Mac: backend + watchOS Simulator + web app. The Simulator
  reaches the backend at `http://localhost:8000` (needs `NSAllowsLocalNetworking`
  in the watch app's Info.plist).

## 3. Condition profiles (thresholds are PLACEHOLDERS — tuned later)

| id | Profile | Signals vs. personal baseline (placeholder logic) | Hazard | act_within_s |
|---|---|---|---|---|
| `orthostatic` | Cardiovascular deconditioning | HR > baseline +25% AND systolic < baseline −15% | gravity | 600 |
| `fever` | Fever / possible infection | temp > baseline +1.0 °C AND HR > baseline +15% | environment | 3600 |
| `co2` | CO2 exposure | resp rate > baseline +30% AND HR up AND cabin CO2 (simulated) high OR headache reported | environment | 900 |
| `sleep_debt` | Sleep debt / behavioural strain | < 6 h sleep 3 nights running AND mood ≤ 2/5 AND resting HR up | isolation | 86400 |
| `spe` | Solar particle event | NOAA ≥10 MeV flux ≥ 10 pfu (external) | radiation | 300 |

Severity levels: `watch` (yellow), `alert` (orange), `critical` (red).
Each profile also stores: `onboard_action` (one line for the watch) and
`body_region` (for the body figure: heart, head, lungs, skin, whole_body).

## 4. API contract → write this into `docs/api-spec.md`

Base URL (dev): `http://localhost:8000`. Auth: none (local hackathon demo).
Crew ids: `a1`–`a4`. All timestamps ISO 8601 UTC.

- `GET /crew` → `[{id, name, role, status: "nominal"|"watch"|"alert"|"critical"}]`
- `POST /astronauts/{id}/ingest` ← `{timestamp, heart_rate_bpm, source: "real"|"simulated"}` → `202 {accepted: true}`
- `GET /astronauts/{id}/vitals` → latest snapshot:
  `{timestamp, heart_rate_bpm, systolic_mmhg, diastolic_mmhg, spo2_pct, temp_c, resp_rate_bpm, sleep_h_last_night, mood_1to5, source, baseline: {…same fields…}}`
- `GET /astronauts/{id}/stream?view=crew|ground` → SSE. Events: `vitals` (snapshot), `alert` (alert object).
  `view=ground` is delayed by the mission's one-way light time.
- `GET /astronauts/{id}/alerts` → `[Alert]`
- **Alert object:** `{id, astronaut_id, profile, severity, hazard: "radiation"|"isolation"|"distance"|"gravity"|"environment", body_region, started_at, onboard_action, act_within_s, ground_eta_s, insight: {why, trend, recommended_action} | null}`
- `GET /mission` → `{environment: "iss"|"moon"|"mars", one_way_delay_s}`; `PUT /mission` ← same shape
- `GET /space-weather` → `{flux_10mev_pfu, observed_at, event_active, source_url}`
- `POST /astronauts/{id}/checkin` ← `{timestamp, mood_1to5?, sleep_h?, symptoms?: [str], vision?: {amsler_distortion: bool, acuity_line: int}, share_with_ground: bool}`
- `POST /debug/scenario` ← `{astronaut_id, scenario: "fever"|"co2"|"orthostatic"|"sleep_debt"|"spe"|"clear"}` (dev only, for the demo)

Rule: **only the API-spec owner (Luca) edits `docs/api-spec.md`**, via a PR the team sees.

## 5. Team lanes

| Lane | Owner | Owns |
|---|---|---|
| Watch + API spec + integration | Luca (has the Mac) | `/watch-app`, `docs/api-spec.md`, merging PRs |
| Backend | TBD | `/backend`, `/tools` |
| Web | TBD | `/web` |

Coordination rules (put these in the root CLAUDE.md):
1. Each person edits only their own folder. Shared decisions go in the root `CLAUDE.md`.
2. Run `git pull` before every Claude Code session.
3. One branch per feature, small PRs, merge to `main` every 2–3 hours. `main` must always run.
4. Never edit `docs/api-spec.md` unless the owner asks.
5. Root `CLAUDE.md` holds stable decisions only — not progress. Progress lives in the team's plan doc checklist.

---

## PHASE 1 — tonight (repo + docs, no feature code)

1. **Check prerequisites:** `git --version`, `gh auth status`,
   `python3 --version`, `xcodebuild -version`. You may install anything missing
   yourself with Homebrew (`brew install …`, no sudo needed). Ask Luca before any
   command that needs `sudo`, and never run `rm -rf` outside this repo. If `gh`
   isn't logged in, ask Luca to run `gh auth login` himself (it's interactive).
2. **Create the GitHub repo** `astronaut-health-monitor` as **private** with
   `gh repo create`, and set it up in the current folder. (It becomes public at
   submission — ask before changing visibility.)
3. **Create this structure:**
   ```
   /watch-app/            (.gitkeep for now — Xcode project comes in step 7)
   /backend/              CLAUDE.md, requirements.txt, .env.example
   /web/                  CLAUDE.md
   /tools/                (.gitkeep)
   /docs/api-spec.md      (from section 4)
   /docs/kickoff.md       (move THIS file here)
   CLAUDE.md  README.md  .gitignore
   ```
4. **Root `CLAUDE.md`:** short (under ~80 lines). Project paragraph, locked
   decisions (section 2), condition profiles (section 3), lanes + coordination
   rules (section 5), and "the API contract is `docs/api-spec.md`". Stable facts
   only.
5. **Lane `CLAUDE.md` files** (`backend/`, `web/`, later `watch-app/`): stack,
   how to run it, and lane-specific conventions. Each is edited only by its owner.
6. **`.gitignore`:** Python (venv, `__pycache__`), `.env`, macOS (`.DS_Store`),
   Xcode (`xcuserdata/`, `DerivedData/`, `*.xcuserstate`).
   **`.env` must never be committed.** `backend/.env.example` contains
   `ANTHROPIC_API_KEY=` (empty).
7. **Watch project:** do NOT hand-write or edit `.pbxproj` files. STOP and ask
   Luca to create it in Xcode: File → New → Project → watchOS → App,
   "Watch-only App", product name `AstronautHealthMonitor`, interface SwiftUI,
   saved inside `/watch-app`. (Xcode 16+ uses synchronized folders, so Swift
   files added to the app folder later are picked up automatically.)
8. **README.md:** what the project is, the three parts, how to run each (backend:
   venv + `uvicorn main:app --reload`; web: open `web/index.html`; watch: open
   the Xcode project, run on the watchOS Simulator).
9. Commit ("Initial repo setup") and push to `main`. Ask Luca for the two
   teammates' GitHub usernames and add them as collaborators with
   `gh api -X PUT repos/{owner}/astronaut-health-monitor/collaborators/{username}`.

**STOP. Show Luca the tree, the root CLAUDE.md and the repo URL.**

## PHASE 2 — at hackathon kickoff (scaffolding, mock first)

Only start when Luca says so (the event's rules may require code to be written
during the hackathon).

1. **Backend mock (first hour):** FastAPI app in `backend/main.py` with EVERY
   endpoint from section 4 returning realistic canned data, including a working
   SSE stream that emits a `vitals` event every 3 s and a fake `alert` every ~60 s.
   CORS open for local dev. This lets Watch and Web build immediately.
2. **`backend/insight_service.py`** as specified in section 2, with the fallback.
3. **`tools/simulate_crew.py`:** posts heart rate for `a2`–`a4` every 3 s with
   scripted scenarios (`--scenario fever --at 60s`), `--seed-baseline`, and a
   deterministic random seed so the demo plays the same every time.
4. **Watch sources** (inside the Xcode app folder): `VitalsSource` protocol;
   `SimulatedSource` (random walk around ~65 bpm + "Simulate exertion" ramp);
   `HealthKitSource` as a stub with a TODO; `APIClient` posting to
   `/astronauts/a1/ingest`; a `ContentView` showing live HR. Add
   `NSAllowsLocalNetworking` to the app's Info settings.
5. **Web placeholder:** `web/index.html` that connects to
   `/astronauts/a1/stream?view=crew` and prints events. Real UI comes later.
6. Run the backend and `curl` each endpoint. Report results. Commit on a branch
   `scaffold`, open a PR.

**STOP. Report what runs and what doesn't.**
