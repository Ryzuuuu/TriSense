"""Tests for blind_mode/engine.py: real-time speed, filtering and proximity alerts."""

from blind_mode.engine import BlindEngine, SensorTrack, ttc_to_pulse_ms


def feed(track, samples):
    st = None
    for t, d in samples:
        st = track.update(d, t)
    return st


def test_speed_uses_real_elapsed_time():
    # 10 cm closer every 0.25 s -> 40 cm/s, regardless of the nominal 0.1 s poll interval
    track = SensorTrack("center")
    st = feed(track, [(i * 0.25, 200 - 10 * i) for i in range(8)])
    assert abs(st.speed - 40.0) < 1.0
    assert abs(st.ttc - st.distance / st.speed) < 1e-9


def test_single_outlier_does_not_trigger_alert():
    track = SensorTrack("center")
    samples = [(i * 0.1, 250.0) for i in range(5)] + [(0.5, 20.0)] + [(0.6 + i * 0.1, 250.0) for i in range(3)]
    for t, d in samples:
        st = track.update(d, t)
        assert st.pulse_ms is None, f"false alert at t={t}"


def test_out_of_range_echo_is_ignored():
    track = SensorTrack("left")
    st = feed(track, [(0.0, 150.0), (0.1, 900.0), (0.2, 150.0)])
    assert st.distance == 150.0


def test_static_close_obstacle_alerts_without_motion():
    # a wall 20 cm away while the user stands still: TTC is undefined, proximity must still fire
    track = SensorTrack("center")
    st = feed(track, [(i * 0.1, 20.0) for i in range(5)])
    assert st.ttc is None
    assert st.pulse_ms == 300 and st.reason == "proximity"
    assert BlindEngine.speech_for([st]) == "Obstacle ahead"


def test_jitter_below_deadband_gives_no_ttc():
    track = SensorTrack("right")
    st = feed(track, [(i * 0.1, 150.0 + (0.8 if i % 2 else -0.8)) for i in range(10)])
    assert st.ttc is None and st.pulse_ms is None


def test_fast_approach_escalates_tiers():
    track = SensorTrack("center")
    pulses = [st.pulse_ms for st in (track.update(300 - 25 * i, i * 0.1) for i in range(11))]
    assert pulses[-1] == 500
    assert 150 in pulses or 300 in pulses


def test_stale_sensor_is_forgotten():
    track = SensorTrack("left")
    feed(track, [(0.0, 50.0), (0.1, 50.0)])
    st = feed(track, [(1.0, None)])
    assert st.distance is None


def test_ttc_tiers_match_haptic_module():
    from blind_mode.haptic import get_alert_intensity
    for ttc in (None, 0.1, 0.49, 0.5, 0.99, 1.0, 1.49, 1.5, 3.0):
        assert ttc_to_pulse_ms(ttc) == get_alert_intensity(ttc)


def test_side_speech():
    eng = BlindEngine()
    states = None
    for i in range(4):
        states = eng.step({"left": 22.0, "center": 250.0, "right": 200.0}, i * 0.1)
    assert BlindEngine.speech_for(states) == "Obstacle left"
