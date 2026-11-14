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

**No backend running?** Open `index.html?mock` (or tick "Mock data"). `mock.js`
generates fake events in the page, mirroring the backend mock: `vitals` every
3 s, an `alert` on `a1` every 30 s re-sent ~2 s later with the same `id` and
`insight` filled in, and the ground view held back by 20 s. URL params `base`,
`aid` and `view` preset the controls.

## Files

- `index.html` / `style.css` / `app.js` — currently the Phase 2 stream check
  (connect, print events, upsert alerts by `id`). Real views replace it.
- `mock.js` — the in-page fake stream. Dev only.

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
