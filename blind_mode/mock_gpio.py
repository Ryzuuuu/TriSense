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

def output(pin, state):
    if state == HIGH:
        # A trigger pin just went HIGH. We don't track which trigger maps to which echo here,
        # we just prime ALL known echo pins to return a pulse representing the mock distance.
        dist = _get_mock_distance()
        pulse_duration = (dist * 2) / 34300.0  # Calculate time needed for this distance
        
        now = time.time()
        with _lock:
            for echo_pin in _echo_states:
                # Echo goes HIGH 10µs from now, and stays HIGH for pulse_duration
                _echo_states[echo_pin] = {
                    "start": now + 0.00001,
                    "end": now + 0.00001 + pulse_duration
                }

def input(pin):
    with _lock:
        if pin in _echo_states:
            state = _echo_states[pin]
            now = time.time()
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
