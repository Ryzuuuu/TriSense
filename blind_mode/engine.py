# blind_mode/engine.py
# -----------------------------------------------------------------------------
# Blind Mode decision engine (hardware free, fully unit testable).
#
# Fixes over the original loop:
#   * closing speed uses the REAL time between readings. The old loops divided
#     by a hard coded 0.1 s even though reading three sensors (plus, in the
#     ModeManager adapter, blocking motor pulses) made the true interval much
#     longer, which inflated speeds and produced false "imminent" alerts.
#   * readings are median filtered and out of range echoes are rejected, so a
#     single bad echo no longer looks like an object teleporting toward you.
#   * speed is smoothed and a small dead band ignores sensor jitter.
#   * a PROXIMITY alert fires for close obstacles even when nothing is moving.
#     The old logic only used time to collision, so a user standing still with
#     a wall 20 cm in front of them got no warning at all.
# -----------------------------------------------------------------------------

from collections import deque
from dataclasses import dataclass
from typing import Dict, List, Optional

try:
    from blind_mode import config as _cfg
except ImportError:  # scripts run from inside blind_mode/
    import config as _cfg

MIN_VALID_CM = getattr(_cfg, "MIN_VALID_CM", 2.0)
MAX_VALID_CM = getattr(_cfg, "MAX_VALID_CM", 400.0)
SPEED_DEADBAND_CM_S = getattr(_cfg, "SPEED_DEADBAND_CM_S", 15.0)
SPEED_EMA_ALPHA = getattr(_cfg, "SPEED_EMA_ALPHA", 0.5)
TTC_ALERT_S = getattr(_cfg, "TTC_ALERT_S", 1.5)
TTC_SPEAK_S = getattr(_cfg, "TTC_SPEAK_S", 1.0)
PROXIMITY_WARN_CM = getattr(_cfg, "PROXIMITY_WARN_CM", 60.0)
PROXIMITY_DANGER_CM = getattr(_cfg, "PROXIMITY_DANGER_CM", 30.0)
STALE_AFTER_S = getattr(_cfg, "STALE_AFTER_S", 0.6)


def ttc_to_pulse_ms(ttc: Optional[float], threshold: float = TTC_ALERT_S) -> Optional[int]:
    """Same tiers as haptic.get_alert_intensity: <0.5 s 500 ms, <1.0 s 300 ms, <1.5 s 150 ms."""
    if ttc is None:
        return None
    if ttc < 0.5:
        return 500
    if ttc < 1.0:
        return 300
    if ttc < threshold:
        return 150
    return None


def proximity_to_pulse_ms(distance: Optional[float]) -> Optional[int]:
    if distance is None:
        return None
    if distance < PROXIMITY_DANGER_CM:
        return 300
    if distance < PROXIMITY_WARN_CM:
        return 150
    return None


@dataclass
class SensorState:
    label: str
    distance: Optional[float]
    speed: Optional[float]
    ttc: Optional[float]
    pulse_ms: Optional[int]
    reason: Optional[str]  # "ttc", "proximity" or None


class SensorTrack:
    """Filtered distance, speed and time to collision for one ultrasonic sensor."""

    def __init__(self, label: str, window: int = 3):
        self.label = label
        self._raw = deque(maxlen=window)
        self._last_d: Optional[float] = None
        self._last_t: Optional[float] = None
        self._speed: Optional[float] = None

    def update(self, distance: Optional[float], t: float) -> SensorState:
        valid = distance is not None and MIN_VALID_CM <= distance <= MAX_VALID_CM
        if valid:
            self._raw.append(float(distance))
        elif self._last_t is not None and t - self._last_t > STALE_AFTER_S:
            # sensor has been silent for a while: forget the old state
            self._raw.clear()
            self._last_d = self._last_t = self._speed = None

        if not self._raw:
            return SensorState(self.label, None, None, None, None, None)

        d = sorted(self._raw)[len(self._raw) // 2]  # median filter
        if valid and self._last_d is not None and self._last_t is not None and t > self._last_t:
            inst = (self._last_d - d) / (t - self._last_t)
            self._speed = inst if self._speed is None else SPEED_EMA_ALPHA * inst + (1 - SPEED_EMA_ALPHA) * self._speed
        if valid:
            self._last_d, self._last_t = d, t

        speed = self._speed
        ttc = d / speed if (speed is not None and speed > SPEED_DEADBAND_CM_S and d > 0) else None

        p_ttc = ttc_to_pulse_ms(ttc)
        p_prox = proximity_to_pulse_ms(d)
        pulse, reason = None, None
        if p_ttc is not None or p_prox is not None:
            if (p_ttc or 0) >= (p_prox or 0):
                pulse, reason = p_ttc, "ttc"
            else:
                pulse, reason = p_prox, "proximity"
        return SensorState(self.label, d, speed, ttc, pulse, reason)


class BlindEngine:
    """Turns timestamped readings from all sensors into haptic and speech decisions."""

    def __init__(self, labels=("left", "center", "right")):
        self.tracks = {lb: SensorTrack(lb) for lb in labels}

    def step(self, readings: Dict[str, Optional[float]], t: float) -> List[SensorState]:
        return [self.tracks[lb].update(readings.get(lb), t) for lb in self.tracks]

    @staticmethod
    def speech_for(states: List[SensorState]) -> Optional[str]:
        """Short spoken warning, or None. Center has priority, then the closer side."""
        by = {s.label: s for s in states}
        c = by.get("center")
        if c and ((c.ttc is not None and c.ttc < TTC_SPEAK_S) or
                  (c.distance is not None and c.distance < PROXIMITY_DANGER_CM)):
            return "Obstacle ahead"
        sides = [s for s in states if s.label in ("left", "right") and s.distance is not None
                 and (s.distance < PROXIMITY_DANGER_CM or (s.ttc is not None and s.ttc < 0.5))]
        if sides:
            closest = min(sides, key=lambda s: s.distance)
            return f"Obstacle {closest.label}"
        return None
