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

## Getting set up (NotKaemy, S1eevee)

Three one-time things you have to do yourself:

1. Install **Claude Code** and sign in.
2. Accept the **collaborator invite** for this repo (check your GitHub email).
3. Authenticate git: `gh auth login`.

Then paste this one line, swapping `backend` for your lane
(`backend` = S1eevee, `web` = NotKaemy, `watch` = Luca):

```sh
git clone https://github.com/TheVixian2/astronaut-health-monitor.git && cd astronaut-health-monitor && git checkout backend && claude
```

That clones, puts you on your branch, and starts Claude Code in the repo. Then
give it this as your first message:

> Read CLAUDE.md, STATUS.md and docs/api-spec.md, then tell me what my lane owns
> and what to build first.

It picks up the project rules, the current state of the other two lanes, and the
API contract on its own from there.

**Using VS Code?** Claude Code works there too — the extension, or just `claude`
in the integrated terminal. Two things: open the **repo folder itself**
(File -> Open Folder -> `astronaut-health-monitor`), not a parent folder or a
single file, or the lane `CLAUDE.md` won't load. And on the web lane, install
the **Live Server** extension to serve `web/index.html` over `http://localhost`
instead of `file://`.

**Push to your own branch only — never to `main`.** Luca merges every couple of
hours. The one exception is the shared files (`CLAUDE.md`, `STATUS.md`, `docs/`,
`presentation/`), which are edited on `main` directly — see coordination rule 3b.

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
