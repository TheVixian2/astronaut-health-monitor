# NASA data and resources we use

Everything from NASA (and partner agencies) in Dr. Galactic, what kind of use it is,
and where it lives in the code. Paste-ready for the submission's **NASA Data** field.

Legend: 🟢 **live NASA data** in the stream · 🔵 **NASA standard or finding built into
the logic or the simulation** · 📄 **cited** (pitch, docs, on-screen links) but not
computed from.

## 🟢 Live NASA data

| Source | What we take | Where |
|---|---|---|
| [NASA ISS Live telemetry](https://lightstreamer.com/customer-story/how-nasa-is-using-lightstreamer/) (public Lightstreamer feed, adapter `ISSLIVE`) | Real ISS cabin air: US Lab + Node 3 CO2 partial pressure, O2, cabin pressure, cabin temperature. It is the cabin our simulated crew lives in. | `backend/iss_live.py` → `GET /environment`, SSE `environment`, Commander → Habitat |
| [NASA JPL Horizons API](https://ssd-api.jpl.nasa.gov/doc/horizons.html) | Today's real Earth–Mars light time (661 s on 2026-11-14). Drives the "can this wait for Mission Control?" verdict when `AHM_LIVE_LIGHT_TIME=1`. | `backend/horizons.py` → `GET /mission/light-time` |

## 🔵 NASA standards and findings in the logic

| Source | What we use | Where |
|---|---|---|
| [NASA-STD-3001 Tech Brief OCHMO-TB-004, Carbon Dioxide](https://www.nasa.gov/wp-content/uploads/2023/12/ochmo-tb-004-carbon-dioxide.pdf) | Cabin CO2 limit **3 mmHg** (1-hour average); headaches from ~2.8–4.5 mmHg; keep the 7-day average < 2.5 mmHg for < 1 % headache risk. Sets the cabin status and the Commander's CO2 suggestion. | `backend/iss_live.py` |
| [NASA-STD-3001 Tech Brief OCHMO-TB-016, Behavioral Health and Performance](https://www.nasa.gov/wp-content/uploads/2023/12/ochmo-tb-016-behavioral-health.pdf) | Missions beyond 6 months or beyond low Earth orbit should add minimally obtrusive, objective measures of psychological state; a pre-flight baseline per astronaut compared in flight (our personal-baseline design); private hygiene compartment and individual quarters (why hygiene is never tracked). | Whole design; `backend/habitat.py` |
| [ISS Solid-State Lighting Assembly (NTRS 20160005080)](https://ntrs.nasa.gov/citations/20160005080) | Lighting modes: general 4500 K, pre-sleep 2700 K, phase-shift 6500 K. The sleep/body-clock feature reads the (simulated) lighting log and suggests modes. | `backend/circadian.py`, Self-check → Sleep & light |
| [NASA HRP: 5 Hazards of Human Spaceflight](https://www.nasa.gov/hrp/hazards) and [Risks of Human Spaceflight](https://www.nasa.gov/hrp/risks) | Every flag is tagged with its NASA hazard and HRP risk, linked on screen. | `web/common.js` (`HAZARDS`, `HRP_RISKS`), `backend/behavioral.py` |
| PVT-B, the 3-minute reaction test in NASA's behavioral-health standard measures ([Basner et al. 2011](https://pmc.ncbi.nlm.nih.gov/articles/PMC3197786)) | Reaction-test check-in; a lapse = response over 355 ms. | `backend/behavioral.py` |
| [Bell, NASA HRP Investigators' Workshop 2026 (NTRS 20260002661)](https://ntrs.nasa.gov/api/citations/20260002661/downloads/Bell_APEX_IWS_2026_final.pdf): HERA campaigns 4–7 and SIRIUS-19/21 | Positive affect declines over time in isolation, so a2's mood is simulated drifting down after the mission midpoint. No reported cases of clinical depression, so we screen, never diagnose. | `tools/simulate_crew.py` (a2's decline), wording everywhere |
| [Dev et al. 2024, Frontiers in Physiology 15:1451269](https://doi.org/10.3389/fphys.2024.1451269): 25 ISS astronauts, 6-month missions | Cognitive performance generally stable over the mission, so healthy crew's simulated reaction times stay flat and only a struggling astronaut drifts. | `tools/simulate_crew.py` |
| [NASA Mars architecture: crew operations for transit to Mars (NTRS 20230012629)](https://ntrs.nasa.gov/api/citations/20230012629/downloads/Overview%20of%20Crew%20Operations%20for%20Transit%20to%20Mars%20V5.pdf) | Mission framing: a crew of **four** on an **850-day** Mars mission (our crew a1–a4). | `backend/engine.py` (CREW), pitch |

## 📄 Cited, not computed from (yet)

| Source | What it says | Used in |
|---|---|---|
| [Stuster 2010, ISS astronaut journals (NTRS 20100026549)](https://ntrs.nasa.gov/citations/20100026549) | Morale dips in the third quarter of a mission. | Pitch; planned: mission timeline marker |
| [Barger et al. 2014, Lancet Neurology](https://pmc.ncbi.nlm.nih.gov/articles/PMC4188436) (NASA-funded): astronaut sleep by actigraphy | Chronic short sleep in flight; frequent sleep-medication use. | Pitch; planned: baseline calibration |
| [NASA Behavioral Medicine Evidence Report 2025 (NTRS 20250001454)](https://ntrs.nasa.gov/citations/20250001454) | Risk of behavioral conditions rises with mission length; exploration-class countermeasures not yet validated. | Pitch |
| NASA Integrated Medical Model estimates ([AsMA 2017 poster](https://www.asma.org/asma/media/AsMA/pdf-meetings/2017%20Annual%20Meeting/posters-2017/201705_458_Friedman.pdf)) | Shuttle-era symptom incidence: anxiety 0.832, depression 0.139 per person-year; no NASA astronaut has met DSM criteria. | Pitch |
| [Bell et al. 2025, Frontiers in Psychology 15:1350630](https://doi.org/10.3389/fpsyg.2024.1350630): 64 analog crew members | Support from crewmates was linked to lower evening stress. Background for the shared-room-time signal (which stays display-only). | Pitch, Habitat note |
| [NASA Life Sciences Portal](https://www.nasa.gov/hrp/nlsp/): HERA Standard Measures (PANAS, GHQ) | NASA collects exactly the measures our tool tracks. **Access by request only**, not available for the hackathon: "NASA has this data; our tool would feed it." | Pitch |

## Space Apps challenge resources

NASA *5 Hazards of Human Spaceflight*, *Risks of Human Spaceflight*, *Ongoing HRP
Research in Space*; CSA *Monitoring Radiation for Astronaut Health* and *Why Do We
Conduct Science Experiments in Space?* (listed on the challenge's Resources tab).

## Non-NASA references (for the References field)

PHQ-2: Kroenke, Spitzer & Williams, *Medical Care* 2003. HRV and depression: Kemp et
al., *Biological Psychiatry* 2010. Mars-500 activity: Basner et al., *PNAS* 2013.
ISS Live telemetry IDs: the open-source [ISS Mimic](https://github.com/ISS-Mimic/Mimic)
project. Python client: `lightstreamer-client-lib`. Charts: Chart.js.
