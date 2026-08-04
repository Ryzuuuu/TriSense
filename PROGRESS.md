# TriSense — Project Progress

## Done
- **Phase 1A: Blind Mode (Software Complete)**
  - Sensor polling, collision math, haptic/audio alert drivers, and mock testing infrastructure implemented and validated (`ALL SYNTHETIC TESTS PASSED [PASS]`).
  - Hardware validation checklist (`blind_mode/HARDWARE_TODO.md`) prepared for Raspberry Pi deployment.
- **Phase 1B: Deaf Mode (Software Complete)**
  - `AudioStreamer`, `ASREngine`, `CaptionFormatter`, `OLEDDisplay`, `CaptionRenderer`, and `DeafModeApp` implemented and verified (`ALL STEP 3.1 TESTS PASSED [PASS]`).
  - Hardware validation checklist (`deaf_mode/HARDWARE_TODO.md`) prepared for Raspberry Pi deployment.
- **Phase 2: System Coordination (Step 1 Complete)**
  - `shared/mode_manager.py`: Created `ModeManager` with single-owner `ResourceGuard` locking (`SPEAKER`, `CAMERA`, `MICROPHONE`, `DISPLAY`, `GPIO_SENSORS`, `GPIO_MOTORS`) ensuring two modes can never run simultaneously.
  - Implemented adapter wrappers (`BlindModePipeline`, `DeafModePipeline`, and `MuteModePipeline` extension point) that start/stop existing pipelines without modifying internal module code.
  - Implemented mock keyboard mode-switch trigger (`handle_key_input`) standing in for GPIO button presses.
  - Verified via standalone test suite (`shared/test_mode_manager.py`) (`ALL MODE MANAGER (STEP 1) TESTS PASSED [PASS]`).
- **Phase 1C: Mute Mode — Step 1: Landmark Extraction Pipeline**
  - `mute_mode/config.py`: MediaPipe Hands hyperparameters, 21 landmark indices, and low-confidence flagging thresholds.
  - `mute_mode/mock_video.py` & `mute_mode/video_stream.py`: Implemented `MockVideoStream` reading real recorded video files (`real_sign.mp4`) without synthetic generation, and unified `VideoStreamer` exposing `.mode` (`"VideoFileStream"` / `"HardwareCamera"`).
  - `mute_mode/landmark_extractor.py`: Implemented `LandmarkExtractor` using real `mediapipe.solutions.hands.Hands` (failing loudly if MediaPipe is unavailable). Performs precise wrist translation (`wrist = (0.0, 0.0, 0.0)`) and bounding scale normalization (`scale_factor`). Exposes per-landmark visibility and flags low-confidence keypoints (`low_confidence: True`) without dropping or fabricating coordinates.
  - `mute_mode/test_landmark_extractor.py`: Verification suite verifying stream mode, 21-landmark extraction, wrist origin normalization, scale invariance, and confidence score flagging.

## Next
- **Phase 1C: Mute Mode — Step 2**
  - Feature smoothing and dynamic gesture sequence buffer for temporal sign language classification.
