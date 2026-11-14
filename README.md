# Astronaut Health Monitor

NASA Space Apps Challenge 2026 — *Create Health Monitoring Software for
Astronauts on Space Missions*.

**Live demo (no login, no install):** https://thevixian2.github.io/astronaut-health-monitor/
— the web app with simulated live streams and data recorded from a real backend run
(`tools/snapshot_mock.py`). Run it locally for the full live system.
Update it after changing `/web`:
`git push origin $(git subtree split --prefix web main):refs/heads/gh-pages --force`

**Dr. Galactic** watches the **behavioral (mental) health** of a crew of four on
a long Mars mission. It compares each astronaut's signals (heart rate, sleep,
mood, a validated two-question depression screen, a reaction-time test) to
**their own personal baseline**, not to population averages. Decision support
only: it never issues a diagnosis.

On Mars, Mission Control is up to 22 minutes away one way, so help has to start
on board. A flag goes to the **commander** first, who decides when to tell the
astronaut; if the commander is the one flagged, it goes to the deputy.
Mission Control receives it after the light delay.

## The three parts

| Part | Folder | Stack |
|---|---|---|
| **Watch app** | `/watch-app` | Native SwiftUI, standalone watchOS app, no iPhone companion. Shows the wearer's vitals and alert banners. |
| **Backend** | `/backend` | Python FastAPI. Vitals store, personal baseline, condition engine, Claude insight service, SSE streams. |
| **Web app** | `/web` | Plain HTML/CSS/JS, no build step, Chart.js via CDN. A Self-check view for the astronaut and a light-time-delayed Ground view for Mission Control. |

Only heart rate is real (from the watchOS Simulator — there is no physical
watch). The other vitals are simulated server-side from a per-astronaut scenario
so they move together coherently.

## What it monitors

**Behavioral health** of a crew of four on a long Mars mission: a wellbeing level
per astronaut built from PHQ-2, mood, sleep and body clock, a 3-minute reaction
test and resting heart rate, each against the astronaut's own baseline, plus a
`sleep_debt` alert. Each flag maps to a NASA spaceflight hazard and Human Research
Program risk.

Thresholds are placeholders pending tuning — see `CLAUDE.md`.

## Getting set up (NotKaemy, stefanalbu2010-byte)

Three one-time things you have to do yourself:

1. Install **Claude Code** and sign in.
2. Accept the **collaborator invite** for this repo (check your GitHub email).
3. Authenticate git: `gh auth login`.

Then paste this one line, swapping `backend` for your lane
(`backend` = stefanalbu2010-byte, `web` = NotKaemy, `watch` = Luca):

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

## Use of AI (Super Intelligence, SI)

Disclosed as the NASA Space Apps submission guide requires for code and data.

- **The idea and the design decisions are the team's.** The focus on behavioral
  health, commander-first release, the hygiene privacy rule (Mission Control
  sees who, the commander sees hours only) and "proven signals only" were decided
  by the team. AI did not come up with the solution.
- **Code: written with AI assistance.** The team used **Claude Code**
  (Anthropic; models Claude Opus 5 and Opus 5.5) to write and edit the backend,
  web app and watch app, from our instructions, and we reviewed and ran the
  result. Commits made through Claude Code carry a `Co-Authored-By: Claude`
  line, and every source file has a header comment saying it was written with AI assistance.
- **Research and docs.** Claude helped search for and summarize studies and NASA
  sources and draft the docs in `docs/`. Each cited source was checked against the
  original paper or NASA page; they are listed with links in `docs/nasa-data.md` and on the Data sources page.
- **AI inside the app (runtime).** The backend calls Claude (`claude-sonnet-5-5`
  by default, `backend/insight_service.py`) for two things only: the plain-language
  explanation of an alert raised from physical readings, and the watch's *Ask*
  and *Why?* answers. It only ever sends physical readings; **psychological data is never sent to a
  cloud model**. Every Claude answer is labelled **"AI-generated (Claude)"** on
  screen. Without an API key, during a communications blackout, or if Claude is
  unreachable, the app uses fixed on-board text instead, labelled "On board".
- **No AI-generated images, video or audio** are in the app or repo. Screenshots
  are of the running app.

## Docs

- `CLAUDE.md` — locked decisions, condition profiles, team lanes, coordination rules.
- `docs/api-spec.md` — **the API contract.** The single source of truth.
- `docs/kickoff.md` — the original project brief.
