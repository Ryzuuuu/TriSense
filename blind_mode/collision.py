# blind_mode/collision.py
# -----------------------------------------------------------------------------
# Collision-time estimation for TriSense — Blind Mode.
# Provides two pure functions (no GPIO, no hardware dependency):
#   compute_closing_speed(d1, d2, dt) -> float | None
#   time_to_collision(distance, closing_speed) -> float | None   [added Step 7]
#
# Run this file directly to execute the built-in unit tests:
#   python3 collision.py
# -----------------------------------------------------------------------------


def compute_closing_speed(d1, d2, dt):
    """
    Estimate how fast an object is approaching based on two distance readings.

    Parameters
    ----------
    d1 : float | None  First distance reading in cm (older sample).
    d2 : float | None  Second distance reading in cm (newer sample).
    dt : float         Time elapsed between the two readings in seconds (> 0).

    Returns
    -------
    float | None
        Closing speed in cm/s.
        Positive  → object is getting CLOSER  (d2 < d1)
        Negative  → object is moving AWAY     (d2 > d1)
        Zero      → object is stationary
        None      → either reading was None (sensor timeout) or dt <= 0

    Notes
    -----
    The build plan samples each sensor ~100 ms apart, so dt ≈ 0.1 s in normal
    operation.  The function intentionally returns negative speeds (moving away)
    so the caller can decide what to do — time_to_collision() will filter those.
    """
    if d1 is None or d2 is None:
        return None
    if dt <= 0:
        return None
    return (d1 - d2) / dt   # positive when d2 < d1 (object approaching)


# ── Unit tests for compute_closing_speed ─────────────────────────────────────

def _test_compute_closing_speed():
    # 1. Normal approach: object moved from 100 cm to 80 cm in 0.1 s
    #    closing speed = (100 - 80) / 0.1 = 200 cm/s
    result = compute_closing_speed(100.0, 80.0, 0.1)
    assert result == 200.0, f"Expected 200.0, got {result}"

    # 2. Object moving away: distance increased
    #    closing speed = (50 - 70) / 0.1 = -200 cm/s  (negative = moving away)
    result = compute_closing_speed(50.0, 70.0, 0.1)
    assert result == -200.0, f"Expected -200.0, got {result}"

    # 3. Stationary object: no change in distance
    result = compute_closing_speed(60.0, 60.0, 0.1)
    assert result == 0.0, f"Expected 0.0, got {result}"

    # 4. First reading is None (sensor timeout) → should return None
    result = compute_closing_speed(None, 60.0, 0.1)
    assert result is None, f"Expected None, got {result}"

    # 5. Second reading is None → should return None
    result = compute_closing_speed(60.0, None, 0.1)
    assert result is None, f"Expected None, got {result}"

    # 6. Both readings None → should return None
    result = compute_closing_speed(None, None, 0.1)
    assert result is None, f"Expected None, got {result}"

    # 7. Zero time delta → undefined speed, return None (avoid division by zero)
    result = compute_closing_speed(100.0, 80.0, 0.0)
    assert result is None, f"Expected None for dt=0, got {result}"

    # 8. Negative time delta → nonsensical, return None
    result = compute_closing_speed(100.0, 80.0, -0.5)
    assert result is None, f"Expected None for dt<0, got {result}"

    # 9. Very small time delta (still valid): 1 cm in 0.001 s = 1000 cm/s
    result = compute_closing_speed(50.0, 49.0, 0.001)
    assert abs(result - 1000.0) < 1e-9, f"Expected 1000.0, got {result}"

    print("  [PASS] All compute_closing_speed tests passed.")


# ── time_to_collision ─────────────────────────────────────────────────────────

def time_to_collision(distance, closing_speed):
    """
    Estimate seconds until an approaching object reaches the sensor.

    Parameters
    ----------
    distance      : float | None  Current distance to object in cm.
    closing_speed : float | None  Speed from compute_closing_speed() in cm/s.

    Returns
    -------
    float | None
        Seconds until collision, or None when:
          - distance or closing_speed is None (bad sensor data)
          - closing_speed <= 0  (object is stationary or moving away —
            TTC is undefined / infinite; no alert needed)
          - distance <= 0  (sensor already at or past the object — clamp)
    """
    if distance is None or closing_speed is None:
        return None
    if closing_speed <= 0:
        return None       # not approaching — no collision risk
    if distance <= 0:
        return None       # already at/past object — treat as immediate
    return distance / closing_speed


# ── Unit tests for time_to_collision ─────────────────────────────────────────

def _test_time_to_collision():
    # 1. Normal case: 150 cm away, approaching at 100 cm/s → TTC = 1.5 s
    result = time_to_collision(150.0, 100.0)
    assert abs(result - 1.5) < 1e-9, f"Expected 1.5, got {result}"

    # 2. Very close and fast: 10 cm at 200 cm/s → TTC = 0.05 s
    result = time_to_collision(10.0, 200.0)
    assert abs(result - 0.05) < 1e-9, f"Expected 0.05, got {result}"

    # 3. Zero closing speed → object stationary, return None
    result = time_to_collision(100.0, 0.0)
    assert result is None, f"Expected None for speed=0, got {result}"

    # 4. Negative closing speed → object moving away, return None
    result = time_to_collision(100.0, -50.0)
    assert result is None, f"Expected None for negative speed, got {result}"

    # 5. distance is None (sensor timeout) → return None
    result = time_to_collision(None, 100.0)
    assert result is None, f"Expected None for distance=None, got {result}"

    # 6. closing_speed is None (upstream None from compute_closing_speed) → None
    result = time_to_collision(100.0, None)
    assert result is None, f"Expected None for speed=None, got {result}"

    # 7. Both None → None
    result = time_to_collision(None, None)
    assert result is None, f"Expected None for both None, got {result}"

    # 8. distance = 0 → undefined / already hit, return None
    result = time_to_collision(0.0, 100.0)
    assert result is None, f"Expected None for distance=0, got {result}"

    # 9. distance negative → nonsensical sensor data, return None
    result = time_to_collision(-5.0, 100.0)
    assert result is None, f"Expected None for negative distance, got {result}"

    print("  [PASS] All time_to_collision tests passed.")


# ── Standalone test runner ────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Running collision.py unit tests...\n")
    _test_compute_closing_speed()
    _test_time_to_collision()
    print("\nAll tests passed. collision.py is ready.")
