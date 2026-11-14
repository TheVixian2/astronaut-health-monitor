"""Live Earth-Mars light time from NASA JPL Horizons.

Asks Horizons for Mars (body 499) as seen from Earth's centre (500@399) with
QUANTITIES=20 (observer range), and converts the range to one-way light time.
Never raises: on any failure it returns None and the configured default stays.
"""

import datetime as dt
import logging
from typing import Optional

import httpx

log = logging.getLogger("horizons")

API_URL = "https://ssd.jpl.nasa.gov/api/horizons.api"
DOCS_URL = "https://ssd-api.jpl.nasa.gov/doc/horizons.html"
AU_KM = 149_597_870.7
LIGHT_KM_S = 299_792.458


async def mars_one_way_light_time_s(day: dt.date) -> Optional[int]:
    params = {
        "format": "json", "COMMAND": "'499'", "OBJ_DATA": "'NO'", "MAKE_EPHEM": "'YES'",
        "EPHEM_TYPE": "'OBSERVER'", "CENTER": "'500@399'", "QUANTITIES": "'20'",
        "START_TIME": f"'{day.isoformat()}'", "STOP_TIME": f"'{(day + dt.timedelta(days=1)).isoformat()}'",
        "STEP_SIZE": "'1 d'",
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(API_URL, params=params)
            r.raise_for_status()
            text = r.json()["result"]
        first_row = text.split("$$SOE", 1)[1].strip().splitlines()[0]
        delta_au = float(first_row.split()[2])  # "2026-Nov-14 00:00  1.3243620  -14.71"
        return round(delta_au * AU_KM / LIGHT_KM_S)
    except Exception as e:
        log.warning("JPL Horizons light-time lookup failed (%s); keeping the default", e)
        return None
