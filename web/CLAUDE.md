# web — CLAUDE.md

**Owner: NotKaemy.** Only the web owner edits this folder.

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

- `login.html` + `auth.js` — **login gate, placeholder only.** One universal
  account, checked in the browser: user `crew`, password `mars2026` (change
  them at the top of `auth.js`). Every page loads `auth.js` first in `<head>`
  and is redirected to the login page when signed out, then sent back to
  where it was going (`?next=`). Session lasts 12 h in `localStorage`. **Not
  security:** the password is readable in the code and the backend has no
  auth. The repo goes public at submission — don't reuse a real password.
- `index.html` — after login: choose **On board** or **Ground**, plus a small
  link to the live demo. Keeps `?mock`/`?base`/`?aid`.
- **Two areas, two menus** (the `.appnav` bar at the top of each page):
  - **On board** (`self-check.html`): *My health · Check-in · Sleep & light ·
    Alerts*. Tabs inside one page, chosen by the URL hash (`#health`,
    `#checkin`, `#sleep`, `#alerts`); sections carry `data-tab`. The alert
    banner stays visible on every tab. "Alerts" shows a count badge.
  - **Ground** (`ground.html`, `stream-check.html`): *Crew overview · Raw
    stream (debug)*.
  - Inside `demo.html` the menus are hidden (`html.embedded`).
- `self-check.html` / `self-check.js` — the astronaut console: alert banner with
  verdict, clickable body figure, vitals tiles vs baseline, Chart.js trend,
  check-in form (`share_with_ground` off by default), alert history.
- **Circadian (PROVISIONAL in the spec):** Self-check's Light & sleep card
  reads `GET /circadian?view=crew` — lighting chip, `card` text, 7-night
  bedtime chart, `recommendation` + source, and the share toggle
  (`PUT /circadian/sharing`). **Shared with ground by default** (decided
  2026-11-14; backend default change requested from stefanalbu2010-byte); the
  astronaut can opt out. **On the ship console sleep data is private**: the
  console is a shared screen, so the card and the "Sleep last night" tile stay
  hidden until the astronaut taps "Show my sleep data", and re-hide after 2 min
  without touching the card. Ground shows one line per astronaut from
  `view=ground`: a **403 means "not shared by the astronaut"**, 404 shows
  nothing. Without the endpoint the card falls back to
  the static guidance. `card` is accepted as a string (backend) or an object
  (spec) via `AHM.circadianCardText()`.
- `ground.html` / `ground.js` — the flight surgeon: one `view=ground` stream
  per astronaut, crew cards (status from received alerts, vitals vs baseline,
  HR sparkline, data age), received-alerts feed, real light time always in the
  header. The **"signals in transit" strip is a demo overlay**: it polls the
  undelayed `GET /alerts` to show the `incoming — 00:18` countdown. Polled, not
  streamed, so the page stays at 4 SSE connections (browser limit ~6 per host).
- `demo.html` — Self-check and Ground side by side (two iframes) for the
  pitch. Holds 5 SSE connections (1 + 4), just under the browser's ~6 per
  host; Ground's in-transit polling shares the last slot. Tested against the
  real backend.
- `stream-check.html` / `stream-check.js` — debug page: raw SSE events.
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
- **Ground** — the flight surgeon. The whole crew at once, **delayed by the
  mission's one-way light time** (use `stream?view=ground`).

## Conventions

- **`docs/api-spec.md` is the contract.** Read from it, don't guess field names.
- Data arrives over **SSE** (`EventSource`), not polling. Listen for the named
  `vitals` and `alert` events.
- Severity colours are fixed: `watch` yellow, `alert` orange, `critical` red.
- The long Claude explanation (`insight.why` / `trend` / `recommended_action`)
  is shown **here only** — the watch gets just the one-line `onboard_action`.
- `insight` can be `null`; render the alert without it rather than waiting.
- Always show which view is active and how stale it is. A flight surgeon looking
  at 11-minute-old data must be able to tell.
- Decision support, never a diagnosis. Keep the wording suggestive, not clinical.
