# Written with AI assistance (Claude Code, Anthropic) and reviewed by the team. See README "Use of AI".
"""Sensor data quality: sensors don't work 100% of the time.

Every sample gets a quality flag before it can feed the baseline, a chart or a report:
  ok           plausible and consistent
  suspect      a sudden jump, a stuck sensor, or a reading the astronaut hasn't confirmed
  implausible  outside what a human body can do: never used for anything
  artifact     the astronaut said they didn't feel it: excluded from history, never deleted
The watch heart rate is also checked for dropouts (no data) and flatlines (a stuck
sensor or a watch off the wrist). All ranges are PLACEHOLDERS pending tuning.
"""

from collections import Counter, deque
from dataclasses import dataclass, field
from typing import Optional

PLAUSIBLE = {  # what a human body can physically do
    "heart_rate_bpm": (25, 220),
    "spo2_pct": (70, 100), "temp_c": (33.0, 42.0), "resp_rate_bpm": (4, 60),
    "hrv_sdnn_ms": (5, 250), "active_min": (0, 1440),
}
MAX_JUMP_PER_TICK = {  # change in one 3 s tick that is more likely a sensor glitch than the body
    "heart_rate_bpm": 35,
    "spo2_pct": 6, "temp_c": 1.0, "resp_rate_bpm": 10,
    "hrv_sdnn_ms": 40, "active_min": 1440,  # the active-minutes counter resets at midnight
}
FLATLINE_TICKS = 20  # identical watch heart rate for 60 s
RECENT_TICKS = 1200  # ~1 h of per-tick results for the accuracy summary


@dataclass
class SignalCheck:
    field: str
    status: str  # ok | spike | implausible | flatline | dropout
    detail: str
    source: str  # real | simulated


@dataclass
class SensorMonitor:
    prev: dict = field(default_factory=dict)
    same_hr_ticks: int = 0
    last_real_hr: Optional[float] = None
    recent: deque = field(default_factory=lambda: deque(maxlen=RECENT_TICKS))
    last_checks: list = field(default_factory=list)

    def check(self, v: dict, hr_source: str, watch_dropout: bool) -> tuple[str, list[SignalCheck]]:
        """Check one tick. Returns the sample's quality flag and a per-signal result."""
        checks = []
        for f, (lo, hi) in PLAUSIBLE.items():
            value, source = v[f], (hr_source if f == "heart_rate_bpm" else "simulated")
            status, detail = "ok", "Within range and consistent."
            if not lo <= value <= hi:
                status, detail = "implausible", f"{value:g} is outside what a body can do ({lo}-{hi})."
            elif f in self.prev and abs(value - self.prev[f]) > MAX_JUMP_PER_TICK[f]:
                status, detail = "spike", (f"Jumped from {self.prev[f]:g} to {value:g} in 3 s; "
                                           f"worth confirming with how you feel.")
            if f == "heart_rate_bpm":
                if watch_dropout:
                    status, detail = "dropout", "No data from the watch for over 10 s; using the simulated value."
                elif hr_source == "real":
                    self.same_hr_ticks = self.same_hr_ticks + 1 if value == self.last_real_hr else 0
                    self.last_real_hr = value
                    if self.same_hr_ticks >= FLATLINE_TICKS and status == "ok":
                        status, detail = "flatline", "The watch has reported exactly the same value for a minute: check its contact."
            checks.append(SignalCheck(f, status, detail, source))
        self.prev = {f: v[f] for f in PLAUSIBLE}
        statuses = {c.status for c in checks}
        quality = ("implausible" if "implausible" in statuses
                   else "suspect" if statuses & {"spike", "flatline"} else "ok")
        self.recent.append(Counter(c.status for c in checks if c.status != "ok"))
        self.last_checks = checks
        return quality, checks

    def recent_counts(self) -> Counter:
        total = Counter()
        for c in self.recent:
            total.update(c)
        return total
