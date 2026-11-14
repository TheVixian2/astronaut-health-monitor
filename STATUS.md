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

- **2026-11-14 (evening) — PIVOT DONE: mental health. Read this before your next commit.**
  Plan: Luca has it (6 workstreams). Deadline **Sun 15 Nov 23:59 Bucharest**.
  - **Removed on `main`:** profiles `orthostatic`, `fever`, `co2`, `sans` (+ `GET /sans`),
    cabin CO2, **blood pressure** (`systolic_mmhg`/`diastolic_mmhg` no longer in vitals),
    check-in `vision`. Scenarios now `sleep_debt | strain | clear` (others → 422). Old
    code is in tag `pre-mental-health-pivot`. **Pull `main` into your lane first.**
  - **Decisions (Luca):** (1) **Commander first, then released** — psych flags go to the
    commander, who releases them to the astronaut; if the commander is flagged → the
    deputy (pilot); ground always, after light delay. This replaces "astronaut sees
    nothing": the official challenge says astronauts must be able to *evaluate and act on
    their own health*, so nothing stays hidden for good. (2) **Stress score driven by
    the watch**: HRV, resting HR, sleep, activity = 60-80 % of the score; PHQ-2, mood,
    reaction test the rest. (3) **Flight surgeon stays** — the challenge text names them.
    (4) Ship's doctor page stays. Shapes in `docs/api-spec.md` → "Decided, NOT built yet".
  - **@stefanalbu2010-byte:** release endpoint + deputy routing; `/ingest` accepts
    `hrv_sdnn_ms`, `active_min`; simulator + seed add HRV/activity (a2 drifts down after
    the midpoint); `behavioral.py` adds `hrv` and `activity` signals with the 60-80 % weight.
  - **@NotKaemy:** remove BP from `common.js` (VITALS), `mock.js`, `ground.js` (SYS
    column) and the removed profiles from `HAZARDS`/`HRP_RISKS`/`meds.js`; bring back
    "Tell them now" on the Commander page and show **released** warnings + guidance on
    Self-check; add per-indicator "what / why it matters in space" lines and a
    "check-in due" prompt (the challenge suggests both). For GitHub Pages: `?mock` must
    skip the login and `mock.js` must serve the wellbeing/notice shapes.
  - **@dbm711 — submission rules (official guide):** demo = **max 7 slides** incl. title
    (or a 30 s video) — over the limit = not eligible for global judging; the 90 s
    `demo-script.md` is for local judging only. Links must be public, no login. Must list
    ≥1 NASA resource and every reference. AI use must be disclosed. No photos of anyone
    under 18. Suggested 7 slides: title/team/challenge · problem · solution + user flow ·
    how it works · NASA data & research · demo screenshots · future + ethics.

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

- **2026-11-14 — `docs/api-spec.md` IS NOW CURRENT. Build from it.**
  Reconciled against the running backend and cross-checked: every live endpoint
  is documented, nothing documented is missing. Covers the post-pivot scope —
  `spe` cut (and `/space-weather` with it), `sans` added, the two-delay verdict
  rule, and the circadian endpoints marked **PROVISIONAL**. The earlier "do not
  build from the spec" warning is lifted.

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
- **Done: circadian rhythm from the on-board lighting log (`backend/circadian.py`,
  branch `backend`). This is the mentor/judge suggestion.** We read the ISS lighting
  system (SSLA modes: general 4500K, pre-sleep 2700K, phase-shift 6500K) instead of
  asking the astronaut. 7 nights of simulated log per astronaut with different
  habits. **Only `a2` is irregular** (bedtime spread ~2 h, bright light before sleep
  on 4 of 7 nights), so that's the demo story. `sleep_h_last_night` in vitals now
  comes from this log.
  - **Ethics, built in:** shared with ground by default (NotKaemy's decision; the
    ground view gets **403** once the astronaut opts out), suggestive wording only (tested: no "must", no
    diagnosis), the app **never changes the lights itself**, no comparison between
    crew, and it doesn't touch crew status or alerts.
  - **Luca, proposed for the spec (already working, provisional):**
    `GET /astronauts/{id}/circadian?view=crew|ground` returns `{share_with_ground,
    lighting{mode,cct_k,since}, nights[7]{night_of,bedtime,wake_time,sleep_h,
    pre_sleep_lighting_min,bright_light_last_hour}, summary{status,nights,
    bedtime_spread_min,nights_bright_before_sleep}, card|null,
    recommendation{text,source,source_url}, evidence{...}}`.
    `PUT /astronauts/{id}/circadian/sharing {share_with_ground}`.
    `PUT /astronauts/{id}/lighting {mode}` records the crew switching the mode.
  - **NotKaemy, for Self-check:** show `card` when not null, `recommendation.text`
    with its source link, a lighting chip ("Pre-sleep · 2700K"), a "share with
    ground" toggle (off by default), and optionally a 7-night bedtime chart from
    `nights`. In the Ground view, a 403 should read "Kept private by the astronaut".
- **Done: circadian is now a full countermeasure loop (branch `backend`).**
  Following the judge's "light simulation must be closer to Earth" point and the
  team's wish to make circadian a big part of the project:
  **detect drift → suggest a lighting plan → verify sleep improved.**
  - **Detect:** body-clock drift in min/night. `a2` drifts ~15 min later each night,
    bedtime spread ~1.7 h, and bright light before sleep on 4 of 7 nights.
  - **Suggest:** `plan` built from the three ISS SSLA modes (morning phase-shift
    6500K → day general 4500K → pre-sleep 2700K → dark). It stays fixed once accepted.
  - **Verify:** `verification` compares before/after, e.g. *"bedtime varied by 0.2 h
    (was 1.7 h), slept 7.1 h (was 6.3 h)"*; `summary.status` becomes `improving`.
  - `environment_note` per mission (ISS 16 sunrises/day; Moon 29.5-day lunar day;
    Mars: no day/night at all, so the lighting is the only cue).
  - **New, provisional (Luca, for the spec):** `PUT /astronauts/{id}/circadian/plan
    {accepted}` is the astronaut's own choice. `POST /debug/circadian {astronaut_id,
    action: advance|reset, nights 1-14}` fast-forwards nights for the demo. `GET
    /circadian` gains `environment_note`, `plan`, `verification`, and
    `summary.drift_min_per_night / sleep_avg_h / target_bedtime`; `status` adds
    `improving`. Existing fields are unchanged.
  - **NotKaemy:** show the plan as a timeline of coloured bars by mode, with an
    "I'd like to try this plan" button (calls `PUT .../plan`) and the verification
    message when present. Demo button: `POST /debug/circadian` advance 4 nights.
  - **Demo beat (~20 s):** `a2` card → accept plan → fast-forward 4 nights → "your
    bedtime varied by 0.2 h, was 1.7 h". The close-the-loop moment.
  - **Persistence note:** the lighting log lives in memory for now. It moves to
    SQLite with the persistence task below.
- **Done: persistence + the real condition engine + SANS (branch `backend`, ready to merge).**
  Luca's persistence task and the `sans` demo problem are both solved.
  - **SQLite** at `backend/data/ahm.db` (gitignored), written by a background thread
    so a disk write never blocks a request or the tick loop. Stores every tick,
    alerts (with the insight cached), check-ins, and the mission start.
  - **Baseline = median of stored mission days 7-14.** It's a real `SELECT` now; it
    falls back to the configured values only if nothing has been seeded.
  - **Condition engine for all five spec profiles** (`orthostatic`, `co2`, `fever`,
    `sleep_debt`, `sans`). It fires only on a NEW match, clears after 5 calm ticks
    (~15 s), and the gate survives a restart (tested: no duplicate alerts).
  - **SANS risk score 0-100** from mission day, acuity vs the day 7-14 baseline,
    Amsler distortion, headaches (7 d) and cabin CO2 (7 d). Trigger 50, clear 40.
  - **`/debug/scenario` is wired** (enum from the spec; `spe` gets 422). Vitals
    shift together and alerts fire in ~20-40 s. `sans` injects a check-in through
    the same path as a real one. `clear` resets the astronaut and drops live
    check-ins so the SANS demo can run again.
  - **Explanations without an API key:** the fallback is built from the real
    numbers plus the verdict, e.g. *"Heart rate 93 bpm vs your baseline 73 (+27%);
    systolic 103 vs 124 (-17%) … a reply takes about 44 min … so the on-board step
    comes first."* `fever`/`sans` say *"This can wait for the flight surgeon"*.
  - **Removed the fake auto-alert every 60 s.** To test alerts, use
    `/debug/scenario` or `tools/simulate_crew.py --run --scenario a2:orthostatic:5`.
- **Demo prep (run before every rehearsal):** from the repo root,
  `backend/.venv/bin/python tools/simulate_crew.py --reset-db --seed-baseline`
  (Windows: `backend\.venv\Scripts\python ...`), then start uvicorn. That gives six
  weeks of history; **a1's SANS score sits at 40/50**, and one check-in with a
  headache plus Amsler distortion takes it to ~73 and fires `sans`.
- **@Luca, three things to know:**
  1. **Watch bug: `MonitorModel.swift` line 52 takes `api.alerts().last` as the
     newest alert, but `/alerts` returns newest FIRST** (backend and `web/mock.js`
     both). With 2+ alerts the watch shows the oldest one and the haptic stops
     firing. One-word fix: `.first`.
  2. **`orthostatic` on a1 with the real watch:** watch HR overrides the simulated
     HR, so the alert needs the watch's HR up (Simulate exertion) **and** the
     systolic drop, which comes from `/debug/scenario orthostatic`. Either press
     both, or stop the watch and the scenario alone fires it.
  3. **`ground_eta_s` now = `real_one_way_delay_s`** (1320), matching the spec's
     example. Before, it was the compressed 20 s.
- **@Luca, for the spec (PROVISIONAL, live now):**
  - `GET /astronauts/{id}/sans?view=crew|ground` →
    `{astronaut_id, mission_day, score, trigger_at, status, baseline_acuity,
    components[{name, points, detail}], vision_checks[{ts, acuity_line,
    amsler_distortion, headache}], note, source_url}`. The ground view only lists
    shared check-ins, and the details of private ones are redacted.
  - `GET /astronauts/{id}/history?hours=24` → up to ~300 averaged points of every
    vital plus `cabin_co2_mmhg`, oldest first, for charts (works up to 42 days).
  - `GET /mission/light-time` → **live Earth-Mars light time from NASA JPL
    Horizons: 661 s (11.0 min) today.** The verdict still uses the spec's 1320 by
    default; `AHM_LIVE_LIGHT_TIME=1` switches it to the live value. Verdicts don't
    change either way.
  - Hazard question: the spec has `sans` → `distance`, but NASA HRP files SANS
    under **altered gravity**. Backend follows the spec for now.
- **@NotKaemy:** charts can now load weeks of real history from `/history`, and the
  SANS view can draw `vision_checks` as a trend line with the `components` as
  the "why". **Circadian sharing default is done on `backend`:** `_shared` now
  defaults to `True`, so Ground gets 200 for everyone, and 403 ("the astronaut has
  opted out…") after `PUT .../circadian/sharing {"share_with_ground": false}`. Tested.
- **Done: judge 3's points (`events/2026-11-14-judge-3-sensors-blackout.md`), branch
  `backend`, tested.** All PROVISIONAL and additive; existing fields unchanged.
  - **Sensor accuracy:** each reading is checked (impossible value / spike / stuck sensor /
    watch dropout) and stored with `quality` = ok | suspect | implausible | artifact.
    Vitals gain `quality`. Impossible readings never raise an alert. The baseline uses only
    `ok`. `GET /astronauts/{id}/sensors` gives per-signal status and last-hour accuracy.
  - **"Do you feel this?":** vitals alerts gain `confirmation {status: pending|felt|not_felt,
    question, answered_at, note}` and `data_quality: ok|suspect`. `POST
    /astronauts/{id}/alerts/{alert_id}/confirm {felt, note?}` returns the alert and re-sends
    it on SSE with the same id. "No" marks the readings as `artifact` (flagged, never
    deleted, left out of the baseline/charts/reports), clears the alert, and mutes that
    episode. SANS alerts have `confirmation: null` (they come from check-ins); confirming
    one gets 409.
  - **Blackout:** `PUT /mission/blackout {active, until?, reason?}`, `GET /mission/blackout`.
    `GET /mission` gains `blackout`. During a blackout, Ground SSE holds every alert plus
    the latest vitals and delivers them after contact returns (plus the light time).
    Explanations say "Earth is out of contact… tell a crewmate or the CMO", with no cloud
    call, and `ground_eta_s` includes the blackout left. `GET /protocols` gives on-board
    steps per condition.
  - **Report from history:** `GET /astronauts/{id}/report?days=7&view=crew|ground` returns
    vitals vs own baseline, alerts with the astronaut's answer, check-ins, SANS, sleep, data
    quality, **time to action vs the Earth round trip**, a ~1.3 KB `text` packet, and
    `delivery`. The ground view leaves out private check-ins and opted-out sleep data.
- **@NotKaemy, UI asks:** Yes/No buttons under `confirmation.question` on an alert; a
  "sensor check" chip from `vitals.quality`; a blackout banner from `GET /mission`
  `blackout` (and on Ground: "Out of contact, data will arrive when contact returns");
  a "Report" panel showing `report.text`.
- **@Luca:** demo beat for blackout + "do you feel this?" is in `presentation/ideas.md`.
  New endpoints listed above, for the spec when you have a minute.
- **TEAM DECISION (2026-11-14): mental health is now the focus**, with a profile per
  astronaut built from all signals plus a crew view, so the commander or ground can be
  notified. SANS, circadian and blackout stay as secondary features. Agreed with
  stefanalbu2010-byte: **astronaut first**. Nothing is shared until the astronaut chooses;
  only "urgent" notifies the commander and ground automatically.
- **Done: behavioral health on `backend` (`backend/behavioral.py`), tested.** All PROVISIONAL.
  - **Profile:** PHQ-2 (validated cut-off ≥3), mood, sleep/body clock, the 3-min reaction
    test (PVT-B, 355 ms lapse) and resting HR, each vs the astronaut's own days 7-14. Levels
    are steady / watch / concern / urgent, each signal comes with a plain reason, and there
    are supportive suggestions. Safety rule: PHQ-2 5-6 plus one other sign is always urgent.
  - **Who sees what:** the astronaut sees everything. Commander/ground see it only if the
    astronaut shared it (per target), or automatically at urgent, and then only the level
    and areas, never the answers. Crewmates never see it. The crew view shows crew-wide
    trends without names, only with ≥3 people; PHQ-2 is never aggregated.
  - **Notifications:** live SSE event **`notice`**, delivered only to the right screen:
    the commander's own console (`a1`'s crew stream), the astronaut themselves, and the
    astronaut's ground stream (delayed; held during a blackout). Also `GET /notifications?viewer=`.
  - **Endpoints:** `GET /checkin/questions` (exact PHQ-2 wording + reaction test),
    `GET /astronauts/{id}/wellbeing?viewer=`, `PUT /astronauts/{id}/wellbeing/sharing?viewer=`
    `{commander?, ground?}` (only the astronaut), `GET /crew/wellbeing?viewer=a1|ground`.
    `POST /checkin` gains optional `phq2 {little_interest, feeling_down}` (0-3 each) and
    `reaction_test {mean_rt_ms, lapses, false_starts, duration_s}`.
  - **`viewer`** = the signed-in astronaut's id, or `ground`. **@NotKaemy:** this is what the
    per-astronaut login should send. Demo-level, not real security.
  - **Demo (repeatable):** seed → `a2` starts at **watch** (mood down after the midpoint,
    slower reactions, drifting bedtimes) → a2 check-in with PHQ-2 = 3 → **concern** → a2
    taps "share with commander" → the commander's console gets the notice.
    `POST /debug/scenario {a3, "strain"}` → **urgent** → commander + ground notified
    automatically, a3 is told. `clear` resets.
- **@NotKaemy, UI asks:** PHQ-2 + reaction test in the check-in (wording from
  `/checkin/questions`); a "My wellbeing" card (level, reasons, suggestions, share toggles
  for commander and ground); a commander view (`/crew/wellbeing?viewer=a1`, notices); on
  Ground, notices and the crew view (`viewer=ground`). Listen for SSE `notice`.
- **@Luca: please merge `backend` into `main`.** `main` still runs the morning's mock
  backend, so none of today's backend work (database, conditions, sensors, blackout, reports,
  mental health) is on `main` yet. The watch fix (`.last` → `.first`) is still open too.
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

- **App renamed to `dr.galactic`** (NotKaemy, 2026-11-14; lowercase, with the
  dot). Done in the web on `web` (not merged yet): page titles, menu brand,
  login / presenter / demo headings. **Luca / @stefanalbu2010-byte / @dbm711:**
  `README.md`, root `CLAUDE.md`, the backend's FastAPI title and the slides
  still say "Astronaut Health Monitor" — yours to rename. The repo name and
  internal names (`window.AHM`, `ahm-session`) stay.

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
- **Done — Ground view (merged to `main`):** `web/ground.html`. One
  `view=ground` stream per astronaut; crew cards (status from *received*
  alerts, vitals vs baseline, HR sparkline, "as of / N s old"); received-alerts
  feed (what the crew was told, raised vs reached-ground time, insight);
  permanent DELAYED VIEW banner. **"Signals in transit" is a labelled demo
  overlay** for the `incoming — 00:18` beat: it polls the undelayed
  `GET /alerts` and drops an alert once the delayed stream delivers it.
- **Done — verdict uses `real_one_way_delay_s` (merged).** Headers read
  `Mars · 22 min one-way (demo: 20 s)` from the field. Checked in mock:
  `orthostatic` -> act on board, `sans` -> ground.
- **Done — NASA hazard + HRP risk on every alert (merged).** Self-check banner
  and history, Ground feed and stream check all show e.g. "NASA hazard: Gravity
  Fields · NASA risk: Risk of Cardiovascular Adaptations", linked to nasa.gov.
  Titles verbatim from nasa.gov/hrp/hazards and /hrp/risks; mapping lives only
  in `web/common.js` (`HAZARDS`, `HRP_RISKS`). **`co2` shows its hazard only —
  NASA lists no CO2 risk.** New post-pivot profiles need a line in `HRP_RISKS`
  to get their risk name; until then they show the hazard alone.
- **Next — waiting on the post-pivot spec:** PHQ-2 check-in flow (questionnaire
  -> AI summary -> astronaut reviews -> `share_with_ground`) and the SANS risk
  score display. Luca, the shapes I need: the PHQ-2 fields on `POST /checkin`,
  where the AI summary comes back from, and how the SANS score arrives (field
  on vitals, its own event, or an alert).
- **Done on `web` (not merged yet) — circadian in both views.** Self-check:
  lighting chip, `card` text, 7-night bedtime chart, recommendation + sources,
  share toggle. Ground: one sleep & light line per crew card. Tested in real
  time against `main`'s backend.
- **Decision (NotKaemy): sleep & lighting is shared with ground by default,
  and private on the ship console.** The console is a shared screen on board,
  so Self-check hides the card and the "Sleep last night" tile behind "Show my
  sleep data" (re-hides after 2 min). The astronaut can still untick sharing;
  Ground then shows "not shared by the astronaut". Web and mock are done.
  - **@stefanalbu2010-byte, one-line backend change please:** in
    `backend/circadian.py`, `_shared = {aid: True for aid in HABITS}` (default
    shared). Until then the real backend still answers Ground with 403, so
    Ground shows "not shared" for everyone.
  - **Luca, spec:** the circadian section should say "shared with ground by
    default; the astronaut can opt out". Also `card` is shown as an object in
    the spec, but `circadian.py` returns a **string or null** — the web
    accepts both for now; please pick one.
- **Done on `web` (not merged yet) — login per role + Commander + ship's
  doctor.** Placeholder logins `crew`, `captain`, `doctor`, `ground`, `demo`
  (presenter, all views), each landing on its own interface. Details in
  `web/CLAUDE.md`.
  - **Commander** (`captain.html`): physical + psychological warnings for every
    crew member, each with advice on how to help. Sees everything (NotKaemy's
    decision).
  - **Ship's doctor** (`doctor.html`): today's doses (due / overdue / given)
    and medication suggestions from live alerts — from a **sample** plan in
    `web/meds.js`, labelled as not medical guidance.
  - **Both are crew too:** their pages open on **their own health data** (My
    health · Check-in · Sleep & light, the same data-only console as the
    crew: Elena `a1`, Sara `a3`, found in `GET /crew` by role), and the crew
    work is a **separate tab** (Crew wellbeing / Medications, with a count on
    the tab). No backend change needed.
- **Decision (NotKaemy): the astronaut console shows DATA ONLY — no warnings
  at all.** "The crew members should not know what happened to them." Their
  console shows their own numbers vs. baseline, chart, check-in and sleep
  log; no banner, verdict, advice, insight, alert history or warning colours.
  Warnings go only to the Commander, the ship's doctor and Ground. Done on
  `web` (not merged yet). This replaces the "Commander first, then release"
  idea, so that backend ask is **withdrawn**.
  - **Luca — this contradicts two things you own:** (1) root `CLAUDE.md`
    says the astronaut is the primary user and first responder, and the
    **watch** shows the wearer an alert banner + haptic + action line. Both
    are yours to update or keep; the web no longer warns the crew. (2) The
    demo script's step 3 ("Self-check lights up: Act on board now"). In
    `demo.html` the left pane is now the **Commander** view, which sees the
    alert instantly while Ground counts down — same story, different
    on-board screen.
  - **@dbm711:** `presentation/demo-script.md` step 3 needs rewording to the
    Commander's screen; notes in `presentation/ideas.md`.
- **Backend ask — @stefanalbu2010-byte, Luca for the spec:**
  1. **Medications.** Nothing in the backend or spec. Proposal: `GET
     /medications` → `[{astronaut_id, drug, dose, route, times[], purpose}]`
     and `PUT /medications/doses/{key}` `{given_at}`. The web's sample plan
     already has that shape (`web/meds.js`).
- **Blocked on:** the post-pivot `docs/api-spec.md` for PHQ-2 and the SANS
  score display. Not blocked on anything else.
