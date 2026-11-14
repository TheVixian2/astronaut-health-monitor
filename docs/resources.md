# Resources — NASA first, then partners and others

What we can use, what each one gives us, and which lane would use it.
Status: **found** = link seen working on 2026-11-14 · **check** = open it and confirm before relying on it.

## Official challenge resources (from the challenge page's Resources tab)

Judges expect **these**, so they come before everything else in this file.

| Resource | What it is | How we use it |
|---|---|---|
| **NASA: 5 Hazards of Human Spaceflight** — https://www.nasa.gov/hrp/hazards | HRP overview of radiation, isolation, distance, gravity and hostile closed environments | Our alert `hazard` field already uses these. **Show it in the UI**: each alert names its hazard and links here. |
| **NASA: Risks of Human Spaceflight** — https://www.nasa.gov/hrp/risks | HRP overview of the main risks, with links to detailed reports | Map every condition to its **official HRP risk** (e.g. `sans` maps to the SANS risk) and show the risk name with the alert. Take exact titles from the page. |
| **NASA: Ongoing HRP Research in Space** | Articles on current HRP research | Pitch: "this is the research we build on". Copy the URL from the challenge page. |
| **CSA: Monitoring Radiation for Astronaut Health** | Canadian technology and research for measuring crew radiation exposure | **The only specific partner resource, and it's about radiation.** See the note below. Copy the URL from the challenge page. |
| **CSA: Why Do We Conduct Science Experiments in Space?** | Why ISS research matters for health on Earth too | Pitch: the "it helps people on Earth" impact line |

> **For Luca, about cutting `spe`:** the challenge's only targeted partner resource is
> CSA radiation monitoring. Cutting radiation completely drops the one partner
> resource judges see listed. A light option is a running dose per mission
> environment from **NASA OSDR RadLab** (below), shown as "radiation (CSA / NASA)".
> It needs no `spe` alert and no NOAA feed.
>
> These resources are background pages, not datasets. The data we can actually call
> (JPL Horizons, OSDR RadLab) is listed further down.

## The plan in one line

Today we use **no NASA data** (see `presentation/ideas.md`). These three fixes are
cheap and make "we use NASA data" true:

1. **Live Mars light-time from JPL Horizons** (backend, ~1 h). Compute the real
   Earth-Mars `one_way_delay_s` for today instead of a hard-coded number. The demo
   still runs compressed, but the header shows "Mars today: X min (JPL Horizons)".
2. **Radiation dose per environment from NASA OSDR RadLab** (backend + web). Real
   measured dose for ISS (DOSTEL), lunar orbit (CRaTER) and Mars (MSL-RAD) maps onto
   our `iss | moon | mars` switch, even with `spe` cut.
3. **Every threshold cites a NASA document** (all lanes). Take them from NASA-STD-3001,
   the OCHMO technical briefs and the HRP evidence reports, put the source in a code
   comment, and show it in a "source" tooltip in the UI.

## NASA — data and APIs we can call

| Resource | What it gives us | Use | Lane | Status |
|---|---|---|---|---|
| **JPL Horizons API** — https://ssd-api.jpl.nasa.gov/doc/horizons.html | Ephemeris of Mars (body `499`) seen from Earth (`CENTER='500@399'`). Range gives the light-time. | Real `one_way_delay_s` per day. Call it once at startup and cache it. | backend | found (pick the QUANTITIES code from the docs) |
| **NASA OSDR RadLab** — https://visualization.osdr.nasa.gov/radlab/ | Measured absorbed dose: DOSTEL (ISS), CRaTER (lunar orbit), MSL-RAD (Mars) | Background dose per mission environment; running dose estimate | backend, web | found (via another team's README) |
| **NASA OSDR** — https://osdr.nasa.gov/bio/ · https://science.data.nasa.gov | Inspiration4 (OSD-569/570/571/575 blood data), Twins Study; public API | Pitch evidence that people differ, so personal baselines are needed. It is not vital-sign time series, so it won't drive the monitor. | presentation | found |
| **NTRS** — https://ntrs.nasa.gov | NASA technical reports, with an API | SANS, EIMO and CMO-DA citations; can say "pulled from a NASA API" | presentation | found |
| **NASA Open APIs / DONKI** — https://api.nasa.gov | Space-weather notifications, including solar energetic particle events | Only if `spe` survives. It's NASA, unlike GOES, which is NOAA. | backend | check |

## NASA — documents for thresholds and the story

| Resource | What it gives us | Use | Status |
|---|---|---|---|
| **NASA HRP SANS risk** — https://www.nasa.gov/reference/risk-of-spaceflight-associated-neuro-ocular-syndrome-sans | Official SANS risk description | SANS framing; already in `ideas.md` | found |
| **Human Research Roadmap** — https://humanresearchroadmap.nasa.gov | Risks and **gaps** (e.g. CBS-BMed2: "validate measures… acceptable thresholds") | One slide: "this NASA gap is what we address" | found |
| **HRP hazards / risks** — https://www.nasa.gov/hrp/hazards · https://www.nasa.gov/hrp/risks | The 5 hazards and the risk list | Our `hazard` field already uses the 5 hazards. Cite this. | found |
| **HRP Evidence Reports** (SANS, cardiovascular/orthostatic, behavioral health) | The evidence behind each risk | Source for `orthostatic` and `sans` logic | check (find on humanresearchroadmap.nasa.gov) |
| **OCHMO technical brief: Carbon Dioxide** (OCHMO-TB-004) — https://www.nasa.gov/wp-content/uploads/2023/12/ochmo-tb-004-carbon-dioxide.pdf | Derived from NASA-STD-3001; links headache and vision changes to fluid shift and CO2 | Justifies **CO2 + headache as SANS inputs**. Cabin CO2 values for the simulation. | found |
| **NASA-STD-3001 / OCHMO standards** — https://www.nasa.gov/ochmo/health-operations-and-oversight/hsa-standards/ | Crew health standards (Vol 1 crew health, Vol 2 habitat), career radiation limit | Hard limits that personal baselines never override | found (confirm the current revision) |
| **Reaction Self Test / PVT-B** (NTRS) | NASA's 3-min vigilance self-test flown on ISS, with a 355 ms lapse threshold | Optional self-check feature (web) | found (in `astro-health/docs/research.md`) |
| **Artemis II, CHAPEA, HERA pages** — nasa.gov | Current missions and analogs, including CHAPEA's comm-delay blackout | Pitch relevance; "NASA is testing this exact problem" | found |
| **NASA Image and Video Library** — https://images.nasa.gov | Mission imagery | Slides. **Follow the rules below.** | found |

### NASA branding rules (read before making slides)

- **No NASA "meatball" insignia, "worm" logotype or seal**: they need explicit
  permission. https://www.nasa.gov/nasa-brand-center/nasa-logo-use/
- Use **Space Apps branding** instead: https://spaceappschallenge.org/brand
- Don't put "NASA" in our product name. "NASA-inspired" is acceptable.
- No images of identifiable current astronauts in promotional material.
  https://www.nasa.gov/multimedia/guidelines/index.html

## Partner space agencies (check which ones the challenge page lists)

| Agency | Resource | Use |
|---|---|---|
| **CSA** (Canada) | **Bio-Monitor / Astroskin**, the ISS smart shirt that measures the vitals we simulate | "Our simulated signals are the ones Bio-Monitor really measures" |
| **ESA** | **EchoFinder-2** (AR ultrasound guided to *each astronaut's own* baseline position); Concordia isolation research | Proof that NASA's partners are also moving to personal baselines |
| **CNES** (France) | **EveryWear**, the crew's personal-assistant tablet app on ISS | Closest existing crew app; shows where we go further |
| **JAXA**, **DLR** | Space-medicine research; CIMON (DLR) | Background only |
| **ROSA** (Romanian Space Agency) | Local agency, Bucharest event | Ask the local organizers if they offer data or mentors. Don't claim a partnership. |

## Other resources

| Resource | Use | Note |
|---|---|---|
| **NOAA SWPC GOES protons** | Radiation, only if `spe` survives | Say **NOAA**, not NASA |
| **PHQ-2** | Behavioural check-in (already chosen) | Validated, free to use |
| **Amsler grid** | SANS vision self-test | Standard clinical test |
| **2017 ACC/AHA blood pressure guideline** | Absolute hard limits (e.g. crisis above 180/120) | Personal baselines never override these |
| **PhysioNet** — https://physionet.org | Open heart-rate datasets to make simulated HR look realistic | Optional |
| **Papers**: Barger 2014 (ISS sleep about 6 h), Stahn 2017 (core temperature rises in long spaceflight), Zeitlin 2013 (MSL-RAD cruise dose) | Simulation ranges and pitch numbers | Cited by other teams too |
| **Research report** — `C:\Users\Stefan\Desktop\astro-health\docs\research.md` (stefanalbu2010-byte's PC) | About 80 cited sources on astronaut self-monitoring, with confidence labels | Can be added to the repo if useful |

## Light, circadian rhythm and immunity (suggested by our mentor/judge)

| Resource | What it gives us | Status |
|---|---|---|
| **NASA ISS Solid-State Lighting Assembly (SSLA)**: https://ntrs.nasa.gov/citations/20160005080 · https://ntrs.nasa.gov/api/citations/20200011570/downloads/20200011570.pdf | ISS LED lighting with 3 modes: **General 4500K** (daytime), **Pre-sleep 2700K** (blue-depleted, so less melatonin suppression), **Phase-shift 6500K** (blue-enriched, for shifting sleep). The values differ slightly between documents. | found (check the exact numbers) |
| **DarkSky International** (formerly IDA): https://darksky.org | Light-pollution advocacy. Recommends **3000K or lower**, fully shielded, dimmable lights. **The site blocks scripts**, so open it in a browser. | found (via search) |
| DarkSky: *Artificial Light at Night: State of the Science 2022*: https://darksky.org/app/uploads/2022/06/SOTS-post-final-version-220527.pdf | Blue light's effect on circadian rhythm depends on intensity and timing | found |
| DarkSky: *Blue-rich light white paper*: https://darksky.org/app/uploads/bsk-pdf-manager/8_IDA-BLUE-RICH-LIGHT-WHITE-PAPER.PDF | Blue-rich light at night suppresses melatonin. **It also says the health evidence "permits no firm conclusions"**, so we quote it honestly. | found |
| *Light at night disrupts biological clocks, calendars, and immune function* (Semin. Immunopathol. 2021): https://pmc.ncbi.nlm.nih.gov/articles/PMC8564795 | Review: light at night suppresses melatonin, alters clock genes, and affects innate and adaptive immunity. **Mostly animal evidence.** | found |
| *Protecting the melatonin rhythm through circadian healthy light exposure*: https://www.ncbi.nlm.nih.gov/pmc/articles/PMC4284776/ | Melatonin suppression peaks around **460 nm (blue)** | found |
| *Latent virus reactivation in ISS astronauts* (Frontiers Microbiol. 2019): https://www.frontiersin.org/journals/microbiology/articles/10.3389/fmicb.2019.00016/full | Shedding of herpesviruses (VZV, EBV, CMV) rises in spaceflight. Changes are associated with the **daily cortisol rhythm**. This is an association, not proof of cause. | found |
| *Astroimmunology* review (Nat Rev Immunol 2025): https://vivo.weill.cornell.edu/display/pubid41102553 | Lists abnormal circadian rhythms among the spaceflight factors that disrupt immune cells | found (abstract only) |

## Psychological profile and room beacons (backend, Consensus-checked 2026-11-14)

Sources behind `backend/behavioral.py` and `backend/location.py`. Labels: Strong / Moderate /
Limited, from the study design and population.

| Resource | What it gives us | Evidence |
|---|---|---|
| Levis et al. (JAMA 2020), *Accuracy of the PHQ-2 Alone and in Combination With the PHQ-9*: https://consensus.app/papers/details/w:157a9876-8a4a-412c-9cf2-afaf86faf638/ | PHQ-2 >= 3: sensitivity 0.72, specificity 0.85; PHQ-2 >= 2 then PHQ-9 >= 10 is more specific. Our two-step check-in. | Strong (individual-participant meta-analysis) |
| Levis et al. (BMJ 2019), *Accuracy of PHQ-9 for screening to detect major depression*: https://consensus.app/papers/details/w:94663b88-e58a-44c2-9c99-52d6dca77cba/ | PHQ-9 >= 10 cut-off | Strong (meta-analysis) |
| Manea et al. (J Affect Disord 2016), *Identifying depression with the PHQ-2*: https://consensus.app/papers/details/w:76fdd8e9-e19b-46a4-aed0-c132a3d19e96/ | PHQ-2 accuracy across studies | Strong (meta-analysis) |
| Mitchell et al. (BJPsych Open 2016), *Case finding and screening clinical utility of the PHQ-9 and PHQ-2*: https://consensus.app/papers/details/w:70cc267b-3cce-431f-a33f-84f66ea479cf/ | Good for ruling out, can't confirm a diagnosis: why we say "screen, never a diagnosis" | Strong (meta-analysis, 40 studies) |
| Kroenke et al. (Med Care 2003), *The Patient Health Questionnaire-2*: https://consensus.app/papers/details/w:964a1886-4c6c-4b5f-9d08-6d45328b5ee7/ | The original PHQ-2 and its cut-off of 3 | Moderate (validation study) |
| Kemp et al. (Biol Psychiatry 2010), *Impact of Depression and Antidepressant Treatment on HRV*: https://consensus.app/papers/details/w:e30389d9-5ce4-4936-b967-0e844d977b45/ | Lower HRV with depression; lower still with more severe depression (r = -0.35) | Moderate (meta-analysis, 18 studies, n = 1,080; patients, not astronauts) |
| Grosicki et al. (Am J Physiol Heart 2025), *HRV coefficient of variation during sleep as a digital biomarker*: https://consensus.app/papers/details/w:ed1bcdff-bd5a-4108-a21d-cadc6f40ecb8/ | Night-to-night HRV swings are normal: why the baseline spread has a floor (`REL_FLOOR`) | Moderate (>21,000 wearable users) |
| Basner et al. (PNAS 2013), *Mars 520-d mission simulation reveals protracted crew hypokinesis*: https://consensus.app/papers/details/w:0d1c235d-e6c1-4b06-9c95-290ca74d35d5/ | Mars-500 crews moved less and their sleep timing shifted over the mission: activity and body clock as inputs | Moderate (analog, n = 6, actigraphy) |
| Basner et al. (PLoS ONE 2014), *Psychological and Behavioral Changes during Confinement in a 520-Day Simulated Mission to Mars*: https://consensus.app/papers/details/w:88d789f2-b38a-432e-8a18-bf05940c04ab/ | Mars-500 tracked weekly depression scores, mood, PVT-B and actigraphy, the same kind of inputs as ours; big differences between people (why we use personal baselines) | Limited (analog, n = 6) |
| Stamatis et al. (npj Ment Health Res 2024), *Passively sensed smartphone features for depression and anxiety*: https://consensus.app/papers/details/w:910d0bc5-13b9-4246-a043-89e2ad1fbba6/ | Time at home vs one's own average predicted depression symptoms: the within-person room signal | Moderate (cohort, n = 1,013) |
| Zhang et al. (JMIR mHealth 2021), *Depressive symptom severity and nearby Bluetooth device counts*: https://consensus.app/papers/details/w:109a6da1-6176-4686-8923-d4995e4af9de/ | Bluetooth proximity linked to depressive symptoms | Limited (preliminary longitudinal study) |
| Johannes et al. (PLoS ONE 2015), *Wireless Monitoring of Changes in Crew Relations during Long-Duration Mission Simulation*: https://consensus.app/papers/details/w:77011ac3-e893-47f9-aac4-9969a4700723/ | Proximity sensors tracked crew relations in Mars-500 | Limited (analog, n = 6) |
| Basner et al. (Front Psychol 2026), *Proximity measurements for objective assessments of crew cohesion in an Antarctic space analog*: https://consensus.app/papers/details/w:5459b588-a250-4e76-aaaf-bab5d12fed24/ | Proximity as a crew-cohesion measure in Antarctica | Limited (analog) |
| Cantisani et al. (PNAS 2026), *Social interactions in ICE environments: Antarctic winter teams using wearable sensors*: https://consensus.app/papers/details/w:f3e38452-0a00-4bc3-a4e6-14005fd1d61a/ | More close contact also went with conflict, so only a change from one's own normal counts | Limited (analog, wearable sensors) |
| Bouse et al. (Sensors 2024), *Indoor Localization Using Bluetooth Beacons and RSSI Fingerprinting with Smartwatch*: https://consensus.app/papers/details/w:85a9c2ed-5af8-4417-ba15-63ea6555bdde/ | Watch + beacon room detection about 86-92% accurate, errors mostly in doorways: why two scans must agree | Limited (engineering study) |

## Astronaut vitals in flight: reference values (Consensus-checked 2026-11-14)

Population values for context and hard limits. The score itself compares each astronaut with
their own in-flight days 7-14, which already include the usual flight shifts.

| Resource | What it gives us | Evidence |
|---|---|---|
| Mendes Zambetta et al. (Front Physiol 2024), *Effects of weightlessness on the cardiovascular system*: https://consensus.app/papers/details/w:e8614dd4-ad0f-4558-a9e4-4311d1ba00d9/ | Heart rate about **+3.4 bpm** in spaceflight vs Earth; HRV and baroreflex sensitivity generally lower | Moderate (systematic review + meta-analysis, 62 studies, n = 963, flight and analogs) |
| Otsuka et al. (Heliyon 2016), *Long-term exposure to microgravity alters the time structure of HRV*: https://consensus.app/papers/details/w:8f3d2dcc-09dd-467d-94dc-b5b74f0656ed/ | HRV keeps its 24-h rhythm on 6-month ISS flights; a ~90-min component grows about 3x | Limited (ISS, n = 10) |
| Stahn et al. (Sci Rep 2017), *Increased core body temperature in astronauts during long-duration missions*: https://consensus.app/papers/details/w:43743ce7-1f34-42dc-9c1a-ff80aa51cef1/ | Resting core temperature rises about **1 °C over 2.5 months**; it rises higher and faster during exercise | Limited (ISS astronauts, small n) |
| Wydotis et al. (Am J Physiol Regul 2026), *Body heat accrual and cognition*: https://consensus.app/papers/details/w:22fe5515-86f8-4619-896a-5534fc86ac20/ | Core ~37 °C on Earth → ~38 °C after 2.5 months in flight; **~38.5 °C may start cognitive decline**; over 40 °C possible in exercise | Limited (review) |
| Gimunová et al. (npj Microgravity 2026), *Spaceflight and thermoregulation: a systematic review*: https://consensus.app/papers/details/w:a5826aef-0e22-4591-bbc4-e35c534de82e/ | Raised core temperature on long missions is a consistent finding | Moderate (systematic review, 20 studies) |
| Jones et al. (Nature 2024), *Molecular and physiological changes in the SpaceX Inspiration4 civilian crew*: https://consensus.app/papers/details/w:ccf73407-b07e-4490-8df9-1802a0d1d99c/ | Real in-flight **smartwatch wearable data** from 4 civilian astronauts (3 days) | Limited (n = 4, short flight) |
| Sanders et al. (npj Microgravity 2024), *Inspiration4 data access through NASA OSDR*: https://consensus.app/papers/details/w:b810f9a8-5cba-490f-90bd-e793459eb5df/ | How to download the Inspiration4 data from **NASA's Open Science Data Repository** (GLOpenAPI) | NASA open data |
| Overbey et al. (Nature 2024), *The Space Omics and Medical Atlas (SOMA)*: https://consensus.app/papers/details/w:2349be28-69d2-4bba-a52f-0d1f8deeac4b/ | Open atlas of clinical and omics data: NASA Twins Study, JAXA, Inspiration4, Axiom, Polaris | Strong as a data source |

## Competition note

Lots of teams are on this same challenge, and several already use **NASA OSDR
RadLab + NOAA GOES** (e.g. "Aurora", https://github.com/fabriciojunio/aurora-astronaut-health)
or cite NASA-STD-3001 and the HRP evidence books (e.g. "AURA",
https://github.com/quirocode/aura-space-health-monitor). Using NASA data is the minimum.
What sets us apart is **SANS as the centrepiece**, the **"act on board vs. wait for
Houston" verdict**, and the **astronaut controlling what is shared with the ground**.
