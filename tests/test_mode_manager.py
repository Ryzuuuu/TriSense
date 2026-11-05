"""Unit tests for ModeManager / ResourceGuard using stub pipelines (no hardware, no models)."""

import pytest

from shared.mode_manager import ModeManager, ResourceGuard, ResourceLockError


class StubPipeline:
    """Minimal pipeline double that records its lifecycle."""

    def __init__(self, resources, fail_on_start=False):
        self.REQUIRED_RESOURCES = set(resources)
        self.fail_on_start = fail_on_start
        self.is_running = False
        self.start_kwargs = None
        self.stop_calls = 0

    def start(self, **kwargs):
        if self.fail_on_start:
            raise RuntimeError("boom")
        self.start_kwargs = kwargs
        self.is_running = True

    def stop(self):
        self.stop_calls += 1
        self.is_running = False


@pytest.fixture
def manager():
    mgr = ModeManager()
    mgr._pipelines = {
        "BLIND": StubPipeline({"SPEAKER", "GPIO_SENSORS", "GPIO_MOTORS"}),
        "DEAF": StubPipeline({"MICROPHONE", "DISPLAY"}),
        "MUTE": StubPipeline({"CAMERA", "SPEAKER"}),
    }
    yield mgr
    mgr.shutdown()


# -- ResourceGuard -------------------------------------------------------------

def test_guard_blocks_overlapping_owner():
    guard = ResourceGuard()
    guard.acquire("BLIND", {"SPEAKER", "GPIO_SENSORS"})
    with pytest.raises(ResourceLockError):
        guard.acquire("MUTE", {"SPEAKER", "CAMERA"})
    # a failed acquire must not leak partial ownership
    assert guard.get_owner("CAMERA") is None


def test_guard_release_and_reacquire():
    guard = ResourceGuard()
    guard.acquire("BLIND", {"SPEAKER"})
    guard.release("BLIND")
    guard.acquire("MUTE", {"SPEAKER"})
    assert guard.get_owner("SPEAKER") == "MUTE"
    assert guard.get_held_resources("MUTE") == {"SPEAKER"}


def test_guard_snapshot_is_a_copy():
    guard = ResourceGuard()
    guard.acquire("DEAF", {"DISPLAY"})
    snap = guard.snapshot()
    snap["DISPLAY"] = "tampered"
    assert guard.get_owner("DISPLAY") == "DEAF"


# -- ModeManager ---------------------------------------------------------------

def test_starts_idle(manager):
    assert manager.current_mode == "IDLE"


def test_switch_acquires_resources_and_forwards_kwargs(manager):
    assert manager.switch_mode("blind", on_telemetry="cb") is True
    assert manager.current_mode == "BLIND"
    assert manager.resource_guard.get_owner("SPEAKER") == "BLIND"
    assert manager.get_pipeline("BLIND").start_kwargs == {"on_telemetry": "cb"}


def test_switch_stops_previous_mode_and_releases_resources(manager):
    manager.switch_mode("BLIND")
    manager.switch_mode("DEAF")
    assert manager.get_pipeline("BLIND").stop_calls == 1
    assert manager.resource_guard.get_owner("SPEAKER") is None
    assert manager.resource_guard.get_owner("DISPLAY") == "DEAF"


def test_switch_to_same_mode_is_a_noop(manager):
    manager.switch_mode("MUTE")
    manager.switch_mode("MUTE")
    assert manager.get_pipeline("MUTE").stop_calls == 0


def test_idle_releases_everything(manager):
    manager.switch_mode("MUTE")
    manager.switch_mode("IDLE")
    assert manager.current_mode == "IDLE"
    assert manager.resource_guard.snapshot() == {}


def test_unknown_mode_raises_and_keeps_state(manager):
    manager.switch_mode("DEAF")
    with pytest.raises(ValueError):
        manager.switch_mode("TELEPORT")
    assert manager.current_mode == "DEAF"


def test_failed_start_reverts_to_idle_and_frees_resources(manager):
    manager._pipelines["BLIND"] = StubPipeline({"SPEAKER", "GPIO_SENSORS"}, fail_on_start=True)
    with pytest.raises(RuntimeError):
        manager.switch_mode("BLIND")
    assert manager.current_mode == "IDLE"
    assert manager.resource_guard.snapshot() == {}


@pytest.mark.parametrize(
    "key, expected",
    [("1", "BLIND"), ("2", "DEAF"), ("3", "MUTE"), ("0", "IDLE"), ("q", "IDLE")],
)
def test_key_mapping(manager, key, expected):
    manager.switch_mode("DEAF" if expected != "DEAF" else "BLIND")
    assert manager.handle_key_input(key) == expected


def test_unmapped_key_is_ignored(manager):
    manager.switch_mode("DEAF")
    assert manager.handle_key_input("z") == "DEAF"
