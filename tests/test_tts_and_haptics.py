"""Tests for the shared TTS queue and the non blocking haptic driver."""

import os
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
# haptic.py uses flat imports and RPi.GPIO: expose blind_mode and the bundled GPIO mock (CI has no RPi.GPIO)
for p in (os.path.join(ROOT, "blind_mode", "mock_lib"), os.path.join(ROOT, "blind_mode")):
    if p not in sys.path:
        sys.path.insert(0, p)

from shared import tts_output  # noqa: E402


def test_cooldown_is_per_phrase_and_stamped_at_queue_time():
    tts_output.flush()
    tts_output.reset_cooldowns()
    assert tts_output.speak("Obstacle ahead", cooldown=2.0) is True
    # the same phrase again immediately: suppressed even though nothing has been spoken yet
    assert tts_output.speak("Obstacle ahead", cooldown=2.0) is False
    time.sleep(tts_output.GLOBAL_GAP_S + 0.05)
    assert tts_output.speak("hello", cooldown=2.0) is True
    tts_output.flush()
    assert tts_output._speech_queue.empty()


def test_queue_is_bounded():
    tts_output.flush()
    tts_output.reset_cooldowns()
    old_gap = tts_output.GLOBAL_GAP_S
    tts_output.GLOBAL_GAP_S = 0.0
    try:
        for i in range(10):
            tts_output.speak(f"word {i}", cooldown=0)
        assert tts_output._speech_queue.qsize() <= tts_output.MAX_PENDING
    finally:
        tts_output.GLOBAL_GAP_S = old_gap
        tts_output.flush()


class FakeGPIO:
    HIGH, LOW = 1, 0

    def __init__(self):
        self.state = {}
        self.events = []

    def output(self, pin, value):
        self.state[pin] = value
        self.events.append((time.monotonic(), pin, value))


def test_haptic_driver_is_non_blocking_and_turns_off():
    from blind_mode.haptic import HapticDriver
    gpio = FakeGPIO()
    drv = HapticDriver(motors={"left": 1, "center": 2}, gpio=gpio)
    t0 = time.monotonic()
    assert drv.pulse("left", 150) is True
    assert time.monotonic() - t0 < 0.05  # returned immediately
    assert gpio.state[1] == 1
    assert drv.pulse("left", 150) is False  # still busy, not re-triggered
    time.sleep(0.25)
    assert gpio.state[1] == 0
    time.sleep(0.1)
    assert drv.pulse("left", 150) is True
    drv.stop()
    assert gpio.state[1] == 0 and gpio.state.get(2, 0) == 0
