# 2026-11-14 — two judges visiting as mentors

**When:** <time — fill in>
**Who:** two judges, acting as mentors
**Who from our side:** stefanalbu2010-byte (at least), Luca

> ⚠️ **RECONSTRUCTED FROM ARTIFACTS, NOT FROM THE CONVERSATION.**
> The actual exchange lives only in stefanalbu2010-byte's Claude Code chat,
> which gets cleared. Everything below is inferred from what he committed.
>
> **@stefanalbu2010-byte: before you clear or compact that session, paste the
> judges' own wording here** — what they asked, how they phrased the
> suggestion, and anything they seemed unconvinced by. Their phrasing is the
> part that can't be reconstructed, and it's the part that's useful.

## The topic

**Circadian rhythm, light exposure, and immunity.** The judges raised it; the
team took it seriously enough to research it and start building the same day.

## What came out of it

**Research** — `docs/resources.md` § "Light, circadian rhythm and immunity",
gathered by stefanalbu2010-byte. Honest about evidence quality throughout, which
is the right posture:

- **NASA ISS Solid-State Lighting Assembly (SSLA)** — real flight hardware, three
  modes: General 4500K (day), Pre-sleep 2700K (blue-depleted, less melatonin
  suppression), Phase-shift 6500K (blue-enriched, for shifting sleep). *This is
  the strongest item we have — actual NASA hardware specs, and the first real
  NASA data anywhere in the project.*
- Melatonin suppression peaks around **460 nm** (blue).
- Latent herpesvirus reactivation (VZV, EBV, CMV) rises in spaceflight,
  associated with the daily cortisol rhythm — **association, not causation**.
- DarkSky's own white paper says the health evidence "permits no firm
  conclusions"; the immunity review is **mostly animal evidence**. Quote both
  honestly or not at all.

**Code** — `backend/circadian.py` (216 lines) + endpoints, marked PROVISIONAL and
not yet in `docs/api-spec.md`:

- `GET /astronauts/{id}/circadian`, `PUT .../circadian/sharing`, `PUT .../lighting`
- `sleep_h_last_night` now **derives from the on-board lighting log** instead of
  being invented — sleep stops being a free-floating simulated number
- Extends our **privacy pattern**: `403` on `view=ground` unless the astronaut
  has shared. Same argument as the behavioural check-in
- Action line worded as a suggestion ("Consider pre-sleep lighting (2700K)…"),
  so it stays decision-support, not prescription

## Our decisions

| Their point | Decision | Owner | Status |
|---|---|---|---|
| Circadian rhythm / light / immunity worth modelling | Research done, provisional implementation built | stefanalbu2010-byte | **OPEN — Luca to decide scope, see below** |
| Does circadian become a 6th alerting condition? | — | Luca | **OPEN** |
| Does it go into `docs/api-spec.md`? | — | Luca | **OPEN** — currently PROVISIONAL and outside the contract |

## The open question

The project was narrowed this morning to **two** conditions whose contrast is the
whole demo — `orthostatic` (act on board now) vs `sans` (ground will advise).
Circadian is a third area. It should probably stay a **context layer** (feeding
sleep, and one suggestion-grade nudge) rather than a sixth alerting condition
competing for the judges' attention during the 90-second run.

Counter-argument, and it's a real one: **a judge suggested it.** Judges remember
their own suggestions and look for them. That weighs more than a
self-generated feature.

## Gut read

<did they linger on anything? seem unconvinced anywhere? — fill in>
