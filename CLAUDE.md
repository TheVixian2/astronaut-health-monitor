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
  - **Ship's doctor** (`doctor.html` / `doctor.js`): *My health · Check-in ·
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
  the Commander, the ship's doctor and Ground. Don't add any back without the
  owner's say-so. (This replaces the earlier "Commander first, then release
  to the crew" mechanism.)
- **Ship's doctor** — today's doses from the **sample** plan in `meds.js`
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
- `stream-check.html` / `stream-check.js` — debug page: raw SSE events.
- **Vital icons:** every vital has a flat icon (`AHM.vitalIcon(key)` in
  `common.js`, `VITAL_ICONS`): heart + pulse, blood drop, lungs, thermometer,
  moon, smiley. Colours are the `--ic-*` tokens in `style.css` (`.vi-*`).
  Shown on the My health tiles; reuse it wherever a vital is labelled.
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
  never raw hex, in new CSS and JS (the chart reads them with
  `getComputedStyle`). On board = Mars red, Ground = blue. Thin lines and link
  text use `--accent`, a lighter tint of the blue, because `#1B3A8A` is too
  dark to read on black. Status colours (ok green, watch yellow, alert orange)
  stay outside the palette because they carry meaning.
- The long Claude explanation (`insight.why` / `trend` / `recommended_action`)
  is shown **here only** — the watch gets just the one-line `onboard_action`.
- `insight` can be `null`; render the alert without it rather than waiting.
- Always show which view is active and how stale it is. Mission Control looking
  at 11-minute-old data must be able to tell.
- Decision support, never a diagnosis. Keep the wording suggestive, not clinical.
