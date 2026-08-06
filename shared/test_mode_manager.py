# shared/test_mode_manager.py
# -----------------------------------------------------------------------------
# Verification Script for TriSense Shared Mode Manager (Step 1).
# Verifies:
#   1. Single-owner resource locking (ResourceGuard prevents simultaneous modes).
#   2. Clean transitions between IDLE <-> BLIND <-> DEAF <-> IDLE modes.
#   3. Mock keyboard trigger (handle_key_input) and MUTE extension point.
# -----------------------------------------------------------------------------

import os
import sys
import time

# Ensure UTF-8 output encoding for console symbols on Windows/cp1252
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Ensure root directory is in python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from shared.mode_manager import ModeManager, ResourceGuard, ResourceLockError


def test_resource_guard():
    print("-----------------------------------------------------------------------")
    print("Test 1: Single-Owner ResourceGuard Enforcement")
    print("-----------------------------------------------------------------------")
    guard = ResourceGuard()
    
    # 1. Acquire resources for BLIND mode
    guard.acquire("BLIND", {"SPEAKER", "GPIO_SENSORS"})
    assert guard.get_owner("SPEAKER") == "BLIND"
    
    # 2. Attempt to acquire overlapping resource for DEAF mode
    conflict_detected = False
    try:
        guard.acquire("DEAF", {"SPEAKER", "DISPLAY"})
    except ResourceLockError as e:
        conflict_detected = True
        print(f"   [Expected Lock Error] {e}")

    assert conflict_detected, "ResourceGuard failed to raise ResourceLockError on overlapping resource!"
    print("   [PASS] ResourceGuard correctly blocked simultaneous resource acquisition.")

    # 3. Release BLIND and re-acquire for DEAF
    guard.release("BLIND")
    assert guard.get_owner("SPEAKER") is None
    guard.acquire("DEAF", {"SPEAKER", "DISPLAY"})
    assert guard.get_owner("SPEAKER") == "DEAF"
    print("   [PASS] Resources successfully acquired after previous owner released.\n")
    return True


def test_mode_transitions():
    print("-----------------------------------------------------------------------")
    print("Test 2: Mode Transitions & Pipeline Lifecycle (IDLE -> BLIND -> DEAF)")
    print("-----------------------------------------------------------------------")
    manager = ModeManager()
    assert manager.current_mode == "IDLE"

    # 1. Switch to BLIND mode
    print("--> Activating BLIND Mode...")
    manager.switch_mode("BLIND")
    assert manager.current_mode == "BLIND"
    assert manager.resource_guard.get_owner("SPEAKER") == "BLIND"
    print("   [PASS] BLIND Mode active and running ultrasonic/haptic pipeline.")
    
    # Let Blind Mode run briefly (sensor polling loop in background)
    time.sleep(0.35)

    # 2. Switch directly to DEAF mode (should stop BLIND first, release SPEAKER/GPIO, acquire DEAF resources)
    print("--> Switching directly from BLIND to DEAF Mode...")
    wav_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "deaf_mode", "real_speech.wav"))
    manager.switch_mode("DEAF", wav_path=wav_path, use_mock=True)
    
    assert manager.current_mode == "DEAF"
    assert manager.resource_guard.get_owner("DISPLAY") == "DEAF"
    assert manager.resource_guard.get_owner("SPEAKER") is None  # Released by BLIND
    print("   [PASS] BLIND Mode stopped cleanly; DEAF Mode active and processed audio.")

    # 3. Return to IDLE
    print("--> Returning to IDLE...")
    manager.switch_mode("IDLE")
    assert manager.current_mode == "IDLE"
    assert len(manager.resource_guard._owners) == 0
    print("   [PASS] All pipelines stopped and all resources released.\n")
    return True


def test_key_trigger_and_mute_mode():
    print("-----------------------------------------------------------------------")
    print("Test 3: Mock Key Trigger & Mute Mode Integration")
    print("-----------------------------------------------------------------------")
    manager = ModeManager()

    # '1' -> BLIND
    mode = manager.handle_key_input("1")
    assert mode == "BLIND"
    print("   [PASS] Key '1' triggered BLIND mode.")

    # '0' -> IDLE
    mode = manager.handle_key_input("0")
    assert mode == "IDLE"
    print("   [PASS] Key '0' triggered IDLE mode.")

    # '3' -> MUTE
    print("--> Testing Key '3' (MUTE Mode integration)...")
    mode = manager.handle_key_input("3", use_mock=True)
    assert mode == "MUTE"
    assert manager.resource_guard.get_owner("CAMERA") == "MUTE"
    assert manager.resource_guard.get_owner("SPEAKER") == "MUTE"
    print("   [PASS] Mute Mode launched successfully and acquired resources.")

    # Return to IDLE
    mode = manager.handle_key_input("0")
    assert mode == "IDLE"
    print("   [PASS] All pipelines stopped and all resources released.\n")
    return True


def run_all_tests():
    print("=======================================================================")
    print(" TriSense ModeManager (Step 1) Verification Suite")
    print("=======================================================================\n")

    t1 = test_resource_guard()
    t2 = test_mode_transitions()
    t3 = test_key_trigger_and_mute_mode()

    all_passed = t1 and t2 and t3
    print("=======================================================================")
    if all_passed:
        print("RESULT: ALL MODE MANAGER (STEP 1) TESTS PASSED [PASS]\n")
    else:
        print("RESULT: MODE MANAGER TEST FAILED [FAIL]\n")
    return all_passed


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
