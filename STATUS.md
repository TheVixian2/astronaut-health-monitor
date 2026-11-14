# STATUS

**Edit only your own lane's section.** That way three people writing to this file
almost never conflict — git merges separate regions cleanly.

**Start every Claude Code session by reading this file**, then run:

```sh
git pull
git log --oneline -15
```

Update your section whenever you merge to `main`, or when you get blocked.

---

## Contract changes — read first

Anything that changed in `docs/api-spec.md`, newest at the top.
**Only Luca writes here.** If you need a change, ask — don't edit the spec.

- **2026-11-14 — `docs/api-spec.md` IS STALE. Do not build from it yet.**
  It still describes the pre-pivot project: five condition profiles, crew
  `a1`-`a4`, the NOAA `/space-weather` endpoint, and no SANS. Agreed since:
  SANS becomes the centrepiece (risk score from vision trend + cabin CO2 +
  headache + mission day), `orthostatic` stays, `spe`/`sleep_debt`/`fever` are
  cut candidates, and a behavioural check-in flow is added
  (PHQ-2 -> AI summary -> astronaut reviews -> `share_with_ground` -> transmit).
  See `docs/monitored-signals.md` for the full signal list and
  `presentation/ideas.md` for the reasoning. **Luca owns this edit.**

---

## Watch — Luca

Branch: `watch`

- **Working:** Xcode project created (Watch-only, watchOS 27.2), builds clean.
- **Next:** `VitalsSource` / `SimulatedSource` / `APIClient` / `ContentView`.
- **Blocked on:** nothing.

## Backend — stefanalbu2010-byte (+ Luca later)

Branch: `backend`

- **PHASE 2 IS GO (Luca, 2026-11-14).** Start with step 1 only.
- **Build now — the mock (`backend/main.py`):** every endpoint from
  `docs/api-spec.md` returning realistic canned data, CORS open for local dev,
  and a working SSE stream on `/astronauts/{id}/stream` emitting a `vitals`
  event every 3 s and a fake `alert` every ~60 s. Both other lanes are blocked
  until this runs, so ship it before anything else.
- **Two things to skip** — the spec is mid-pivot (see Contract changes above):
  - **Skip `/space-weather`** entirely. The `spe` profile is being cut.
  - **Stub `/debug/scenario`** but don't wire real scenarios yet — the enum
    is changing.
  Every other endpoint's *shape* is stable, so build them as written.
- **After the mock:** `insight_service.py` (with the canned fallback — it must
  never raise into the request path), then `tools/simulate_crew.py`
  (`--seed-baseline` + deterministic seed; the crew wander near their own
  distinct baselines via random walk with mean reversion — see
  `docs/monitored-signals.md` §2).
- **Do NOT build the condition engine from `docs/api-spec.md` yet** — the five
  profiles there are pre-pivot. `docs/monitored-signals.md` §6 has the current
  intent. Ask Luca before implementing conditions.
- **Blocked on:** nothing for step 1.

## Web — NotKaemy

Branch: `web`

- **Working:** nothing yet — Phase 2 not started.
- **Next:** `index.html` connecting to `/astronauts/a1/stream?view=crew` and
  printing events. Real UI after the mock backend is up.
- **Blocked on:** backend mock (can start against canned JSON meanwhile).
