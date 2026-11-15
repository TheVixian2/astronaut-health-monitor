# web — CLAUDE.md

**Owner: NotKaemy.** Only the web owner edits this folder.

**App name: "Dr. Galactic"** (renamed by NotKaemy 2026-11-14). It is in
every page's `<title>` ("Commander · Dr. Galactic"), the top-left brand in the
menu bar, and the login / presenter / demo headings, where it is wrapped in
`.app-name`. The name is shown **20% larger** than the text around it
(`.app-name, .appnav .brand { font-size: 1.2em }` in `style.css`). Internal
names (`window.AHM`, `ahm-session`, the repo) stay as they are.

## Stack

Plain HTML/CSS/JS. **No build step, no framework, no npm.** Chart.js from a CDN
`<script>` tag. Open `index.html` in a browser — that's the whole workflow.

## Run it

Start the backend first, then open `web/index.html`. If `file://` causes trouble:

```sh
python3 -m http.server 5500   # then visit http://localhost:5500
```

On Windows (no `source`, no `python3`): from `backend/`,
`py -3.12 -m venv .venv`, `.venv\Scripts\python -m pip install -r requirements.txt`,
then `.venv\Scripts\python -m uvicorn main:app --port 8000`. Set
`MOCK_AUTO_ALERT_S=20` first for faster fake alerts.

**No backend running?** Open `index.html?mock` (or tick "Mock data"). `mock.js`
generates fake events in the page, mirroring the backend mock: `vitals` every
3 s, an `alert` on `a1` every 30 s re-sent ~2 s later with the same `id` and
`insight` filled in, and the ground view held back by 20 s. URL params `base`,
`aid` and `view` preset the controls.

## Files

- `login.html` + `auth.js` — **login gate with one account per role,
  placeholder only.** Checked in the browser; all passwords `mars2026`
  (change them in `ACCOUNTS` at the top of `auth.js`):

  | Login | Role | Lands on | May open |
  |---|---|---|---|
  | `crew` | Astronaut | `self-check.html` | that only |
  | `captain` | Commander | `captain.html` | that only |
  | `doctor` | Crew Medical Officer | `doctor.html` | that only |
  | `ground` | Mission Control | `ground.html` | + `stream-check.html` |
  | `demo` | Presenter | `index.html` | everything, incl. `demo.html` |

  `PAGE_ROLES` in `auth.js` decides who may open what; a wrong role is sent to
  its own interface. Every page loads `auth.js` first in `<head>`. Session
  lasts 12 h in `localStorage`. **Not security:** passwords are readable in
  the code and the backend has no auth. The repo goes public at submission —
  don't reuse a real password.
- `index.html` — presenter-only page: the four profiles as a **2 × 2 grid** of
  cards (role icon, the real name from `GET /crew` by role, Ground's light
  time from `GET /mission`, the profile's tabs, its login), plus the live demo
  link. **Fills the window exactly** (screens ≥ 721 × 521): a small script in
  `index.html` finds the largest font size at which all four cards fit and
  sets `--fit`; every size on the page is in `em` of it, so it all scales
  together and re-fits on resize. Narrower or shorter: one column, normal
  scrolling. Keeps `?mock`/`?base`/`?aid`. Card styles:
  `.profiles` / `.profile` in `style.css`, tinted with the area tokens
  `--onboard-*` / `--ground-*`.
- **Menus** (the `.appnav` bar at the top of each page; "All views" link only
  for the presenter, `[data-demo-only]`):
  - **Astronaut console** (`self-check.html`): *My health · Check-in · Sleep &
    light*. Tabs inside one page, chosen by the URL hash (`#health`,
    `#checkin`, `#sleep`); sections carry `data-tab`.
  - **Commander** (`captain.html` / `captain.js`): *My health · Check-in ·
    Sleep & light · Crew wellbeing* (`#crew`, with a warning count).
  - **Crew Medical Officer** (`doctor.html` / `doctor.js`): *My health · Check-in ·
    Sleep & light · Medications* (`#meds`, with a count).
  - The Commander and the doctor are crew too (decided by NotKaemy
    2026-11-14): their first three tabs are **their own data**, the same
    data-only console as the crew, and the crew-facing work is a separate tab.
    Whose data it is comes from `GET /crew` by role (`data-crew-role` on
    `<main id="console">`: "Commander" = a1, "Crew Medical Officer" = a3;
    `data-aid` is the fallback).
  - **Ground** (`ground.html`, `stream-check.html`): *Crew overview · Raw
    stream (debug)*.
  - Inside `demo.html` the menus are hidden (`html.embedded`).
- **Commander** — one panel per crew member: **physical** warnings (vital-sign
  alerts) and **psychological** ones (`sleep_debt` / hazard `isolation`
  alerts, mood ≤ 2/5, short sleep, the circadian irregular-sleep card), each
  with pre-written "How you can help" advice (`ADVICE` in `captain.js`).
  The Commander sees everything for everyone (decided 2026-11-14), their own
  warnings included: that panel is tagged "you" and its advice says to see the
  Crew Medical Officer (`SELF_ADVICE`).
- **The astronaut console is DATA ONLY — no warnings** (decided by NotKaemy
  2026-11-14: "the crew members should not know what happened to them").
  It shows the person's own numbers against their own baseline, the chart,
  the body figure (to pick a region, never coloured by alerts), check-in and
  their sleep/lighting log. It does **not** subscribe to `alert` events and
  shows no banner, verdict, advice, insight, warning colours, or the
  circadian `card` / `recommendation` / `evidence` texts. Warnings go only to
  the Commander, the Crew Medical Officer and Ground. Don't add any back without the
  owner's say-so. (This replaces the earlier "Commander first, then release
  to the crew" mechanism.)
- **Crew Medical Officer** — today's doses from the **sample** plan in `meds.js`
  (`schedule`, station time UTC): due now (−15/+30 min), overdue, upcoming,
  "Mark given" (kept in `localStorage`). Live alerts from the last hour add
  "Consider: …" suggestions from `meds.js` `onAlert`, always the CMO's
  decision. No medication data exists in the backend or spec yet.
- **Commander and doctor poll** `GET /vitals` + `GET /alerts` every 3 s
  (`AHM.watchCrew`) instead of 4 SSE streams each, and their own-data tabs
  poll their own `GET /vitals` (`data-poll`): browsers allow ~6 connections
  per host and the console + Ground already use 5 on one machine. In `?mock`
  mode they use in-page mock streams.
- **My health fills the window** (all three console pages): `self-check.js`
  sets `body[data-tab]`; on `health` the console grid stretches to the
  bottom, the vitals tiles are tall and stretch across the row (`auto-fit`),
  and the chart (`.chart-box`, canvas absolutely positioned so Chart.js can't
  grow the card) and the body figure take the free height.
- `self-check.html` / `self-check.js` — the astronaut console (data only):
  body figure, vitals tiles vs baseline, Chart.js trend, check-in form
  (`share_with_ground` off by default), sleep & light log. **Its cards are
  markup in `consoleMarkup()` at the end of `self-check.js`**, injected into
  `<main id="console">` on `self-check.html`, `captain.html` and
  `doctor.html`; edit them there. The tab list is the page's
  `[data-tab-link]` entries.
- `demo.html` left pane is the **Commander's Crew wellbeing tab**
  (`captain.html#crew`; the Commander learns first on board now that crew
  consoles show no warnings); right pane is Ground.
- **Circadian (PROVISIONAL in the spec):** Self-check's Light & sleep card
  reads `GET /circadian?view=crew` — lighting chip, `card` text, 7-night
  bedtime chart, `recommendation` + source, and the share toggle
  (`PUT /circadian/sharing`). **Shared with ground by default** (decided
  2026-11-14; backend default change requested from stefanalbu2010-byte); the
  astronaut can opt out. **On the ship console the 7-night log and lighting
  are private**: the console is a shared screen, so they stay hidden until the
  astronaut taps "Show my sleep data", and re-hide after 2 min without
  touching the card. **"Sleep last night" is public** (tile + the "Last
  night: X h" line; NotKaemy, 2026-11-14). Ground shows one line per astronaut from
  `view=ground`: a **403 means "not shared by the astronaut"**, 404 shows
  nothing. Without the endpoint the card falls back to
  the static guidance. `card` is accepted as a string (backend) or an object
  (spec) via `AHM.circadianCardText()`.
- `ground.html` / `ground.js` — Mission Control: one `view=ground` stream
  per astronaut, crew cards (status from received alerts, vitals vs baseline,
  HR sparkline, data age), received-alerts feed, real light time always in the
  header. The **"signals in transit" strip is a demo overlay**: it polls the
  undelayed `GET /alerts` to show the `incoming — 00:18` countdown. Polled, not
  streamed, so the page stays at 4 SSE connections (browser limit ~6 per host).
- `demo.html` — Commander and Ground side by side (two iframes) for the
  pitch. The Commander pane polls (no SSE) and Ground holds 4 SSE streams,
  under the browser's ~6 per host. Tested against the real backend.
- **Every visit starts at the login page** (owner, 2026-11-14): the session is
  in sessionStorage, so it lasts for one tab (and demo.html's panes and pages
  opened from it). On GitHub Pages the login page offers **"Continue as
  presenter"** with no password, which keeps the Space Apps "no login" rule.
- **Threshold scales on Mission Control** (owner, 2026-11-14): every crew card
  lists all vitals with a green-to-red bar and a marker. `AHM.thresholdLevel`
  (`common.js`, `THRESHOLDS`) measures distance from the astronaut's OWN usual
  (never a population range); watch / alert / critical steps are placeholders.
- **No explanation boxes** (owner, 2026-11-14): the Commander's "Crew members
  don't see these warnings" note, the Medications "Sample medication plan" note
  and Mission Control's green-to-red key were removed on request. Don't add
  boxes that explain the page back without asking. The decision-support footer
  on `doctor.html` stays; the sample plan is still marked in `meds.js`.
- **Cycle-aware usual** (owner, 2026-11-14): personal baselines already cover
  differences between bodies, but not the menstrual cycle (luteal phase: about
  +0.3-0.5 °C, a few bpm, HRV a little lower). Opt-in from the astronaut's own
  console (Cycle button by the body switch, shown with the female figure or when
  on): first day of the last period + cycle length. `AHM.withCycle` then shifts
  the usual for temperature (+0.35 °C), heart rate (+4 %) and HRV (-8 %) in the
  luteal phase; stress follows. Only the own console names the cycle ("cycle
  usual", "Cycle day N"); Mission Control just uses the adjusted usual. Saved in
  localStorage `ahm-cycle` per astronaut (would belong with the astronaut's
  private data on the backend). The demo pattern follows the cycle when it is on.
- **Presenter sees a pattern, not live data** (owner, 2026-11-14): signed in as
  `demo`, the console, Commander, doctor and Mission Control pages load a
  deterministic pattern for the whole mission (`pattern.js`: station day,
  nightly sleep and daily mood, weekly X-ray scans, a2's strain in the second
  half, a4's hard days around day 31) and show a **period selector** (span +
  "ends at" slider) in the header instead of the live status. Readings are the
  moment the period ends; charts show the period (bucket averages on long
  spans). Not inside `demo.html` (the live light-delay demo stays live), not
  with `?live`. Crew wellbeing, meds, habitat and alerts are unchanged.
- **Test feed** (owner, 2026-11-14): the `test` account (or `ground.html?test`)
  shows one scripted test subject (`test-feed.js`), new data every 10 s: one
  vital wrong (past critical), then good, through every vital in turn. Browser
  only, no backend; the step comes from the clock so all tabs agree.
- **The 6-connection limit is shared by every tab** (bug found 2026-11-14:
  a Mission Control tab + a demo tab left open starved every new page, stuck
  on "connecting…" until the backend was restarted). `AHM.openStream` returns
  a `PausingEventSource` (`common.js`): a stream closes once its tab has been
  hidden for 15 s and reopens when the tab is shown. Keep every new stream on
  `openStream`; never `new EventSource` directly.
- `stream-check.html` / `stream-check.js` — debug page: raw SSE events.
- **Check-in is one question at a time** (Back / Next, Submit on the last):
  mood → sleep hours (± half-hour buttons) → symptoms (with an exclusive
  "None of these") → the two PHQ-2 items (wording from `GET /checkin/questions`;
  left out if that fails) → the optional reaction test. **Every question needs
  an answer: Next and Submit stay disabled until it has one** (owner,
  2026-11-15: no skipping by pressing Next); only the reaction test can be
  skipped. "none" is never sent as a symptom. **No
  "share with ground" box: check-ins are always sent with
  `share_with_ground: true`** (NotKaemy, 2026-11-14 — note the spec calls this
  the astronaut's control; flagged to Luca in STATUS). Form is `novalidate`:
  a field on a hidden step would otherwise block Submit silently.
- **Bigger interface on big windows:** `auth.js` zooms every page (except
  `index.html` / `demo.html`) by `min(width/1280, height/720)`, between 1 and
  1.75, and sets `--z`. CSS zoom also scales `vh`, so write window heights as
  `calc(100dvh / var(--z, 1))`. Chart.js gets a matching pixel ratio. My
  health, Check-in and Sleep & light stretch to the window's height.
- **Vital icons:** every vital has a flat icon (`AHM.vitalIcon(key)` in
  `common.js`, `VITAL_ICONS`): heart + pulse, blood drop, lungs, thermometer,
  moon, smiley, pulse trace (HRV), gauge (stress). Colours are the `--ic-*`
  tokens in `style.css` (`.vi-*`). Shown on the My health tiles; reuse it
  wherever a vital is labelled.
- **HRV and stress** (owner, 2026-11-14/15): ten readings, five per row. HRV is
  `hrv_sdnn_ms` from the vitals (SDNN, as Apple Watch records it). **Stress
  (0-100)** comes from the backend's wellbeing score (`AHM.withStress`), with an
  HRV-only fallback where the backend scores nothing (pattern, test feed).
  **Its usual is 30, never 0** (owner, 2026-11-15: "it cannot be 0"): Apple
  Watch has no stress score; Garmin's HRV-based 0-100 score (Firstbeat) averaged
  30 across all users in its 2024 Connect data report ("low"; countries 28-33).
  Shown = 30 + backend score × 0.7, so normal reads 30 and the worst 100; the
  backend's levels keep their cut-offs on this scale (steady ≤ 43, watch 44-57,
  concern 58-71, urgent 72+; `THRESHOLDS` steps 44 / 58 / 72). Fallback: 30 at
  the usual HRV, +16 per 10 % below it, lower when HRV is above it (sleep reads
  low, as on wearables). Fields with `derived: true` are skipped where raw
  backend fields are listed (`stream-check.js`).
- **Body shape** (owner, 2026-11-14): a Male | Female slider on the body card
  swaps the silhouette (`setSex` in `self-check.js`; shapes in `common.js`
  `AHM.BODY_SHAPES`, generated so both share their points and morph). Sex is
  not in the crew data, so `AHM.sexOf(member)` takes: the slider choice
  (localStorage per astronaut, `ahm-body-sex`), else a `sex` field on
  `GET /crew` if the backend adds one, else the demo default `DEFAULT_SEX`
  (a1 Elena, a3 Sara female; a2 Mihai, a4 Jonas male).
- **Crew avatars are whole-body figures with the affected parts lit up**
  (owner, 2026-11-14; "whole body avatars on which the affected body parts get
  highlighted", not head-and-shoulders). `AHM.bodyFigure(member, hits)`: the
  My health silhouette and organs, male or female by `sexOf`; `hits` maps a
  part (head, heart, lungs, skin = arms and legs, torso, whole_body = outline)
  to watch / alert / critical, or info (blue: on treatment, nothing due).
  `AHM.addHit` keeps the most urgent level per part.
  - Commander's Crew wellbeing: a figure on the left of every card. Alerts
    light their `body_region`; low mood, short sleep, irregular sleep timing
    and a wellbeing check above steady light the head.
  - Medications: a row of the four crew above the lists, each with what their
    medicines are for (`region` / `area` per entry in `meds.js`): overdue
    orange, due now yellow, later today blue, given goes back to normal; alert
    suggestions light the alert's body part. The lists themselves show names.
- **The Commander sends; only then does the crew member's console change**
  (owner, 2026-11-15). Every crew member's card on Crew wellbeing (not the
  Commander's own) has **"Send to <name>"**: it releases their unreleased
  psychological alerts (`PUT /astronauts/{id}/alerts/{alert_id}/release`,
  viewer = the Commander) and keeps their health now (`AHM.healthScore`) plus
  the card's warnings, without the Commander's advice, via `AHM.setSentTo`.
  On their console the **health bar shows only what was sent** (neutral "—"
  until the first send; it never follows live readings) and "From your
  commander" lists the sent warnings next to released alerts. The Commander's
  own bar stays live. The CMO can send too (wellbeing bar only). Stored by the
  backend (`PUT/GET /astronauts/{id}/shared-check`); this browser keeps a copy
  (`ahm-sent-to-crew`) only after the backend accepted it.
  - **"Sent ✓"** on the button for 2.5 s after a send succeeds
    (`AHM.markJustSent` / `justSent`; the pages re-render, so sendRow reads it).
  - **Why it changed** (owner, 2026-11-15): with every report, **right under
    the wellbeing bar** on My health (`#wbWhy`, renderWhy): "Wellbeing 33%, down
    from 80%", the top 3 reasons and a link to My report. The reasons are the
    backend's, from their own `GET /wellbeing?viewer=<self>`: each signal with
    the % it takes off the bar (bar = 100 − score; points scaled like the
    backend does when a whole group has no data, so they add up to the drop).
    While a flag still waits for the commander the backend withholds them, and
    it says the reasons come once the commander has talked with them.
  - **My report tab** (`#report`, renderReport; owner, 2026-11-15) on the crew
    console and the CMO's page, not the Commander's (their bar is live): the
    whole last report. Value and level, change since the last report, how sure
    (confidence, coverage), every reason with its detail and evidence (tagged
    "new" / "was −N%" against the previous report; reasons that went away show
    0%), a 14-day chart up to the report's day (`trend.timeline`, 100 − score),
    the warnings shared with them, "What might help" (`suggestions`), signals
    still close to usual and those without enough data. A "New" badge on the
    menu until opened (`ahm-report-read`). Previous value and reasons are kept
    per browser (`ahm-sent-seen`). Send times are compared by moment
    (`sameAt`): the backend writes `.740000Z` where the browser wrote `.740Z`.
- **History and Data sources show the full menu, no Back link** (owner,
  2026-11-15): `AHM.pageMenu` (common.js) fills their nav with every tab of the
  page they were opened from (`?from=`, added to their links by common.js), or
  of the signed-in role; the page itself is marked current. Add a tab to a role
  page → add it to `PAGE_MENUS` too.
- **Chart scales:** `FIELDS[].axis` fixes the y-axis for bounded vitals:
  mood 1-5 (reads 5 4 3 2 1), stress 0-100 (never negative).
- **Bone density and muscle mass** (owner, 2026-11-14: the crew has a
  portable X-ray machine; replaced "skeletal mass" the same day). From a
  weekly DXA scan: `bone_density_g_cm2` (whole-body bone mineral density,
  3 decimals as DXA reports it) and `muscle_mass_kg` (lean tissue of arms and
  legs, the scan's stand-in for skeletal muscle). Region "skin" (limbs);
  change shown to 1 decimal (`dp` / `deltaDp` on the field). **PROVISIONAL
  bridge:** the backend sends neither yet, so `AHM.withScan` fills in
  simulated scans per field (`SIM_SCAN`: usual from the days 7-14 scan; bone
  ~0.35 %/month lower since, LeBlanc et al. 2000; muscle ~0.4 %/month, a
  placeholder rate) and the chart note says "Simulated scans for now". A field
  the backend sends wins. Simulating in the web breaks the "simulated
  server-side" rule on purpose until then.
- `common.js` — shared helpers (`window.AHM`): field list, profile names,
  verdict rule, stream/fetch wrappers that switch to the mock. Put the verdict
  logic here only.
- `mock.js` — in-page fake backend (`window.Mock`): stream, `/crew`,
  `/mission`, `/alerts`, `/checkin`. Dev only.
- `style.css` — one stylesheet for every page.

## Two views

- **Self-check** — the astronaut, on a station tablet. Their own vitals, a
  clickable body figure (regions: heart, head, lungs, skin, whole_body), the
  check-in form. **Not delayed.**
- **Ground** — Mission Control. The whole crew at once, **delayed by the
  mission's one-way light time** (use `stream?view=ground`).

## Conventions

- **`docs/api-spec.md` is the contract.** Read from it, don't guess field names.
- Data arrives over **SSE** (`EventSource`), not polling. Listen for the named
  `vitals` and `alert` events.
- Severity colours are fixed: `watch` yellow, `alert` orange, `critical` red
  (the palette's Mars red `#D62828`).
- **Colour palette** (team decision, 2026-11-14): Light Silver `#C0C6D4`, Mars
  Orange Red `#D62828`, Dark Mars Red `#8F1F0F`, Black `#0B0B0B`, Blue
  `#1B3A8A`. They live as tokens at the top of `style.css`; use the tokens,
  never raw hex, in new CSS and JS (charts read them with
  `getComputedStyle`). On board = Mars red, Ground = blue. Status colours (ok
  green, watch yellow, alert orange) stay outside the palette because they
  carry meaning; use `--*-ink` for them as text, the plain ones for fills.
- **Design system** (frontend-design pass, NotKaemy 2026-11-14; full notes at
  the top of `style.css`): a dark ship console. **Black is the page**
  (the owner switched back from the silver day look the same day; that set is
  in git at 09b4f03), silver is the type, panels are black lifted one step
  (`--panel`, 6 px radius). **Type is Archivo** (Google Fonts, one family at three
  widths): 125 % heavy for the wordmark and page titles, 75 % semibold
  tabular for readouts (vitals, counts, big stats), normal for the rest.
  Sentence case everywhere: no ALL-CAPS labels, no "A · B · C" strings, no
  "→" on links. The six vitals are **one instrument strip** (cells divided by
  rules, charted one marked with a Mars-red top bar), not six cards.
  **Always this dark theme** (owner, 2026-11-14): the console used to switch to
  a warm, blue-free set when the module's lighting went to Pre-sleep or off;
  that automatic switch is gone (the owner saw it as the colours changing).
  The warm set still exists for a demo: add `?light=pre_sleep` to any URL.
- The long Claude explanation (`insight.why` / `trend` / `recommended_action`)
  is shown **here only** — the watch gets just the one-line `onboard_action`.
- `insight` can be `null`; render the alert without it rather than waiting.
- Always show which view is active and how stale it is. Mission Control looking
  at 11-minute-old data must be able to tell.
- Decision support, never a diagnosis. Keep the wording suggestive, not clinical.
