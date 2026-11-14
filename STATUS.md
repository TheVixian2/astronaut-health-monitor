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

- **2026-11-14 — REAL NASA DATA in the stream + new dependency. Run
  `pip install -r backend/requirements.txt` (adds `lightstreamer-client-lib`).**
  `backend/iss_live.py` subscribes to NASA's public ISS Live telemetry: the cabin our
  simulated crew lives in is the real ISS cabin (CO2, O2, pressure, temperature).
  `GET /environment` + SSE event `environment`; the Commander's Habitat tab shows it.
  Also new since the last entry: History page (`web/history.html`), Commander sees
  every crew member's wellbeing level + areas, Habitat map (`GET /habitat`,
  `/crew/locations`, `/astronauts/{id}/rooms`). Shapes in `docs/api-spec.md`.

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
    reaction test the rest. (3) **No "flight surgeon": the ground role is called Mission Control** (Luca).
    (4) Ship's doctor page stays. Shapes in `docs/api-spec.md` → "Decided, NOT built yet".
  - **@stefanalbu2010-byte:** release endpoint + deputy routing; `/ingest` accepts
    `hrv_sdnn_ms`, `active_min`; simulator + seed add HRV/activity (a2 drifts down after
    the midpoint); `behavioral.py` adds `hrv` and `activity` signals with the 60-80 % weight.
  - **@NotKaemy — done for you by Luca's session (pull first):** BP removed from
    `common.js`, `ground.js`, `mock.js`; check-in lost the vision check and the "Off by
    default…" line; every "flight surgeon" is now **Mission Control** (UI, logins, backend
    text, docs). Still yours: old profile entries in `captain.js`/`meds.js`/`common.js`/`mock.js`.
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

Branch: `backend` (latest `f728ec1`). Section rewritten 2026-11-14 for the mental-health
version; the older notes (SANS, fever, orthostatic, astronaut-first sharing) are in git history.

- **@Luca: please merge `backend` into `main`.** It already contains `main`'s ISS Live CO2,
  habitat map and history work (merged, the 5 conflicts in `main.py` resolved, tested).
  `pip install -r backend/requirements.txt` first (`lightstreamer-client-lib`).
- **Demo prep (before every rehearsal):** from the repo root,
  `backend/.venv/bin/python tools/simulate_crew.py --reset-db --seed-baseline`
  (Windows: `backend\.venv\Scripts\python ...`), then start uvicorn. The seed is now
  **repeatable**: the same story whatever time it runs (a2 ends at "watch" on day 42).
- **Done: one psychological profile per astronaut (`backend/behavioral.py`).** Every input is
  compared with the astronaut's **own** mission days 7-14 (how many SDs it moved, in the
  worrying direction), then weighted. Score 0-100: steady < 20, watch 20-39, concern 40-59,
  urgent 60+. Weights (Luca's 70/30 split, `GET /wellbeing/method` lists them all):

  | Watch and station (70) | | Check-ins (30) | |
  |---|---|---|---|
  | Sleep | 15 | PHQ-2 / PHQ-9 | 15 |
  | Heart-rate variability (night) | 12 | Mood | 8 |
  | Time with crewmates (beacons) | 12 | Reaction test (PVT-B) | 7 |
  | Activity | 11 | | |
  | Body-clock regularity (lighting log) | 10 | | |
  | Resting heart rate (night) | 10 | | |

  - **Safety rules on top (validated cut-offs):** PHQ-2 >= 3 or PHQ-9 >= 10 → at least
    concern; PHQ-2 >= 5 plus another sign, or PHQ-9 >= 20 → urgent; **PHQ-9 question 9 above
    0 → urgent and shown at once.** PHQ-2 >= 2 asks for the PHQ-9 next (two-step screening,
    Levis et al., JAMA 2020).
  - **Missing data:** an input needs 4 of 7 days; otherwise its weight is shared within its
    group, and `confidence` (high / medium / low) says how much had data.
  - **Trends over time:** a daily score for the whole mission, the slope over 14 days
    (worsening / improving at ±5 points a week), each input's own trend, the first day flagged.
  - **Psych report:** `GET /astronauts/{id}/psych-report?viewer=&days=28`, a ~2.7 KB text.
- **Accuracy check (`tools/check_profile.py --seeds 30`, 30 simulated crews):** false
  "concern" on stable astronaut-days **0.0%**, false "watch" **0.8%**; a2's slow decline
  detected on **87%** of days 35-41 (flagged from day 34, median; the decline starts on day 22).
  Synthetic data only: it checks the scoring against its own simulation, not clinical accuracy.
- **Done: alerts are commander-first (Luca's decision).** `wellbeing_concern`,
  `wellbeing_urgent` and `sleep_debt` go to the commander (a1), or to the deputy if the
  commander is the one flagged, and to Mission Control after the light delay. The
  astronaut's own views hold them back until the commander releases them
  (`PUT /astronauts/{id}/alerts/{alert_id}/release?viewer=a1`) or after 12 h
  (`AHM_RELEASE_AFTER_S`). Psychological data is never sent to a cloud model.
- **Done: Bluetooth beacons (`backend/location.py`).** One beacon per room, strongest above
  -90 dBm, two scans in a row must agree. Room ids are the habitat map's (`q_a1`..`q_a4`,
  `command`, `lab`, `galley`, `exercise`; **hygiene has no beacon, never tracked**).
  `/crew/locations` and `/astronauts/{id}/rooms` now read the same live room and stored stays
  as the profile (one model; `habitat.py` folded into `location.py`). Every crew-map view
  shows up in the astronaut's own `seen_by`.
- **New endpoints, PROVISIONAL (Luca, for the spec):** `GET /wellbeing/method`,
  `GET /astronauts/{id}/wellbeing?viewer=`, `GET /crew/wellbeing?viewer=a1|ground`,
  `GET /notifications?viewer=`, `GET /astronauts/{id}/psych-report?viewer=`,
  `GET /astronauts/{id}/alerts?viewer=`, `PUT .../alerts/{alert_id}/release?viewer=`,
  `GET /checkin/questions` (PHQ-2, PHQ-9, reaction test), `phq9 {answers: [9 x 0-3]}` on
  `POST /checkin`, `GET /station/rooms`, `POST` + `GET /astronauts/{id}/location`.
  `/ingest` takes `hrv_sdnn_ms` and `active_min`. `/rooms` adds `with_crew_7d_avg_h` and
  `with_crew_normal_h`. **Removed:** `PUT /astronauts/{id}/wellbeing/sharing`.
- **Demo beats:** (1) Commander page: a2 at **watch**, trend worsening. (2) a2's check-in
  with PHQ-2 = 3 → **concern** → the commander's console gets the notice; a2's own page says
  it's with the commander. (3) The commander releases it → a2 sees the assessment and
  suggestions. (4) `POST /debug/scenario {a3, "strain"}` → **urgent**. `clear` resets.
- **Done: optional check-in tags (`c7773a8`).** `POST /checkin` takes
  `context: ["ill" | "new_medication" | "period"]`. Those days are left out of the body
  signals they distort (a cold, a new sleep pill, the late menstrual cycle lowering HRV), so
  they aren't read as a change in wellbeing. Mood and the PHQ always count and the safety
  rules always apply, so a tag can't hide a warning. Others only see "N of the last 7 days
  left out (marked in a check-in)", never which tag. Signals gain `left_out_days`;
  `GET /checkin/questions` gains `context` (question, options, note).
- **Safety fix:** a PHQ-9 with question 9 above 0 now keeps the level at urgent for the
  14-day PHQ window. Before, a routine PHQ-2 the next day could clear it.
- **Decided (Stefan, 2026-11-14):**
  - **The psychological side never shows on the watch.** Backend: `POST /ask` answers
    questions about feelings on board with a pointer to a person (crisis words: "tell someone
    in person now"). They're never sent to Claude and never get a level or score.
  - **Hygiene in an emergency:** the commander, CMO and Mission Control may see the current
    room through `GET /astronauts/{id}/location` during an emergency (active critical alert or
    urgent level), hygiene included. That's the one exception to the hygiene rule, and the
    astronaut's `seen_by` lists who looked.
- **@Luca, watch:** please **remove the "Mood" row** from the vitals page (`ContentView.swift`,
  the `VitalRow(label: "Mood", ...)` line). Mood is a check-in answer, and the watch now shows
  no psychological data at all. Keep decoding `mood_1to5` (the vitals shape still has it).
  Your filter on psychological alerts in `MonitorModel.swift` stays as it is.
- **Team decisions needed:**
  1. **Time with crewmates in the score.** Stefan asked for every input to feed the profile,
     so it carries 12 of 100 points now. Luca's habitat note said display-only (weak evidence).
     To make it display-only: drop `social_time` from `behavioral.INPUTS` (its points spread over
     the other watch inputs) and re-run `check_profile.py`.
  2. **Crew map always on** for the commander and Mission Control (Luca: fire,
     depressurisation). Kept. Each astronaut's own room history stays private (the Crew
     Medical Officer sees the current room only in an emergency).
  3. **Who is the deputy?** The crew has no pilot. Default: the Crew Medical Officer, a3
     (`AHM_DEPUTY` to change it).
- **@Luca, watch:** (1) `MonitorModel.swift` takes `api.alerts().last`, but `/alerts` returns
  newest first: use `.first`. (2) The watch polls `/astronauts/a1/alerts`, which now
  includes a1's own unreleased psychological alerts (they belong to the deputy until
  released). Poll `/astronauts/a1/alerts?viewer=a1` instead, and they stay off the wrist.
- **@NotKaemy, UI asks:** (1) a **PHQ-9 step** in the check-in when the wellbeing answer
  has `needs_phq9: true` (wording in `GET /checkin/questions` → `phq9`; send
  `phq9: {answers: [...9]}`). If question 9 is above 0, show the support message at once.
  (2) Optional: the 3-min reaction test (`reaction_test`); without it its 7 points are
  shared among the other check-in inputs. (3) Commander page: a **Release** button on
  unreleased psychological alerts, and the psych report text. (4) Self-check: when the
  wellbeing answer has `withheld: true`, show "your commander has this first" instead of
  a level. (5) An optional "Anything that might affect your body this week?" step with
  the three `context` options from `GET /checkin/questions`, and its note under it.
  Your one-question check-in already matches the backend (mood, sleep,
  symptoms, PHQ-2).
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

- **My health: HRV and a stress level, Male | Female body** (NotKaemy,
  2026-11-14; on `web`, main merged in). HRV is `hrv_sdnn_ms` from the vitals.
  **The stress level (0-100) is computed in the web** from HRV vs the astronaut's
  own usual (usual = 30, each 10 % lower adds 16; bands resting / low / medium /
  high). Apple Watch has no stress score, so the scale is ours and the UI says
  so. **@stefanalbu2010-byte:** if `behavioral.py`'s watch-driven score gets
  exposed in the vitals, the web will show that instead. The body card has a
  Male | Female slider; sex is not in `GET /crew`, so it is remembered per
  browser. **@Luca:** a `sex` field on `/crew` would be picked up automatically.
- **Bone density and muscle mass are vitals** (NotKaemy, 2026-11-14: the crew
  carries a **portable X-ray machine**, DXA; they replace the earlier "skeletal
  mass"). From a weekly scan: `bone_density_g_cm2` (whole-body bone mineral
  density, 3 decimals) and `muscle_mass_kg` (lean tissue of arms and legs, DXA's
  stand-in for skeletal muscle). **@stefanalbu2010-byte:** please send both in the
  vitals and their `baseline` (usual = the mission days 7-14 scan; bone ~0.35 %/month
  lower since, the whole-body loss after long flights, LeBlanc et al. 2000; the web
  uses ~0.4 %/month for muscle as a placeholder). Until then the web fills in
  **simulated scans** and says so on screen; your values replace them
  automatically, field by field. **@Luca:** both need a line in `docs/api-spec.md`
  and `docs/monitored-signals.md` (NASA HRP risks: early onset osteoporosis;
  reduced muscle mass, strength and endurance).
- **Check-in: one question at a time, and no "share with ground" box**
  (NotKaemy, 2026-11-14; on `web`, not merged yet). Steps: mood → sleep →
  symptoms → the two PHQ-2 items from `GET /checkin/questions`. **Every
  check-in is now sent with `share_with_ground: true`.** **Luca:** the spec
  calls that field "the astronaut's control over what Mission Control sees… a
  deliberate design position" — NotKaemy decided to remove the choice; your
  call whether the spec/pitch wording changes. Also on `web`: every page
  (except presenter/demo) zooms up on big windows so it fills the screen.
- **App renamed to "Dr. Galactic"** (NotKaemy, 2026-11-14; the name is shown
  20% larger than the text around it). Done in the web on `web` (not merged yet): page titles, menu brand,
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
