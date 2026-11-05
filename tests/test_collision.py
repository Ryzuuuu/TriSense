"""Unit tests for Blind Mode collision math (pure Python, no hardware)."""

import pytest

from blind_mode.collision import compute_closing_speed, time_to_collision


def test_approaching_object_has_positive_speed():
    assert compute_closing_speed(100.0, 90.0, 0.1) == pytest.approx(100.0)


def test_receding_object_has_negative_speed():
    assert compute_closing_speed(90.0, 100.0, 0.1) == pytest.approx(-100.0)


def test_stationary_object_has_zero_speed():
    assert compute_closing_speed(50.0, 50.0, 0.1) == 0.0


@pytest.mark.parametrize(
    "d1, d2, dt",
    [(None, 60.0, 0.1), (60.0, None, 0.1), (None, None, 0.1), (60.0, 50.0, 0), (60.0, 50.0, -1)],
)
def test_bad_input_returns_none(d1, d2, dt):
    assert compute_closing_speed(d1, d2, dt) is None


def test_time_to_collision_basic():
    assert time_to_collision(100.0, 50.0) == pytest.approx(2.0)


@pytest.mark.parametrize(
    "distance, speed",
    [(None, 50.0), (100.0, None), (100.0, 0.0), (100.0, -10.0), (0.0, 50.0), (-5.0, 50.0)],
)
def test_no_collision_risk_returns_none(distance, speed):
    assert time_to_collision(distance, speed) is None
