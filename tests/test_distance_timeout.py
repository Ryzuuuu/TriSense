"""Regression test: a sensor whose ECHO never rises must time out instead of hanging."""

import os
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
# blind_mode modules use flat imports (`from config import ...`) and RPi.GPIO,
# so expose the package directory and the bundled GPIO mock.
for p in (os.path.join(ROOT, "blind_mode", "mock_lib"), os.path.join(ROOT, "blind_mode")):
    if p not in sys.path:
        sys.path.insert(0, p)

import distance  # noqa: E402


def test_get_distance_returns_none_when_echo_never_rises(monkeypatch):
    monkeypatch.setattr(distance.GPIO, "input", lambda pin: 0)
    monkeypatch.setattr(distance.GPIO, "output", lambda pin, state: None)

    start = time.time()
    result = distance.get_distance(trig=13, echo=16, timeout=0.05)
    elapsed = time.time() - start

    assert result is None
    assert elapsed < 1.0
