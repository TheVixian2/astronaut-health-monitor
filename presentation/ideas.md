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

## 2026-11-14 — NASA data (gap + plan)

- **Current state: we use no NASA data at all.** The only external feed is NOAA
  GOES proton flux — **NOAA, not NASA** — and it's a cut candidate with `spe`.
  Say "NOAA" in the pitch; misattributing it is exactly what a judge catches.
  Space Apps judging usually weights use of NASA data, so this is a real gap.
- **Best fix, cheapest: parameterise the simulation from NASA's published
  evidence and cite it in the code.** Baseline ranges, the mission-day 7-14
  window, ~70% SANS prevalence, Frisén grading, cabin CO2 levels. Turns "we
  invented these numbers" into "these are NASA figures" — defensible and true.
- **NTRS** (NASA Technical Reports Server) has a real API —
  `https://ntrs.nasa.gov/api/citations/...` — and holds the SANS literature. We
  can honestly say we pulled from a NASA API.
- **NASA OSDR** hosts the Inspiration4 mission data (first open-access commercial
  astronaut health database) with a public API. **Caveat:** heavily omics and
  biospecimen data, not vital-sign time series — it will not drive a monitor.
  Look, but don't plan around it. https://science.data.nasa.gov
- **Not usable in a weekend:** LSDA / LSAH (archived astronaut medical data) —
  formal request, data use agreement, board review.
- **TODO:** check the Space Apps challenge page's own suggested-resources list.
  Judges often expect those specific datasets, and that list beats anything
  found by general search.

## 2026-11-14 — NASA resources (see `docs/resources.md`)

- **Full list of NASA, partner-agency and other resources is in `docs/resources.md`**,
  with what each gives us, which lane uses it, and whether the link was checked.
- **Three cheap fixes for "we use no NASA data":** (1) live Mars light-time from the
  **JPL Horizons API**, (2) measured dose per environment (ISS/Moon/Mars) from **NASA
  OSDR RadLab**, (3) every threshold cites **NASA-STD-3001 / OCHMO technical briefs /
  HRP evidence**, shown as a "source" tooltip.
- **Strong citation for SANS inputs:** NASA's OCHMO Carbon Dioxide technical brief ties
  headache and vision changes to fluid shift and CO2. That is exactly our CO2 + headache
  input. https://www.nasa.gov/wp-content/uploads/2023/12/ochmo-tb-004-carbon-dioxide.pdf
- **Partner agencies to name:** CSA Bio-Monitor (measures the vitals we simulate), ESA
  EchoFinder-2 (also guided by each astronaut's own baseline), CNES EveryWear (the
  closest existing crew app).
- **Slides: no NASA meatball, worm or seal** (needs permission). Use Space Apps branding.
  Don't put "NASA" in the product name.
- **Many teams are on this challenge and already use OSDR RadLab + NOAA.** NASA data is
  the minimum. What sets us apart is SANS, the act-now verdict and astronaut-controlled
  sharing.
- **Official challenge resources found** (now at the top of `docs/resources.md`): NASA's
  *5 Hazards*, *Risks of Human Spaceflight*, *Ongoing HRP Research*, plus two CSA pages
  (radiation monitoring, why science in space). **Name them on a slide and in the
  submission form.** Every alert shows its NASA hazard and HRP risk, so it's easy to
  point at them in the demo.
- **The only targeted partner resource is CSA radiation monitoring.** Cutting `spe`
  completely would drop it. A light radiation display (dose per environment, OSDR RadLab)
  keeps it in.
## 2026-11-14 — light, circadian rhythm and the immune system (from our mentor/judge)

- **A judge raised this, so show we listened.** Mentor/judge explained how blue light
  and circadian rhythm affect the immune system and pointed us to DarkSky
  (https://darksky.org). Sources are in `docs/resources.md` under "Light, circadian rhythm
  and immunity".
- **The chain in one sentence:** blue light (~460 nm) at the wrong time suppresses
  melatonin and shifts the body clock, which hurts sleep, and a disrupted clock
  dysregulates the immune system.
- **Why it's worse in space:** the ISS sees ~16 sunrises a day and all light is
  artificial. Crews sleep ~6 h, and dormant herpesviruses (VZV, EBV, CMV) reactivate
  more often in flight, linked to changes in the daily cortisol rhythm. **Say
  "associated with", not "causes".**
- **NASA already treats light as medicine:** the ISS LED lights have a **pre-sleep mode
  (2700K, blue-depleted)** and a **phase-shift mode (6500K, blue-enriched)**, plus 4500K
  for daytime. Strong slide: "NASA changes the colour of the station's light to protect
  the crew's clock".
- **What we can build cheaply (ask Luca, the check-in would need a new optional field):**
  1. Check-in question: "screens or bright light in the last hour before sleep?"
     and/or bedtime, so we can see whether sleep timing is irregular.
  2. Recommendation text that uses NASA's own modes: "Switch your module to *pre-sleep*
     lighting 1 h before bed; avoid screens." Our `sleep_debt` action already says
     "dim lights 1 h before, no screens", so cite the SSLA there.
  3. Self-check card: "Your sleep timing varied by 2 h this week. Irregular light and
     sleep can weaken immune defence." Decision support, never a diagnosis.
- **Impact on Earth (ties to the CSA "why science in space" resource):** shift workers,
  night-shift nurses, polar crews, and everyone under light pollution. DarkSky's
  guidance (≤3000K, shielded, dimmable) is the Earth-side version of the ISS pre-sleep mode.
- **Be honest about evidence:** most immune findings come from animal studies, and
  DarkSky's own white paper says the health evidence "permits no firm conclusions".
  Saying that out loud makes us look *more* credible to a judge.