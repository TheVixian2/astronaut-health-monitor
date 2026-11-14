# Presentation ideas

Append freely. Dated bullets. Unsorted is fine.

## 2026-11-14

- **The core question, in one sentence:** "Can this wait for Houston, or do I act
  now?" Everything the software does serves that one question.
- **Two conditions, opposite verdicts.** `orthostatic` (`act_within_s` 600) vs
  Mars round-trip (up to ~44 min) → *act on board now*. SANS is slow-onset →
  *ground will advise*. One demo proves the system makes a judgement rather than
  just raising alarms. Don't demo only one condition — the contrast is the point.
- **One physiological story, not five.** Headward fluid shift in microgravity
  causes both cardiovascular deconditioning and the eye swelling behind SANS.
  Two related conditions read as an argument; five unrelated ones read as a
  feature list.
- **Personal baseline isn't a design choice for SANS, it's the only thing that
  works.** There is no population threshold for "your vision is distorted" —
  only your own pre-flight result.
- **SANS is NASA's leading spaceflight-related health risk**, classed as a Mars
  "red risk", and ~70% of ISS astronauts show swelling at the back of the eye.
  Sources: https://www.nasa.gov/reference/risk-of-spaceflight-associated-neuro-ocular-syndrome-sans
  and https://www.scientificamerican.com/article/nasas-mars-plans-complicated-by-eye-problems-during-long-spaceflights/
- **NASA's own term for the premise:** "Earth-independent medical operations."
  Use it — it shows the problem is one NASA names, not one we invented.
- **Light-time is a hard physical ceiling, not a latency problem.** Worth saying
  explicitly: no amount of engineering removes it.
- **Say the demo delay is compressed.** `Mars · 22 min one-way (demo: 20 s)` on
  screen. Keep the real figure permanently in the Ground header so the stakes
  stay visible after the countdown ends.
- **Decision support, never a diagnosis.** Say this out loud before a judge asks.
- **Don't oversell the radiation data if `spe` is cut** — and if it's kept, note
  that GOES measures near Earth and is a stand-in for deep space.

## 2026-11-14 — SANS measurement and countermeasures

- **Positioning, say it exactly like this:** this does not replace OCT. It is the
  *between-scans early-warning layer* — the cheap daily self-test that tells the
  crew when it's worth doing an OCT scan or escalating to the ground. Judges
  can't poke holes in that; "our tablet diagnoses SANS" they can.
- **Why the gap is real:** strict SANS diagnosis needs optic disc edema visible
  on fundoscopy, which catches only ~15% of astronauts — but OCT shows *most*
  long-duration crew have some disc swelling fundoscopy misses. OCT is
  infrequent, needs scheduling and needs an expert to read it. On Mars there is
  no expert at the other end of a 22-minute link.
- **What's actually on station:** OCT (crew-operated, ground-guided), ocular
  ultrasound, tonometry. MRI — which shows globe flattening — is post-flight only.
- **Clinical picture (for the slide):** optic disc edema graded on the Frisén
  scale, globe flattening, choroidal and retinal folds, hyperopic refractive
  shift, cotton wool spots.
- **Close the loop — the strongest demo beat.** Detect trend -> recommend
  countermeasure -> re-test -> show the trend flatten. The software prescribes
  and then *verifies*, rather than just alarming.
- **Countermeasures under investigation (say "under investigation", not
  "proven"):** Lower Body Negative Pressure, venoconstrictive thigh cuffs,
  B-vitamin supplementation (one-carbon metabolism pathway implicated in
  severity), and "space anticipation glasses" — which are correction, not
  prevention.
- **Don't overclaim mechanism.** It is still unclear whether the swelling is true
  papilledema from raised intracranial pressure; the asymmetry between eyes
  doesn't fit that cleanly.
- **Persistence is a good closing line:** most signs resolve after return, but
  globe flattening and refractive change have persisted **over 12 years** in some
  astronauts.
- Sources: https://pmc.ncbi.nlm.nih.gov/articles/PMC7005826 ·
  https://pmc.ncbi.nlm.nih.gov/articles/PMC6043524 ·
  https://pmc.ncbi.nlm.nih.gov/articles/PMC8085766 ·
  https://cm.healio.com/news/ophthalmology/20180515/nasa-research-progresses-toward-understanding-ocular-consequences-of-longduration-spaceflights

## 2026-11-14 — behavioural health check-in

- **The AI's job is compression, not assessment.** Deep-space comms are
  bandwidth-constrained, so the questionnaire is summarised before transmission
  rather than sent raw. That is a real operational practice and a defensible
  reason for an LLM to be in the loop at all.
- **The astronaut reviews the summary and decides what goes to ground.**
  Flow is: questionnaire -> AI summary -> astronaut reviews -> astronaut
  chooses -> transmit. `share_with_ground` already exists in `POST /checkin`.
- **Why that matters — the strongest point here.** Mental health is the one area
  where crew have a real incentive to underreport: in aerospace medicine,
  disclosing psychological symptoms can affect flight status, so people don't
  disclose. A system where the crew member controls what goes down may produce
  *more* honest reporting than one that transmits automatically. Non-obvious,
  and it shows we understood the domain rather than just built a form.
- **Use PHQ-2** — two validated screening questions — not invented ones. Free,
  and anyone clinical in the room will notice the difference.
- **Seed six weeks of history** via `--seed-baseline` so a declining trend is
  visible immediately. Bi-weekly cadence is otherwise undemoable in a 2-day event.
- Decision support bites hardest here: the summary describes what was reported
  and how it is trending. It never names a condition.
