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
