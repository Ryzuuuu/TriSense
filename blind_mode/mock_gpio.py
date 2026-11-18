# blind_mode/mock_gpio.py
# -----------------------------------------------------------------------------
# Mock RPi.GPIO interface for testing TriSense on non-Pi machines.
# Fakes the API expected by config.py, gpio_setup.py, distance.py, haptic.py.
# Uses the MOCK_DISTANCE environment variable to simulate obstacle distances.
# -----------------------------------------------------------------------------

import time
import os
import random
import threading

# GPIO Constants (matches RPi.GPIO)
BCM = "BCM"
OUT = "OUT"
IN = "IN"
LOW = 0
HIGH = 1
PUD_UP = "PUD_UP"
PUD_DOWN = "PUD_DOWN"
FALLING = "FALLING"

_echo_states = {}
_lock = threading.Lock()

# Per sensor overrides set live by the web emulator: {"left": 85.0, "center": None, ...}
# A value of None simulates a sensor that never hears an echo (timeout).
_overrides = {}
_noise_cm = 0.5


def _trigger_to_label():
    try:
        from blind_mode.config import SENSORS
    except ImportError:
        from config import SENSORS
    return {trig: (label, echo) for label, trig, echo in SENSORS}


def set_distances(distances: dict, noise_cm: float = 0.5):
    """Emulator hook: set the simulated distance (cm, or None for no echo) per sensor label."""
    global _noise_cm
    with _lock:
        _overrides.update(distances)
        _noise_cm = noise_cm


def clear_distances():
    with _lock:
        _overrides.clear()

def _get_mock_distance():
    """
    Read MOCK_DISTANCE from the environment.
    Supports "RANDOM" or a fixed float like "45.0"
    """
    val = os.environ.get("MOCK_DISTANCE", "50.0")
    if val.upper() == "RANDOM":
        return random.uniform(10.0, 150.0)
    try:
        dist = float(val)
        # Add a tiny bit of noise to simulate real sensor jitter (±0.5 cm)
        return max(1.0, dist + random.uniform(-0.5, 0.5))
    except ValueError:
        return 50.0

def setwarnings(flag):
    pass

def setmode(mode):
    pass

def setup(pin, mode, **kwargs):
    if mode == IN:
        with _lock:
            _echo_states[pin] = {"start": 0, "end": 0}

_pending = {}  # trigger pin -> list of (echo_pin, distance or None) armed on the rising edge


def output(pin, state):
    """
    Trigger pins arm a simulated echo on the rising edge and fire it on the
    falling edge, like a real HC-SR04 (which starts its burst after the 10 us
    trigger pulse). Timing uses perf_counter: on Windows the 10 us sleep in
    distance.py can stretch to milliseconds, which used to eat into the echo.
    """
    if state == HIGH:
        trig_map = _trigger_to_label()
        with _lock:
            if pin in trig_map and trig_map[pin][0] in _overrides:
                label, echo_pin = trig_map[pin]
                dist = _overrides[label]
                if dist is not None:
                    dist = max(1.0, float(dist) + random.uniform(-_noise_cm, _noise_cm))
                _pending[pin] = [(echo_pin, dist)]
            elif pin in trig_map or not trig_map:
                # No override: legacy behaviour, every echo pin reports MOCK_DISTANCE
                d = _get_mock_distance()
                _pending[pin] = [(e, d) for e in _echo_states]
        return
    # falling edge: start the echo(s) armed by this trigger
    with _lock:
        armed = _pending.pop(pin, None)
        if not armed:
            return
        now = time.perf_counter()
        for echo_pin, dist in armed:
            if dist is None:  # dead sensor: echo never rises
                _echo_states[echo_pin] = {"start": now + 10.0, "end": now + 10.0}
            else:
                dur = (dist * 2) / 34300.0
                _echo_states[echo_pin] = {"start": now + 0.00001, "end": now + 0.00001 + dur}


def input(pin):
    with _lock:
        if pin in _echo_states:
            state = _echo_states[pin]
            now = time.perf_counter()
            if now < state["start"]:
                return LOW
            elif now <= state["end"]:
                return HIGH
            else:
                return LOW
    return LOW

def cleanup():
    pass

def add_event_detect(*args, **kwargs):
    pass
