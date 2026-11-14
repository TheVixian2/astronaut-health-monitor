# 2026-11-14 — judge 3: sensor accuracy, niche, blackout, history

**When:** <time — fill in>
**Who:** one judge (third visit; separate from `2026-11-14-mentor-judges.md` and `2026-11-14-judge-business.md`)
**Who from our side:** stefanalbu2010-byte (+ <fill in>)

## What we showed them

<fill in — what state the demo was in>

## What they said

As stefanalbu2010-byte typed it right after the visit:

> "another judge came and told us about that we shouldnt think that sensors work 100
> procent of the time so we should analyse sensor acuracy and that we should niche on
> one thing and we told her that we are nieching on the fact that the eye developes
> problems and that develop in long periods of microgravity and she told us that we
> could also focus on the offline or "blackout" part of the program so that we can make
> sure they are safe and know what to do when they have emergencies. also focus on their
> history and incorporate it with reports. also so that we can confirm the spikes we
> have in measurments are felt by the astronaut and make sure there are no errors and
> fix them in their history"

> "she also said to make something that speeds everything up and makes it better than
> whats on the market"

Her points, one per line:

1. Sensors don't work 100% of the time: **analyse sensor accuracy**.
2. **Niche on one thing.** We answered: the eye, SANS developing over long periods in
   microgravity. She accepted that.
3. Also focus on the **offline / blackout** part, so the crew is safe and knows what to
   do in an emergency.
4. Focus on their **history**, built into **reports**.
5. **Confirm that spikes are felt** by the astronaut, catch errors, and **fix them in
   the history**.
6. Make something that **speeds everything up** and is **better than what's on the market**.

## Questions they asked

- <fill in — e.g. did she ask how accurate the watch is?>

## Our decisions

| Their point | Decision | Owner | Status |
|---|---|---|---|
| Analyse sensor accuracy | **Actioned (backend).** Every reading is checked for impossible values, sudden jumps, a stuck sensor and watch dropouts, and stored with a quality flag. `GET /astronauts/{id}/sensors` shows the accuracy summary. Impossible readings never raise an alert. | stefanalbu2010-byte | done on `backend` |
| Niche on one thing | Keep **SANS** as the niche; the other features support safety on long missions. Say it in the pitch: "one problem, done properly". | everyone / dbm711 | open (pitch) |
| Blackout: safe, know what to do | **Actioned (backend).** `PUT /mission/blackout`: everything on board keeps working (monitoring, alerts, explanations, protocols); explanations say "Earth is out of contact… tell a crewmate or the CMO"; Ground gets the held data when contact returns. `GET /protocols` gives the on-board steps. | stefanalbu2010-byte | done on `backend`; web needs a blackout banner (NotKaemy) |
| History built into reports | **Actioned (backend).** `GET /astronauts/{id}/report` builds a ~1.3 KB report from the stored history for the flight surgeon. | stefanalbu2010-byte | done on `backend`; web/presentation can show it |
| Confirm spikes are felt, fix errors in history | **Actioned (backend).** Each vitals alert asks "Do you feel this?". "No" marks the readings as a likely sensor error: **flagged, never deleted**, and left out of the baseline, charts and reports. | stefanalbu2010-byte | done on `backend`; web needs Yes/No buttons (NotKaemy) |
| Speed things up, better than the market | Interpreted as **time to action**: the report shows seconds from alert to the astronaut's answer vs the ~44-min round trip. Market comparison drafted in `presentation/ideas.md`. **@stefanalbu2010-byte: confirm that's what she meant.** | stefanalbu2010-byte / dbm711 | open (confirm meaning) |

## Gut read

<fill in>
