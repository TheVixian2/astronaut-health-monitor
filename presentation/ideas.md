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
## 2026-11-14 — NASA hazard + risk on every alert (web, NotKaemy)

- **Every alert now names its NASA hazard and official HRP risk, linked to
  nasa.gov** (Self-check, Ground, stream check). Point at it in the demo: "each
  alert maps to a risk NASA itself tracks". Titles are verbatim from
  https://www.nasa.gov/hrp/hazards and https://www.nasa.gov/hrp/risks.
- **Mapping:** `orthostatic` -> *Risk of Cardiovascular Adaptations*;
  `sans` -> *Risk of Spaceflight Associated Neuro-ocular Syndrome (SANS)*;
  `fever` -> *Risk of Altered Immune System Responses*; `sleep_debt` ->
  *Risk of Inadequate Sleep and Irregular Schedules*; `spe` -> *Risk of
  Radiation-Induced Cancers* (NASA lists no separate acute-radiation risk).
- **NASA's list has no CO2 risk.** That supports keeping `co2` only as a SANS
  input (OCHMO-TB-004 links CO2 + headache to SANS) rather than a standalone
  alert. Don't claim a "NASA CO2 risk" on a slide.
- **Behavioural check-in has an exact match:** *Risk of Behavioral Changes and
  Psychiatric Disorders*. Use that title on the PHQ-2 slide.
- **Built (backend): the app reads the station's lighting system instead of asking.**
  No extra question for the crew. It notices that `a2`'s bedtime varied ~2 h and the
  lights stayed bright before sleep on 4 of 7 nights, and *suggests* NASA's pre-sleep
  mode. **Ethics line for the pitch:** "It's private by default: the flight surgeon
  sees it only if the astronaut chooses. It suggests, never orders, and never changes
  the lights by itself." It ties straight back to the under-reporting point.
## 2026-11-14 — judge on business: draft answers (see `events/2026-11-14-judge-business.md`)

A judge asked for UVP / what for / who for / why this product / funding. **Drafts
to tighten, not final claims.**

- **Unique value proposition (one line):** *"An onboard health companion that judges
  each astronaut against their own normal and tells them, in seconds, whether this can
  wait for Houston or needs action now, while the astronaut stays in control of what
  is shared."*
- **What is it for:** spotting health changes early, on board, when the doctor is
  minutes to hours away. The questions it answers are "is this normal *for me*?" and
  "can this wait for Houston?"
- **Who is it for:**
  - *User:* the astronaut, as first responder. The flight surgeon gets a delayed,
    consented view.
  - *Customers:* space agencies running long missions (Artemis, Mars), commercial
    space stations and private astronaut missions.
  - *Earth spin-offs:* Antarctic and polar stations, submarines, offshore rigs,
    remote clinics, which are the same "doctor is far away" problem.
- **Why this product (vs others):** personal baseline instead of population
  thresholds; the act-now vs wait verdict from real light-time; SANS early warning
  between OCT scans; privacy by design (which also fixes under-reporting); built on
  NASA's own hazards, risks and lighting hardware. **Many teams build dashboards, but
  few make a judgement.**
- **"Why use data, not only where":** on the data slide, every source gets a *why*:
  JPL/NASA delay data decides act-now vs wait; NASA HRP risks decide which conditions
  matter; NASA's lighting modes are the countermeasure we recommend; and so on.
- **Funding path (say "possible routes", don't claim any):** prizes from startup
  competitions (Space Apps itself, then space-startup competitions), grants (EU
  Horizon Europe / EIC, ESA business-incubation programmes, check which ones cover
  Romania), space-health research funding (e.g. TRISH, NASA-funded), and later
  investors. Revenue idea: a licence or subscription per crew or per mission for
  commercial stations, plus a B2B version for remote Earth workforces. *Check
  eligibility before naming a specific programme on a slide.*
- **Ahead of the market (closing line):** *"Today the ISS can call Houston. On the
  way to Mars, help is 20 minutes away each way. Longer flights won't just benefit
  from onboard self-assessment, they'll require it."*
- **Eyes, say it precisely:** fluid shift deforms the eye (**SANS**, what we track);
  radiation clouds the lens (**cataracts**, NASA astronaut studies). Both are threats
  to sight that grow with mission length. Don't say "radiation deforms the eyeball".
## 2026-11-14 — circadian rhythm as a main part of the story

- **Thesis line (Luca's framing plus the judge's point):** *"On the way to Mars there
  is no sunrise. The station's lighting is the last link to Earth's rhythm, so we
  turned it into medicine."*
- **It's a countermeasure loop, not just another alarm:** detect body-clock drift →
  suggest a lighting plan built only from NASA's own ISS lighting modes (6500K
  morning, 4500K day, 2700K pre-sleep, dark) → verify that sleep improved. The
  software closes the loop instead of only raising alerts.
- **Demo beat (~20 s, backend ready):** `a2`'s card says "your sleep has been shifting
  about 15 min later each night" → the astronaut taps "I'd like to try this plan" →
  fast-forward 4 nights → "your bedtime varied by 0.2 h (was 1.7 h), you slept 7.1 h
  (was 6.3 h)". The fast-forward is a demo control, so say so.
- **It connects to everything else:** sleep feeds the baseline; body-clock disruption
  is linked to immune changes (judge 1); the lighting plan is a countermeasure the
  crew runs *without* waiting for Houston (the core question); and the astronaut
  chooses whether to follow it, with data private by default (ethics).
- **Environment-aware:** ISS (16 sunrises a day), Moon (a lunar day is 29.5 Earth
  days), Mars transit (no day/night at all) and Mars surface (a sol is 24 h 39 min).
  The longer and farther the mission, the more the lighting matters, which fits
  judge 2's "longer flights will need our system".
- **Keep it honest:** "may help", "linked to". Phase-shift light is normally used with
  flight-surgeon guidance, and the plan says so.
## 2026-11-14 — circadian privacy changed (web, NotKaemy)

- **Update to the ethics line above.** Sleep & lighting data is now **shared with
  the flight surgeon by default**; the astronaut can opt out at any time. The
  "private by default" wording no longer matches the app — don't say it on stage.
- **New privacy point instead: the ship console is a shared screen.** On board,
  the sleep card and the sleep tile stay hidden until the astronaut taps
  "Show my sleep data", and hide again after 2 minutes. Crewmates walking past
  the console don't see each other's sleep. Suggested line: "Your flight surgeon
  can see it, like a doctor would. Your crewmates can't."
- **Keep in mind for Q&A:** the earlier under-reporting argument (crew control
  what goes down, so they report more honestly) is weaker with sharing on by
  default. The opt-out is still there; lean on that if a judge asks.

## 2026-11-14 — real NASA data is now live in the backend

- **NASA JPL Horizons, queried live:** Earth-Mars one-way light time **today is 11.0
  min** (661 s). It ranges from about 3 to 22 min over the orbit. Slide line:
  *"Mars today: 11 min one way (NASA JPL Horizons), up to 22 min. Either way, a
  reply takes longer than an orthostatic episode can wait."* `GET /mission/light-time`.
- **The personal baseline is now real:** the median of six weeks of stored data,
  mission days 7-14 (days 1-6 skipped because of space adaptation). Say: *"Every
  number is compared to this astronaut's own days 7-14, never to an average human."*
- **SANS is explainable:** the score shows its parts (mission day, acuity vs your
  own baseline, Amsler grid, headaches, cabin CO2), so a judge can see *why* it
  rose. One check-in takes a1 from 40 to ~73 on stage.
## 2026-11-14 — judge 3: sensors, blackout, history (see `events/2026-11-14-judge-3-sensors-blackout.md`)

- **Niche, said out loud:** *"We do one thing properly: catching eye problems (SANS) that
  build up over months in microgravity, with everything around it built so an astronaut can
  trust it and act on it far from Earth."*
- **Sensors are not right 100% of the time, and we designed for that.** Every reading is
  checked for impossible values, sudden jumps, a stuck sensor and a watch that stops
  sending. An alert asks *"Do you feel this?"*. If the astronaut says no, the readings are
  marked as a likely sensor error: **flagged, never deleted**, and kept out of the baseline,
  charts and reports. Line: *"The astronaut is the final sensor check."*
- **Blackout demo beat (~15 s):** switch on the blackout (solar conjunction, ~2 weeks with no
  contact) → raise an alert → the app says *"Earth is out of contact for about 13 more days…
  tell a crewmate or the Crew Medical Officer"* and shows the on-board protocol → the Ground
  screen shows nothing → end the blackout → the held alert arrives at Ground.
  *"It keeps the crew safe when nobody on Earth can help."*
- **Reports from history:** one ~1.3 KB plain-language report for the flight surgeon:
  vitals vs the astronaut's own baseline, every alert with the astronaut's answer, sensor
  errors marked and excluded, SANS score, sleep. Small enough for a congested deep-space link.
- **Speed (her "speeds everything up"):** the report shows **time to action**: in testing
  the astronaut answered in **3 s**, vs a **44-min** round trip to Earth.
- **Better than what's on the market (draft, check before saying it):** consumer
  wearables are built for Earth. They assume a phone, the cloud and a doctor nearby.
  Some (e.g. Oura) do use personal baselines, so **don't claim that alone is unique.**
  What they don't have, and we do:
  1. a verdict that knows the light-time delay ("act now" vs "can wait for Houston")
  2. a blackout mode that keeps working and forwards data when contact returns
  3. SANS early warning between OCT scans
  4. the astronaut confirming or correcting sensor errors in their own history
  5. explanations and protocols that need no internet
## 2026-11-14 — TEAM DECISION: mental health is the focus

- **The story now:** *"Months from Earth, in a small crew, the hardest thing to see is how
  someone is really doing. We build a wellbeing profile from many small signals, and the
  astronaut stays in control of who sees it."*
- **NASA grounding (name both on a slide):** HRP risks *Adverse Cognitive or Behavioral
  Conditions and Psychiatric Disorders* and *Inadequate Cooperation, Coordination,
  Communication and Psychosocial Adaptation within a Team*. https://www.nasa.gov/hrp/risks
- **Signals, each vs the astronaut's own normal:** mood, sleep and body clock (from the
  station lighting), NASA's 3-minute reaction test, resting heart rate, and **PHQ-2**, two
  validated questions that use their standard cut-off. *"Validated questions, not
  invented ones."*
- **Astronaut first is the ethics answer:** the astronaut sees it first and chooses whether
  the commander and/or the flight surgeon see it. Only an urgent level is passed on
  automatically, and the astronaut is told it was. Even then: *"the level and which areas,
  never your answers."* This answers the under-reporting problem: people report more
  honestly when they're in control.
- **The crew view separates "it's the mission" from "it's me":** if most of the crew
  sleeps less, it's probably the schedule or environment, and the app tells each astronaut
  that ("it may be the schedule, not you"). Crew-wide trends never name anyone and need at
  least 3 people.
- **Demo (~30 s, repeatable):** a2's profile shows *watch* (mood down after the mission
  midpoint, slower reactions, drifting bedtimes) → a2's check-in → *concern* → a2 taps
  "share with commander" → the commander's console gets a notice. Then show the urgent case
  (a3): commander and flight surgeon notified automatically, and a3 sees "you were notified".
- **Keep SANS, circadian and blackout as supporting features.** One line each: they show
  the same baseline engine works for the body too.
- **Say it:** decision support, never a diagnosis; PHQ-2 is a screen, not a diagnosis.
## 2026-11-14 — Commander and ship's doctor roles (web, NotKaemy)

- **New on-board roles, each with its own login and screen:** the Commander
  sees every crew member's physical and psychological warnings with advice on
  how to help; the ship's doctor sees which medications are due or overdue
  for whom, plus suggestions when an alert fires (always "your decision").
- **Strong demo beat: psychological warnings reach the Commander first.** The
  crew member's console doesn't show them until the Commander presses
  "Tell them now", so hard news comes from a person, in private, not from a
  screen. Physical alerts still go to everyone at once. Suggested line:
  "The app never tells you you're struggling. Your commander does, face to
  face."
- **Expect a privacy question.** The Commander sees everyone's psychological
  data by default (team decision). The earlier argument (crew under-report
  when it can affect flight status) cuts against that. Honest answer: the
  Commander is responsible for the crew's wellbeing on a mission with no ground
  support for 22 minutes; the data is shown with advice to talk in private,
  never to act on someone's duties without the doctor.
- **Medication data is a sample plan** (vitamin D for everyone, melatonin,
  ibuprofen for back pain, decongestant for fluid shift). Say "illustrative";
  don't present the doses as medical guidance.
