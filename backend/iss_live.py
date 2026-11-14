"""Live cabin environment from NASA's ISS Live telemetry (real data, PROVISIONAL).

NASA publishes ISS telemetry through a public Lightstreamer server (push.lightstreamer.com,
adapter ISSLIVE). We read the US Lab and Node 3 cabin sensors and use them as the cabin our
simulated crew lives in. NASA-STD-3001 limits cabin CO2 to 3 mmHg (1-hour average) because
headaches start around 2.8-4.5 mmHg (NASA OCHMO-TB-004).

Never blocks the app: the client runs on its own threads; if the feed is unreachable, the
environment reads "unavailable" and nothing else changes. AHM_ISS_LIVE=0 turns it off.
"""

import logging
import os
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Optional

log = logging.getLogger("ahm")

ITEMS = {  # ISS Live telemetry id -> our name (ids from the ISS Mimic project's telemetry list)
    "USLAB000055": "ppco2_lab_mmhg",     # LAB_MCA_ppCO2 (torr = mmHg)
    "NODE3000003": "ppco2_node3_mmhg",   # Node_3_MCA_ppCO2
    "USLAB000053": "ppo2_lab_mmhg",      # LAB_MCA_ppO2
    "USLAB000058": "cabin_pressure_mmhg",  # LAB_PCA_Cabin_Pressure
    "USLAB000059": "cabin_temp_c",       # LAB1P6_CCAA_In_T1 (cabin air into the Lab air conditioner)
}
CO2_LIMIT_MMHG = 3.0          # NASA-STD-3001, 1-hour average
CO2_HEADACHE_7D_MMHG = 2.5    # keeps headache risk below 1% (OCHMO-TB-004)
SOURCE_URL = "https://www.nasa.gov/wp-content/uploads/2023/12/ochmo-tb-004-carbon-dioxide.pdf"

latest: dict[str, float] = {}
updated: dict[str, datetime] = {}
_co2: deque[tuple[float, float]] = deque()  # (monotonic time, max cabin ppCO2)
_client = None
# Demo only (POST /debug/cabin): a CO2 value that replaces the live reading until it expires,
# so the "can't wait for Earth" alarm can be shown. Always labelled, never mixed with real data.
_override: Optional[tuple[float, float]] = None  # (ppCO2 mmHg, monotonic expiry)


def set_override(ppco2_mmhg: Optional[float], minutes: float = 5) -> None:
    global _override
    _override = None if ppco2_mmhg is None else (ppco2_mmhg, time.monotonic() + minutes * 60)


def _iss_time(hours_of_year: str) -> datetime:
    now = datetime.now(timezone.utc)
    # ISS Live counts hours from day 1 of the year (day-of-year is 1-based), so day 1 = 24 h.
    return datetime(now.year, 1, 1, tzinfo=timezone.utc) + timedelta(hours=float(hours_of_year) - 24)


def _on_update(item: str, value: Optional[str], stamp: Optional[str]) -> None:
    if value is None or item not in ITEMS:
        return
    try:
        latest[ITEMS[item]] = float(value)
        updated[ITEMS[item]] = _iss_time(stamp) if stamp else datetime.now(timezone.utc)
    except ValueError:
        return
    co2 = [latest[k] for k in ("ppco2_lab_mmhg", "ppco2_node3_mmhg") if k in latest]
    if co2:
        t = time.monotonic()
        _co2.append((t, max(co2)))
        while _co2 and t - _co2[0][0] > 3600:
            _co2.popleft()


def start() -> None:
    global _client
    if os.getenv("AHM_ISS_LIVE", "1") == "0" or _client is not None:
        return
    try:
        from lightstreamer.client import LightstreamerClient, Subscription, SubscriptionListener

        class Listener(SubscriptionListener):
            def onItemUpdate(self, update):
                _on_update(update.getItemName(), update.getValue("Value"), update.getValue("TimeStamp"))

        _client = LightstreamerClient("https://push.lightstreamer.com", "ISSLIVE")
        sub = Subscription("MERGE", list(ITEMS), ["TimeStamp", "Value"])
        sub.setRequestedSnapshot("yes")
        sub.addListener(Listener())
        _client.subscribe(sub)
        _client.connect()
        log.info("ISS Live: subscribed to %d cabin sensors", len(ITEMS))
    except Exception:
        log.exception("ISS Live unavailable; the cabin environment stays empty")


def stop() -> None:
    if _client is not None:
        try:
            _client.disconnect()
        except Exception:
            pass


def snapshot() -> dict:
    co2_now = max([latest[k] for k in ("ppco2_lab_mmhg", "ppco2_node3_mmhg") if k in latest], default=None)
    avg = round(sum(v for _, v in _co2) / len(_co2), 2) if _co2 else None
    demo = _override is not None and time.monotonic() < _override[1]
    if demo:
        co2_now = avg = _override[0]
    status = ("unavailable" if co2_now is None else
              "above_limit" if (avg or co2_now) > CO2_LIMIT_MMHG else
              "elevated" if (avg or co2_now) > CO2_HEADACHE_7D_MMHG else "ok")
    return {
        "source": ("DEMO OVERRIDE, not real ISS data (POST /debug/cabin)" if demo
                   else "NASA ISS Live telemetry (US Lab and Node 3 cabin sensors)"),
        "demo_override": demo,
        "updated_at": max(updated.values()) if updated else None,
        **{k: (round(v, 2) if k in latest else None) for k, v in ((n, latest.get(n)) for n in ITEMS.values())},
        "co2_mmhg": round(co2_now, 2) if co2_now is not None else None,
        "co2_1h_avg_mmhg": avg,
        "co2_limit_mmhg": CO2_LIMIT_MMHG,
        "status": status,
        "note": ("Real, live cabin data from the International Space Station, used as the cabin our "
                 "simulated crew lives in. NASA-STD-3001 limits CO2 to 3 mmHg (1-hour average); "
                 "headaches start around 2.8-4.5 mmHg."),
        "source_url": SOURCE_URL,
    }
