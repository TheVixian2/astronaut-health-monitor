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

- _(none yet)_

---

## Watch — Luca

Branch: `watch`

- **Working:** Xcode project created (Watch-only, watchOS 27.2), builds clean.
- **Next:** `VitalsSource` / `SimulatedSource` / `APIClient` / `ContentView`.
- **Blocked on:** nothing.

## Backend — S1eevee (+ Luca later)

Branch: `backend`

- **Working:** nothing yet — Phase 2 not started.
- **Next:** mock `main.py` returning canned data for every endpoint in the spec,
  including a working SSE stream. This unblocks both other lanes, so it is the
  first thing built.
- **Blocked on:** nothing.

## Web — NotKaemy

Branch: `web`

- **Working:** nothing yet — Phase 2 not started.
- **Next:** `index.html` connecting to `/astronauts/a1/stream?view=crew` and
  printing events. Real UI after the mock backend is up.
- **Blocked on:** backend mock (can start against canned JSON meanwhile).
