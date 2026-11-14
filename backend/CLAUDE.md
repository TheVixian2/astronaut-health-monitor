# backend — CLAUDE.md

**Owner: S1eevee**, joined by Luca once the watch app is done. Only the backend owner edits this folder.

## Stack

Python 3 + **FastAPI** (locked). `uvicorn` to serve, `httpx` for the NOAA fetch,
`pydantic` for every request/response model, `anthropic` for the insight service.
No database — in-memory stores are fine for a hackathon demo.

## Run it

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env     # then paste your ANTHROPIC_API_KEY into .env
uvicorn main:app --reload
```

Serves on `http://localhost:8000`. CORS stays open for local dev — the web app is
opened as a `file://` page and the watchOS Simulator talks to `localhost`.

## Conventions

- **`docs/api-spec.md` is the contract.** Match it exactly. If something needs to
  change, ask Luca — don't change the shape unilaterally.
- Every endpoint gets a pydantic model. No bare dicts in responses.
- Vitals other than heart rate are **simulated server-side** from a per-astronaut
  scenario state, so they move together coherently (fever raises temp AND HR).
- The condition engine fires an alert only on a **new** match, not on every tick.
  That's what gates the Claude call.
- `insight_service.py` must **never** raise into the request path. Missing API key
  or a failed call returns a canned fallback `Insight`.
- SSE: `text/event-stream`, named events (`vitals`, `alert`), `view=ground` is
  delayed through a queue by the mission's one-way light time.
- Keep the NOAA fetch cached (it updates every few minutes) and never let a NOAA
  outage take down `/space-weather`.

## Layout

- `main.py` — FastAPI app and the endpoints.
- `insight_service.py` — the Claude call plus its fallback.
- `/tools` (sibling folder, same owner) — `simulate_crew.py` and other scripts.
