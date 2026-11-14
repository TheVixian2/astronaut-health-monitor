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

## Competition note

Lots of teams are on this same challenge, and several already use **NASA OSDR
RadLab + NOAA GOES** (e.g. "Aurora", https://github.com/fabriciojunio/aurora-astronaut-health)
or cite NASA-STD-3001 and the HRP evidence books (e.g. "AURA",
https://github.com/quirocode/aura-space-health-monitor). Using NASA data is the minimum.
What sets us apart is **SANS as the centrepiece**, the **"act on board vs. wait for
Houston" verdict**, and the **astronaut controlling what is shared with the ground**.
