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

- **2026-11-14 — `GET /mission` adds `real_one_way_delay_s`. Verdict decided.**
  Resolves NotKaemy's "demo verdict contradicts the rule" question (option a).
  The verdict now uses the **real** light time: `2 × real_one_way_delay_s >
  act_within_s` → "Act on board now". `one_way_delay_s` stays 20 s and only
  sets how long the Ground stream waits. Mars default: `20` / `1320`.
  Result: `orthostatic`, `co2` → act on board; `fever`, `sans` → ground.
  Field is optional on `PUT` (defaults to `one_way_delay_s`). Already done on
  `main` in `backend/main.py`, `web/common.js`, `web/mock.js` — **pull `main`
  into your lane branch before your next commit.**
  - **@NotKaemy:** nothing to build; `verdict()` in `common.js` handles it and
    the Ground view picks it up. You can drop the "please decide" item.
  - **@stefanalbu2010-byte:** when you wire `insight_service.generate_insight()`
    into `main.py`, pass `mission.real_one_way_delay_s`, not `one_way_delay_s`.

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

- **Working:** Phase 2 step 4 done on branch `watch`. `VitalsSource`,
  `SimulatedSource` (random walk + exertion ramp), `HealthKitSource` stub,
  `APIClient` (POST ingest + poll `/alerts`), `MonitorModel`, `ContentView`
  with HR readout and alert banner. Builds and runs on the watchOS 27.2
  Simulator; HR updates live; degrades to "offline" with no backend.
- **Design note for the backend lane:** the watch **polls `GET
  /astronauts/a1/alerts` every 3 s** rather than holding an SSE connection —
  much less code on watchOS. The mock needs `/alerts` to return a JSON array
  (`[]` is fine). Haptic fires only when the newest alert `id` changes.
- **Next:** `NSAllowsLocalNetworking` (see below), then verify against the real
  mock once the backend is up.
- **Blocked on:** backend mock, to confirm ingest actually lands.
- **ATS / `NSAllowsLocalNetworking` is NOT needed — verified 2026-11-14.**
  Previously flagged here as a required Xcode setting. It isn't: the watch app
  reached `http://localhost:8000` from the watchOS 27.2 Simulator with no ATS
  exception at all (17/17 ingest POSTs returned 202, 17/17 alert polls 200).
  Don't spend time on it.

## Backend — stefanalbu2010-byte (+ Luca later)

Branch: `backend`

- **Done — mock is up (`backend/main.py`, branch `backend`, ready to merge).**
  Every spec endpoint except `/space-weather` (skipped as asked), pydantic
  models, CORS open. Run: `cd backend`, activate the venv, `uvicorn main:app --reload`
  → `http://localhost:8000/docs`. Smoke-tested every endpoint and both SSE views.
  - Vitals: random walk with mean reversion around a **different baseline per
    astronaut** (`a1` ~58 bpm ... `a2` ~74). `POST /ingest` HR overrides the
    simulated HR (and its `source`) for 10 s.
  - SSE: `vitals` every 3 s; a fake `alert` on `a1` every 60 s (cycles fever,
    co2, orthostatic, sleep_debt, sans). Set `MOCK_AUTO_ALERT_S=10` for faster
    testing, `0` to turn it off.
  - **Web, note:** an alert is sent with `insight: null`, then **re-sent ~2 s
    later with the same `id`** and `insight` filled in. Update by `id`.
  - `view=ground` is delayed by `one_way_delay_s`. **Default mission is
    `mars` / 20 s** (demo-compressed). Change it with `PUT /mission`.
  - `/debug/scenario` is a stub (any string, 202, does nothing).
  - `/checkin` returns `202 {"accepted": true}`. The spec gives no response shape.
- **Luca, please confirm in the spec:** (1) insight delivered by re-sending the
  alert event with the same id, (2) the `/checkin` and `/debug/scenario` responses.
- **Done — `backend/insight_service.py`:** `generate_insight(profile, vitals, baseline, ...)`
  calls `claude-sonnet-5-5` via `messages.parse()` and returns `Insight(why, trend,
  recommended_action)`. It never raises: no key, timeout, API error or refusal all
  return the fallback. Tested the no-key and bad-key paths; **not yet tested with a
  real key** (none on this machine). Profile-agnostic, so it works for any post-pivot
  condition. Not wired into `main.py` yet — the mock's fake alerts keep canned text
  until the condition engine exists.
- **Next:** `tools/simulate_crew.py`. Not building the condition engine until the
  post-pivot spec lands. **Note for the spec:** `sans` builds up over days, so
  `orthostatic` is the only condition that can be triggered live in the demo.
- **Blocked on:** nothing.

## Presentation — dbm711

Branch: **none — works on `main`** (`presentation/` is a shared path, rule 3b)

- **Working:** `presentation/ideas.md` is seeded with the SANS framing and
  sources, the demo choreography, the behavioural-health argument and the NASA
  data gap. `demo-script.md` has the 90-second run.
- **Next:** turn `ideas.md` into actual slides; chase the TODO about the Space
  Apps challenge page's own suggested-resources list.
- **Blocked on:** nothing. Scope is still settling, so expect the content to move.

## Web — NotKaemy

Branch: `web`

- **Done — Self-check view (merged to `main`):** `web/self-check.html`. Alert
  banner with the verdict + one-line `onboard_action` + insight behind a
  toggle; clickable body figure (regions take their alert's severity colour);
  vitals tiles vs baseline; Chart.js trend with baseline dashed; check-in form
  matching `POST /checkin` (`share_with_ground` **off by default**); session
  alert history. `web/index.html` is now a landing page; the old placeholder
  is `web/stream-check.html` (raw SSE debug). Verdict rule lives only in
  `web/common.js`.
- **Run without a backend:** add `?mock` to any page (`web/mock.js` mirrors the
  backend mock). **Tested in mock mode only — not yet against the real
  backend** (no Python on my machine). Luca, if you run the backend, opening
  `web/index.html` -> Self-check is a quick end-to-end check.
- **Check-in uses the current spec fields.** The PHQ-2 -> AI summary ->
  review -> transmit flow waits for the post-pivot spec.
- **Luca, please decide — the demo verdict contradicts the rule.** CLAUDE.md:
  "round trip > `act_within_s` -> Act on board now". With the demo-compressed
  20 s one-way delay, round trip is 40 s, far under `orthostatic`'s 600 s, so
  the page says **"Ground will see this in 20 s"** — but `demo-script.md` step 3
  needs **"Act on board now"**. Options: (a) compute the verdict from the
  *real* environment delay (Mars 22 min) and compress only the delivery
  countdown, e.g. a new `verdict_delay_s` or `real_one_way_delay_s` in
  `GET /mission`; (b) demo with a delay over 300 s. Web currently follows the
  rule as written; (a) is a one-line change here once the field exists.
- **Next:** Ground view — whole crew, `view=ground`, incoming-alert countdown,
  real Mars delay always shown in the header.
- **Blocked on:** nothing.
