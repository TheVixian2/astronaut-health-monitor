# 2026-11-14 — two judges visiting as mentors

**When:** <time — fill in>
**Who:** two judges, acting as mentors
**Who from our side:** stefanalbu2010-byte (at least), Luca

> ⚠️ **Mostly reconstructed from artifacts.** The section below is everything
> stefanalbu2010-byte's Claude Code session actually holds. **The session never
> had the judges' exact wording**, only his one-line summary, so the quotes, the
> time and the gut read can only come from his memory (or Luca's).

## From stefanalbu2010-byte's session (verbatim, 2026-11-14)

His report of the visit, as typed:

> "we had a mentor and judge explain to us how blue light and cicardian rithm
> affect the immune system and told me to research https://darksky.org/"

- **The judge's concrete pointer was DarkSky International (https://darksky.org)**,
  the light-pollution organisation. So they framed it from the **light-at-night**
  side (blue light, melatonin, body clock), not only from sleep.
- "A mentor and judge" could be **one person in both roles or two people**.
  **@stefanalbu2010-byte: confirm**, and fix the "Who" line above.
- **Two follow-up decisions were stefanalbu2010-byte's own, not the judges':**
  1. "the first one could be avoided by just seeing the light system onboard".
     We read the ISS lighting log instead of adding a check-in question.
  2. "make sure it suggests and doesnt violate any ethical concerns". This led to
     private by default, suggestive wording only, the app never switching the
     lights, and no crew comparison.
- DarkSky's site blocks automated reading (403), so the research used DarkSky's PDFs
  found by search. Someone should **open darksky.org in a browser** in case the
  judge expects something specific from it.

**Still to fill in from memory (stefanalbu2010-byte / Luca):** the time, their
exact words, any question they asked, and the gut read below.

## What the judge actually said (via Luca, 2026-11-14)

We were discussing **SANS**. One judge's point:

> The thing that *also* gravely affects circadian rhythm is the **light
> simulation** — on long missions such as Mars it needs to be **closer to
> Earth**.

(Paraphrase from Luca. @stefanalbu2010-byte still to paste the verbatim
exchange from his session.)

### Why this reframes the whole thing

He is not describing a **monitoring** problem. He is describing a
**countermeasure** problem. The lighting system is not a signal to watch — it is
the intervention. That makes circadian a **close-the-loop** feature:

> detect circadian drift -> recommend a lighting mode -> verify sleep improved

which is the strongest demo beat available to us, now effectively requested by a
judge.

### The Mars framing is sharper than the ISS one

- **ISS:** 16 sunrises a day. A bad cue, but a cue.
- **Mars transit:** no external day/night cue at all, for ~9 months. **The
  lighting system is the only zeitgeber the crew has.**
- **Mars surface:** a sol is **24 h 39 m**. The crew must entrain to a 24.65-hour
  day — a known hard problem that wrecked Earth-based rover ops teams who tried it.

So the lighting system is the **last remaining link to Earth's rhythm on a
mission that is otherwise Earth-independent.** That is our thesis, in language a
judge has already shown he cares about.

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
| Circadian rhythm / light / immunity worth modelling | Research done, provisional implementation built | stefanalbu2010-byte | actioned |
| Light simulation must be closer to Earth on long missions | **Reframes circadian as a COUNTERMEASURE, not a condition** — detect drift, recommend a lighting mode, verify sleep improved | Luca | **OPEN — recommended: take it** |
| Does circadian become a 6th alerting condition? | **No** — it is a countermeasure loop, which is better than either a condition or a passive context layer | Luca | **OPEN** |
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
