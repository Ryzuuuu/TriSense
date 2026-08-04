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
  - `mute_mode/landmark_extractor.py`: Implemented `LandmarkExtractor` supporting both legacy `mediapipe.solutions.hands` and modern `mediapipe.tasks.python.vision.HandLandmarker` (for Python 3.12+ compatibility, failing loudly if MediaPipe is unavailable). Performs precise wrist translation (`wrist = (0.0, 0.0, 0.0)`) and bounding scale normalization (`scale_factor`). Exposes per-landmark visibility and flags low-confidence keypoints (`low_confidence: True`) without dropping or fabricating coordinates.
- **Phase 1C: Mute Mode — Step 2: Feature Smoothing & Gesture Sequence Buffer**
  - `mute_mode/config.py`: Added `EMA_ALPHA = 0.6`, `WINDOW_SIZE = 30`, and `MAX_HOLD_FRAMES = 5`.
  - `mute_mode/sequence_buffer.py`: Implemented `LandmarkSmoother` applying Exponential Moving Average (EMA) smoothing across 21 3D coordinates per hand to eliminate jitter without lagging gesture motion. Implemented hold-last-good-value imputation for occluded/low-confidence frames (`imputed = True`, exponential confidence decay $0.5^k$ up to `MAX_HOLD_FRAMES = 5`), cleanly resetting to zero-coordinate placeholders (`missing = True`) on extended occlusion. Implemented `GestureSequenceBuffer` 30-frame rolling FIFO deque with warmup padding and explicit `buffer_full` status.
  - `mute_mode/test_sequence_buffer.py`: Verification suite verifying EMA jitter reduction on real video (`real_sign.mp4`), 30-frame sliding window FIFO integrity, and explicit occlusion imputation (`ALL MUTE MODE STEP 2 TESTS PASSED [PASS]`).

- **Phase 1C: Mute Mode — Step 3: Classifier Architecture & Training Pipeline (Structural Only)**
  - `mute_mode/config.py`: Defined 12-word vocabulary (`hello`, `thank you`, `help`, `yes`, `no`, `water`, `food`, `stop`, `please`, `sorry`, `more`, `done`) and sequence tensor dimensions (`SEQ_LENGTH = 30`, `FEATURE_DIM = 126`, `NUM_CLASSES = 12`).
  - `mute_mode/classifier.py`: Implemented edge-optimized `SignLanguageClassifier` (1D-CNN spatial motif blocks + 1-layer GRU temporal sequence model) with 62,604 trainable parameters (<100,000 budget for Pi deployment). Includes `extract_sequence_tensor()` for Step 2 `GestureSequenceBuffer` integration and `predict_step()` returning class label, confidence, and softmax probability distribution.
  - `mute_mode/train_classifier.py`: Implemented training script structure (`SignLanguageDataset`, `train_one_epoch`, `evaluate_epoch`, `save_checkpoint`, `load_checkpoint`) with dummy dataset generator for structural smoke testing. Enforces explicit warning banner on synthetic data and prevents reporting % accuracy claims as real performance.
  - `mute_mode/test_classifier_pipeline.py`: Verification suite confirming <100k parameter budget (62,604 params), 1-epoch structural training/validation on dummy tensors, warning banner enforcement, and checkpoint save/load round-trip (`ALL MUTE MODE STEP 3 TESTS PASSED [PASS]`).

## Next
- **Phase 1C: Mute Mode — Step 4**
  - End-to-end Mute Mode pipeline integration (connecting landmark extractor, sequence buffer, classifier inference, and mock trigger) or Phase 2 quantization/export planning.
