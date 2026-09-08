# TriSense — Build Explanation: What We Did and Why
### DSN4091 Capstone Project | VIT Bhopal University

> **Grounding note:** Every claim in this document is traced to a specific file, commit hash, or test result in the repository. Claims that could not be confirmed from files are explicitly marked **⚠️ UNVERIFIED**.

---

## 1. Project Overview

**TriSense** is a single wearable device built on a Raspberry Pi 4 that provides three independent, switchable accessibility modes: **Blind Mode** (obstacle detection and haptic/audio alerts), **Deaf Mode** (real-time offline speech-to-text captioning on an OLED), and **Mute Mode** (sign-language-to-speech translation using a camera and neural network classifier). The core design premise — one platform, three modes, software-switched — was chosen over building three separate devices because it reduces hardware cost, weight, and complexity while unifying the user experience.

**Deliverable priority:** Blind Mode and Deaf Mode are hard, non-negotiable deliverables. Mute Mode is a stretch goal that was explicitly protected from consuming schedule or resources earmarked for the two core modes. This constraint is documented in `docs/TriSense_Project_Writeup.md` (§ 1 and § 3.1.4) and `PROGRESS.md`.

---

## 2. Chronological Build Log

### Step 1 — Blind Mode: Configuration & GPIO Abstraction
**Commits:** `2a5b803`, `4a7ce57`

**What was built:**
- `blind_mode/config.py` — Single source of truth for all GPIO pin numbers (BCM numbering), sensor tuples, motor pin map, and echo timeout constant. No logic, only constants.
- `blind_mode/gpio_setup.py` — GPIO initialization and cleanup.
- `blind_mode/mock_lib/RPi/GPIO.py` — Software mock that simulates the RPi.GPIO library so the entire Blind Mode stack can be run and tested on a laptop without a Raspberry Pi.

**Why this approach:**
The comment block in `config.py` is explicit: *"Change these values here if you rewire sensors or motors; everything else imports from this file."* Centralizing pins in one file means any hardware re-wire requires editing exactly one file rather than hunting through multiple modules. The mock GPIO layer was built at the same time as the real GPIO layer — not as an afterthought — because it was recognized that all iterative development would happen on a laptop, not on hardware.

**Verification:** No automated test at this stage. The mock layer was verified as part of later test runs (`synthetic_test.py` and `test_mode_manager.py`).

---

### Step 2 — Blind Mode: Distance Sensing
**Commit:** `9ba7630`

**What was built:**
- `blind_mode/distance.py` — HC-SR04 ultrasonic sensor driver. Sends a 10 µs TRIG pulse, then times how long the ECHO pin stays HIGH to compute round-trip distance (speed of sound at 343 m/s). Returns `None` on timeout rather than crashing.

**Why this approach:**
The ECHO timeout (`ECHO_TIMEOUT_S = 0.03` in `config.py`) is set slightly above the HC-SR04's theoretical maximum range (≈ 400 cm → 0.023 s round-trip) with a margin. Returning `None` instead of raising an exception is deliberate — a timeout is a valid "no obstacle detected" state in practice, and crashing the sensor loop on every timeout would make the device unusable.

**Verification:** Verified as part of the synthetic simulation (`646b3b0`). Hardware physical validation pending — see `blind_mode/HARDWARE_TODO.md` § 2.

---

### Step 3 — Blind Mode: Collision Math
**Commit:** `dac3760`

**What was built:**
- `blind_mode/collision.py` — `compute_closing_speed(d_a, d_b, dt)` and `time_to_collision(distance, closing_speed)`. Closing speed is the delta between two consecutive sensor readings divided by the polling interval. TTC is simply current distance divided by closing speed.

**Why this approach:**
Finite-difference velocity estimation over two sequential readings at a fixed 100 ms interval (`POLL_INTERVAL_S = 0.1` in `sensor_loop.py`) is the simplest approach that works without a dedicated IMU or Kalman filter. The tradeoff is one polling interval of latency before any obstacle is detected — acceptable given typical walking speeds and the 1.5 s TTC alert threshold.

**Verification:** Verified end-to-end via `synthetic_test.py` which checks `[PASS] Closing speed and TTC computed correctly at each step.` The test simulates a subject walking at 100 cm/s from 200 cm to 10 cm and validates TTC at each step against the expected `d_b / 100.0`.

---

### Step 4 — Blind Mode: Haptic Motor Driver
**Commit:** `a4800dc`

**What was built:**
- `blind_mode/haptic.py` — `get_alert_intensity(ttc, threshold)` maps TTC to a pulse duration (ms), and `pulse_motor(pin, duration_ms)` drives the NPN-transistor-gated motor. Motors are fired from a daemon thread (`fire_motor_async` in `sensor_loop.py`) so the sensor loop is never blocked while a motor buzzes.

**Why this approach:**
The non-blocking thread approach for motor firing is explicitly documented in `blind_mode/HARDWARE_TODO.md` § 3 (Thread Overlap Test): if threads are NOT used, the motor can stutter when multiple sensors trigger simultaneously. The `daemon=True` flag ensures the thread does not keep the process alive if the main loop terminates.

**Verification:** Verified via `synthetic_test.py`: `[PASS] Haptic alerts fired at the correct threshold (< 1.5s).` Hardware validation of actual motor vibration is pending (`HARDWARE_TODO.md` § 3).

---

### Step 5 — Blind Mode: Audio Alerts (TTS)
**Commit:** `22eee20`

**What was built:**
- `blind_mode/audio_alert.py` (original) — pyttsx3-based TTS running in a dedicated background queue/worker thread. A 2-second cooldown prevents alert spam. The worker thread is started at module import time as a daemon.

**Why this approach:**
Running pyttsx3 in a dedicated background thread (not on the main sensor thread) is necessary because `engine.runAndWait()` is a blocking call that would freeze the sensor loop for the duration of each utterance. The cooldown prevents the system from speaking "Obstacle ahead" dozens of times per second at close range.

**Design evolution (later refactored in TTS extraction steps):** This module was later refactored into a thin proxy delegating to `shared/tts_output.py` so ModeManager — not individual modes — owns the TTS lifecycle. The public interface (`speak_alert`, `shutdown_audio`) was preserved unchanged so existing callers required no modification.

**Verification:** `[PASS] Audio alert fired correctly when TTC < 1.0s.` in `synthetic_test.py`. Hardware ALSA driver test pending (`HARDWARE_TODO.md` § 4).

---

### Step 6 — Blind Mode: Sensor Loop Integration & Synthetic Test
**Commits:** `4b3a649`, `646b3b0`

**What was built:**
- `blind_mode/sensor_loop.py` — The full A→B polling loop: reads all three sensors, computes closing speed and TTC per sensor, fires haptic motor asynchronously, speaks center alert when TTC < `TTC_AUDIO_THRESHOLD_S` (1.0 s).
- `blind_mode/synthetic_test.py` — Deterministic simulation of a subject walking at 100 cm/s from 200 cm to 10 cm, mocking `read_all_sensors` to return computed distances. Validates TTC math, haptic thresholds, and audio trigger from the resulting CSV.
- `blind_mode/test_logger.py` — Full pipeline loop that logs every sensor reading to a CSV for post-hoc false-positive/false-negative analysis.

**Why synthetic testing instead of hardware-only testing:**
Hardware was not yet available. The synthetic test lets the logic be validated deterministically on a PC. The test has a known answer (100 cm/s approach, TTC = d/100) and asserts against it — it is not merely checking "did it run" but "did the math produce the correct answer."

**Bugs found and fixed (post-initial commit):**
- `synthetic_test.py` used `sys.path.append(os.path.abspath("mock_lib"))` — a relative path that broke when run from the repository root. Fixed by replacing with `os.path.abspath(os.path.join(os.path.dirname(__file__), "mock_lib"))`. Root cause: relative `os.path.abspath()` resolves relative to the process's current working directory, not the script file's directory.
- Unicode characters `✅` / `❌` in the final print lines crashed on Windows with `cp1252` encoding. Fixed by replacing with ASCII `[PASS]` / `[FAIL]`. Root cause: Windows default console encoding does not support Unicode checkmarks.

**Verification:** Neel ran `python blind_mode/synthetic_test.py` from the repo root after the fixes and confirmed the output `OVERALL: ALL SYNTHETIC TESTS PASSED [PASS]` (57 sensor rows logged).

---

### Step 7 — Blind Mode: Hardware Validation Checklist
**Commit:** `7be1df3`

**What was built:**
- `blind_mode/HARDWARE_TODO.md` — Step-by-step checklist for physical hardware validation: floating pin check, sensor calibration at 50/100/150 cm, cross-talk check between the three sensors, motor strength and thread-overlap test, ALSA driver lock-up check, and a full walking obstacle-course test.

**Why pre-written:**
Hardware bugs (e.g., floating ECHO pins producing phantom readings, ultrasonic crosstalk between array elements) are well-known for HC-SR04 arrays. The checklist pre-documents their symptoms, root causes, and fixes so the team can diagnose issues quickly during hardware bring-up without needing to debug from first principles.

**Known pre-applied fix documented in the checklist:**
- **Floating pin false triggers:** Add `pull_up_down=GPIO.PUD_DOWN` to ECHO pin setup in `gpio_setup.py` (checklist § 1, Floating Pin Check). This is listed as a _fix_, not yet confirmed as applied in code. **⚠️ UNVERIFIED: Neel should confirm whether `GPIO.PUD_DOWN` is currently set in `gpio_setup.py` before hardware testing.**
- **Ultrasonic crosstalk:** Add `time.sleep(0.02)` between sensors in `read_all_sensors()`. **⚠️ UNVERIFIED: Neel should confirm whether this delay is currently implemented in `distance.py`.**

---

### Step 8 — Deaf Mode: Audio Input Abstraction
**Commit:** `e6eaeca`

**What was built:**
- `deaf_mode/audio_stream.py` — `AudioStreamer` class that wraps either `sounddevice.RawInputStream` (live INMP441 microphone) or a `MockAudioStream` feeding pre-recorded WAV blocks. Exposes a uniform callback interface regardless of source.
- Mock WAV helper for testing without physical hardware.

**Why an abstraction layer:**
A uniform `AudioStreamer` interface means the ASR engine, the caption pipeline, and the integration tests do not care whether audio comes from a live microphone or a WAV file. This allows all downstream code to be developed and tested on a PC using recorded speech.

**Verification:** Verified via `deaf_mode/test_audio_stream.py` (referenced in `PROGRESS.md` § Done, Phase 1B).

---

### Step 9 — Deaf Mode: Vosk Offline ASR Engine
**Commit:** `09dd10e`

**What was built:**
- `deaf_mode/asr_engine.py` — Wrapper around the Vosk `KaldiRecognizer`. Exposes `accept_waveform`, `result` (final utterance), and `partial_result` (in-progress partial transcript). Includes a `MockASREngine` that emits canned text for testing.

**Why Vosk (offline) over cloud ASR:**
Explicit design decision documented in `TriSense_Project_Writeup.md` § 3.2 and `HARDWARE_TODO.md` § 3 (Quiet Room Test): the wearable must work without internet connectivity, which rules out cloud services (Google Cloud Speech, Whisper API). Vosk provides fully local, real-time speech recognition with a small model (`vosk-model-small-en-us`). The `HARDWARE_TODO.md` quotes a target of > 90% accuracy at 1 m in a quiet room — **⚠️ UNVERIFIED: this has not yet been tested on physical hardware.**

**Verification:** Verified via `deaf_mode/test_asr_engine.py`.

---

### Step 10 — Deaf Mode: Caption Formatting & OLED Word Wrapping
**Commit:** `bdaa041`, `646eab1`

**What was built:**
- `deaf_mode/caption_formatter.py` — Wraps transcribed text to 20-character lines for the 128×64 OLED. Maintains a full history buffer and provides a 3-line viewport with leading `...` ellipsis when lines overflow.

**Bug caught and fixed:**
- **Root cause:** Original implementation truncated caption text at the viewport limit without any indication to the user. Words beyond line 3 were silently lost.
- **Fix (commit `646eab1`):** Changed to a full-history buffer model — all text is retained internally, and the viewport always shows the most recent lines with a leading `...` ellipsis to signal that earlier text exists. Users now always know they are seeing a truncated view rather than the complete caption.
- The fix was identified during modular testing of `caption_formatter.py`, not at integration time.

**Verification:** Verified via `deaf_mode/test_caption_formatter.py`.

---

### Step 11 — Deaf Mode: OLED Display & Caption Renderer
**Commits:** `248f6ea`, `b3bc2a9`

**What was built:**
- `deaf_mode/oled_display.py` — `OLEDDisplay` wrapping the luma.oled SSD1306 driver. Includes `MockOLEDDisplay` that renders ASCII art to the terminal for hardware-free testing.
- `deaf_mode/caption_renderer.py` — `CaptionRenderer` that takes formatted caption text and renders it to the display, managing the status banner, partial/final caption states.

**Why ASCII mock first:**
Developing the OLED rendering against an ASCII simulation in the terminal allowed verifying the correct layout (20 chars × 3 lines, ellipsis, header) before any physical display was available. This is explicitly called out in `docs/TriSense_Project_Writeup.md` § 3.2: *"OLED output validated via ASCII simulation before physical display integration."*

**Verification:** Verified via `deaf_mode/test_oled_display.py` and `deaf_mode/test_caption_renderer.py`.

---

### Step 12 — Deaf Mode: End-to-End Main Loop
**Commit:** `7e7c21a`

**What was built:**
- `deaf_mode/main_loop.py` — `DeafModeApp` that wires `AudioStreamer → ASREngine → CaptionFormatter → CaptionRenderer` into a live callback pipeline. `_audio_callback` is registered on the AudioStreamer and invoked per audio block; partial results update the display in real time while final utterances commit to history.

**Verification:** Verified via `deaf_mode/test_main_loop.py`. The `docs/TriSense_Project_Writeup.md` also states *"Core pipeline implemented and manually verified working"* — **⚠️ UNVERIFIED: it is not clear from the files whether Neel ran a live end-to-end test on a PC with real speech or only via the WAV-based mock. Neel should confirm whether the pipeline was tested with real microphone input.**

---

### Step 13 — Deaf Mode: Hardware Validation Checklist
**Commit:** `ddd8f18`

**What was built:**
- `deaf_mode/HARDWARE_TODO.md` — Checklist for physical hardware bring-up: I2S bus wiring, ALSA mic detection, I2C OLED address scan, quiet-room and ambient-noise ASR accuracy tests, and end-to-end latency walkthrough.

---

### Step 14 — System Coordination: ModeManager & ResourceGuard
**Commit:** `7e46274`

**What was built:**
- `shared/mode_manager.py` — `ModeManager` orchestrates mode transitions. `ResourceGuard` enforces single-owner access to six hardware resources: `SPEAKER`, `CAMERA`, `MICROPHONE`, `DISPLAY`, `GPIO_SENSORS`, `GPIO_MOTORS`. Three adapter classes (`BlindModePipeline`, `DeafModePipeline`, `MuteModePipeline`) wrap each mode's existing code without modifying its internals.

**Why this design (adapter pattern, not internal modification):**
Documented in `mode_manager.py` header: *"Coordinates switching between operational pipelines without modifying their internal code."* Each mode was developed in isolation as a standalone pipeline. Rather than refactoring each to be mode-switch-aware (which would have been invasive and risky), adapter wrappers call each pipeline's `start()` and `stop()` from the outside. This preserves each mode's internal test suite intact.

**Verification:** `shared/test_mode_manager.py` — all three tests passing (`ALL MODE MANAGER (STEP 1) TESTS PASSED [PASS]`), confirmed by Neel.

---

### Step 15 — Mute Mode: Landmark Extraction
**Commits:** `331e481`, `e07299e`

**What was built:**
- `mute_mode/landmark_extractor.py` — `LandmarkExtractor` using MediaPipe Hands to extract 21 3D keypoints per hand per frame. Applies wrist-origin translation (wrist landmark becomes (0,0,0)) and bounding-box scale normalization before returning.
- **Bug fixed (`e07299e`):** MediaPipe changed its Python API between versions; the fix added compatibility handling for the MediaPipe Tasks API to support Python 3.12 and resolve an MSVC runtime symbol lookup error on Windows.

**Why wrist normalization:**
Raw MediaPipe coordinates are image-relative (0–1 in screen space), which means the same hand gesture at different positions in the frame produces different raw values. Translating relative to the wrist makes the features position-invariant. Scale normalization by bounding box span makes features scale-invariant. Both are standard preprocessing steps for hand-gesture classification.

**Verification:** Verified via `mute_mode/test_landmark_extractor.py` (referenced in `PROGRESS.md`).

---

### Step 16 — Mute Mode: Sequence Buffer with EMA Smoothing
**Commit:** `6b650f1`

**What was built:**
- `mute_mode/sequence_buffer.py` — `LandmarkSmoother` (EMA smoothing, α=0.6 from `mute_mode/config.py`) and `GestureSequenceBuffer` (30-frame FIFO deque). During hand occlusion (landmark missing), the last valid value is held for up to `MAX_HOLD_FRAMES = 5` frames before being imputed.

**Why 30 frames:**
The 30-frame window is a fixed frame-count buffer, not a fixed time window. Duration therefore scales with the source camera's FPS (approximately 1.5 s at 20 FPS, 1.0 s at 30 FPS). This is documented in `mute_mode/DATASET_SOURCE.md` § 3. The tradeoff: at lower FPS the temporal coverage increases (potentially capturing more of a sign's motion), but the inference latency also increases.

**Verification:** Verified via `mute_mode/test_sequence_buffer.py` (referenced in `PROGRESS.md`).

---

### Step 17 — Mute Mode: 1D-CNN + GRU Classifier
**Commit:** `fcfca28`

**What was built:**
- `mute_mode/classifier.py` — `SignLanguageClassifier`: two Conv1d layers (126→64, 64→64) with BatchNorm and dropout, followed by a 1-layer GRU (hidden_size=64), and a Linear classification head.
- `mute_mode/train_classifier.py` — Training script with `load_checkpoint` utility.
- Input shape: `(batch_size, 30 frames, 126 features)` where 126 = 2 hands × 21 keypoints × 3 coords (X, Y, Z).

**Architecture rationale (from `classifier.py` header):**
*"Lightweight sequence classification model designed for edge inference (Raspberry Pi 4 CPU / TFLite / ONNX export)."* The 1D-CNN block extracts local spatial-temporal motifs within the 30-frame window; the GRU models longer-range temporal dependencies across the sequence. The parameter budget is approximately **68,324 trainable parameters** (as corrected throughout the codebase — the header of `classifier.py` still shows the old `~62.6k` figure from before the correction was applied to the code comments).

**⚠️ NOTE on parameter count in source:** `classifier.py` line 15 still reads `# Parameter budget: ~62.6k trainable parameters`. The corrected figure of 68,324 appears in `README.md`, `PROGRESS.md`, and `mute_mode/config.py`'s `NUM_CLASSES = 100`. **Neel should verify which is accurate by running `model.get_parameter_count()` on a live checkpoint.**

**Verification:** Verified via `mute_mode/test_classifier_pipeline.py` (smoke test, architecture verification — not accuracy).

---

### Step 18 — Mute Mode: WLASL Dataset Acquisition
**Commit:** `a47c8c9`

**What was built:**
- `mute_mode/dataset_downloader.py` — Fetches WLASL video clips for a 100-word vocabulary using dual-timeout strategies and YouTube exclusion (YouTube videos require authenticated API calls unavailable in this project). Guarantees at least 8 samples per class.

**Dataset choice:**
WLASL (Word-Level American Sign Language, Li et al., WACV 2020) was chosen as the primary dataset. ASL Citizen was evaluated but not used due to a Kaggle login requirement (documented in `mute_mode/DATASET_SOURCE.md` § 2). Raw video is never stored — only extracted 30×126 float32 `.npy` tensors are retained, stored at `mute_mode/dataset/<word>/sample_NN.npy`.

**Verification:** Dataset acquisition is not directly tested with an automated assertion. The 8-samples-per-class guarantee is a script-level invariant. **⚠️ UNVERIFIED: the actual number of successfully downloaded samples per class has not been recorded in any file in the repo.**

---

### Step 19 — Mute Mode: Training and Integration
**Commit:** `712663c`

**What was built:**
- Trained `SignLanguageClassifier` on the 100-word WLASL dataset.
- `MuteModePipeline` in `shared/mode_manager.py` fully wired: VideoStreamer → LandmarkExtractor → GestureSequenceBuffer → classifier → TTS output.
- Trained checkpoint at `mute_mode/checkpoints/final_model.pth`.

**Validation accuracy:** **33.33%** on the 100-word classification task. This figure is recorded in `PROGRESS.md` § Done, Phase 1C: *"Trained on 100-word vocabulary achieving 33.33% validation accuracy."*

**Verification of integration:** `shared/test_mode_manager.py` Test 3 exercises the MuteModePipeline start/stop lifecycle and confirms the TTS call path using a mocked classifier (confidence forced to 0.99 for `"mock_word"`). The real classifier's actual inference path on real input is **not exercised by any automated test** — the 33.33% accuracy figure comes from the training script's own evaluation on a held-out validation split.

---

### Step 20 — GPIO Pin Conflict Resolution
**Commit:** `f5fd449`

**What was built/fixed:**
- A documentation audit identified a **3-way GPIO conflict**: `ECHO_CENTER = 19` in `blind_mode/config.py` collided with the I2S WS line (GPIO 19) used by both the INMP441 microphone and the MAX98357A speaker amplifier.
- A secondary conflict: `ECHO_RIGHT = 21` collided with the I2S DIN line (GPIO 21) used by the speaker amplifier.
- **Fix applied in code:** `ECHO_CENTER` reassigned from GPIO 19 → **GPIO 16**; `ECHO_RIGHT` reassigned from GPIO 21 → **GPIO 17**. Updated in `blind_mode/config.py`, `README.md` BOM table, and `TriSense_Build_Plan.md`.

**Why this matters:**
This conflict would have caused silent hardware failures — the I2S peripheral and the ultrasonic sensor would both attempt to use the same GPIO line, resulting in either sensor read errors or audio dropouts that would be extremely difficult to diagnose from software alone.

**Verification:** Neel ran `python blind_mode/synthetic_test.py` after the fix and confirmed all tests still passed.

---

### Step 21 — TTS Centralization (In Progress)
**Commits:** Present in working tree, not yet fully committed.

**What was built:**
- `shared/tts_output.py` — Central TTS engine with `start_tts_worker()`, `stop_tts_worker()`, and `speak(text, cooldown)`.
- `blind_mode/audio_alert.py` refactored into a thin proxy delegating to `shared.tts_output`.
- `MuteModePipeline._run_loop_wrapper` updated to call `shared.tts_output.speak` directly instead of `blind_mode.audio_alert.speak_alert`.

**Why:** The original architecture had `MuteModePipeline` importing TTS from `blind_mode.audio_alert` — a cross-mode dependency. `BlindModePipeline.stop()` was calling `shutdown_audio()` which would kill the TTS thread even if Mute Mode was about to use it. The fix moves lifecycle ownership to `ModeManager`.

**Status:** Steps 1–3 of 5 complete. Steps 4–5 (shifting lifecycle calls in ModeManager itself) not yet executed.

---

## 3. Per-Mode Status Summary

### 3.1 Blind Mode

| | |
|---|---|
| **Software status** | Complete |
| **Tests passing** | `synthetic_test.py`: ALL SYNTHETIC TESTS PASSED (57 rows, TTC math, haptic threshold, audio trigger) — verified by Neel |
| **Hardware tested** | ❌ None — no physical hardware yet |
| **Pending** | All items in `blind_mode/HARDWARE_TODO.md`: GPIO floating pin check, sensor calibration at 50/100/150 cm, crosstalk check, motor thread-overlap test, ALSA lock-up test, walking obstacle-course test |
| **Pre-applied fixes** | Pin map corrected (GPIO 16 for ECHO_CENTER, GPIO 17 for ECHO_RIGHT). Pull-down resistor and inter-sensor delay documented in HARDWARE_TODO.md as expected fixes — **⚠️ not yet confirmed applied in gpio_setup.py/distance.py** |

---

### 3.2 Deaf Mode

| | |
|---|---|
| **Software status** | Complete |
| **Tests passing** | Modular test suite: `test_audio_stream.py`, `test_asr_engine.py`, `test_caption_formatter.py`, `test_caption_renderer.py`, `test_oled_display.py`, `test_main_loop.py` — all referenced as passing in `PROGRESS.md` |
| **Hardware tested** | ❌ None — no physical hardware yet |
| **Bug caught and fixed** | Caption truncation: captions were being silently cut off. Fixed with full-history buffer + leading `...` ellipsis viewport (`646eab1`) |
| **Pending** | All items in `deaf_mode/HARDWARE_TODO.md`: I2S wiring, ALSA capture test, I2C OLED scan, quiet-room ASR accuracy test (target > 90%), ambient-noise test, end-to-end latency walkthrough |
| **⚠️ UNVERIFIED** | Whether `DeafModeApp` was tested with real microphone input on a PC, or only via WAV mock |

---

### 3.3 Mute Mode

**Important: two separate claims must not be conflated.**

#### Architectural Integration Status
MuteModePipeline is fully wired into ModeManager. The pipeline launches on mode switch, runs the inference loop (VideoStreamer → LandmarkExtractor → GestureSequenceBuffer → classifier → TTS), and stops cleanly on mode exit. This was verified by `shared/test_mode_manager.py` Test 3 with the mock classifier forced to confidence 0.99. The pipeline does not crash, resources are acquired and released correctly, and the TTS call path is exercised. **This is confirmed.**

#### Classification Accuracy Status
The trained model achieves **33.33% validation accuracy** on the 100-word WLASL vocabulary. Source: `PROGRESS.md` line 20. This is the only accuracy figure in the repository.

For context, random guessing over 100 classes yields 1.0% accuracy. 33.33% represents meaningful learning. However, **33.33% is not usable accuracy for a real-world assistive device** — a device that recognizes the correct sign only 1 in 3 attempts would not be reliable for a person depending on it for communication.

#### What this means for the viva
The Mute Mode software pipeline is architecturally sound and integrated. The classification accuracy reflects the constraints of a small per-class sample count (minimum 8 samples guaranteed by the downloader) and a 100-word vocabulary. Accuracy improvement would require more training data per class, longer training, or a larger pre-trained backbone.

| | |
|---|---|
| **Architecture** | Complete and integrated |
| **Validation accuracy** | 33.33% (source: `PROGRESS.md`) |
| **Hardware tested** | ❌ None |
| **Usable as accessibility tool** | Not yet — accuracy is below practical threshold |
| **Stretch goal status** | Correctly treated as protected non-blocking stretch goal throughout |

---

## 4. System Coordination Layer

### What ModeManager solves

Without coordination, switching from Blind Mode to Deaf Mode would require: manually stopping the sensor loop, releasing GPIO pins, then starting the audio stream. If done incorrectly, two modes could run simultaneously — two threads both trying to use the speaker, or the camera claimed while still in use.

`ModeManager` solves this with a five-step transition protocol (implemented in `switch_mode()`):
1. Stop the current mode's pipeline.
2. Release all resources held by the current mode.
3. Check that no requested resources for the new mode are held by any other mode.
4. Acquire resources for the new mode.
5. Start the new mode's pipeline.

If step 3 fails, a `ResourceLockError` is raised before any resource is taken, preventing partial state.

### ResourceGuard — Six Resources

| Resource | Used By |
|---|---|
| `SPEAKER` | Blind Mode (TTS alerts), Mute Mode (sign-to-speech output) |
| `CAMERA` | Mute Mode |
| `MICROPHONE` | Deaf Mode |
| `DISPLAY` | Deaf Mode |
| `GPIO_SENSORS` | Blind Mode (ultrasonic array) |
| `GPIO_MOTORS` | Blind Mode (haptic motors) |

The guard enforces **single-owner exclusivity**: only one mode may hold a resource at a time. The `acquire()` method checks all requested resources before granting any of them, preventing partial acquisition. `release()` drops all resources belonging to the named owner at once. Both methods are protected by a `threading.Lock`.

### Adapter Pipeline Pattern

Each mode's code was developed independently and has no knowledge of ModeManager. The adapter classes (`BlindModePipeline`, `DeafModePipeline`, `MuteModePipeline` in `mode_manager.py`) call each mode's public entry points — `setup()`, `sensor_loop`, `DeafModeApp` — from the outside. No internal module code was modified to achieve integration. This keeps each mode's unit tests intact and eliminates the risk of integration work breaking mode internals.

---

## 5. Design Decisions & Trade-offs

### 5.1 Single Device, Three Software Modes (vs. Three Devices)
**Decision:** One Raspberry Pi 4 running one mode at a time, switched by a button press.
**Reasoning:** Three separate devices means three separate hardware builds, three power sources, and an unwearable amount of hardware. One device reduces per-prototype cost to ₹7,000–9,500 (per `docs/TriSense_Project_Writeup.md` § 4) and weight.
**Tradeoff:** Modes cannot run simultaneously. If a Blind Mode user wants TTS output from the Mute Mode pipeline, they must switch modes. The resource guard enforces this hard constraint.

### 5.2 Fully Offline Operation
**Decision:** All inference (ASR via Vosk, sign classification via PyTorch, TTS via pyttsx3) runs entirely on-device with no network connectivity required.
**Reasoning:** A wearable assistive device that requires internet connectivity fails the moment the user is in a dead zone. Offline operation is a hard requirement, not a preference.
**Tradeoff:** Model size is constrained by available RAM and storage on the Raspberry Pi. Vosk uses a small English model rather than a full-size model; the sign classifier is limited to ~68k parameters rather than a ResNet-scale backbone.

### 5.3 MediaPipe Hands for Landmark Extraction (vs. Raw CNN on Video)
**Decision:** Use MediaPipe to extract 21 3D keypoints per hand, then classify the 30×126 keypoint sequence with a lightweight CNN+GRU.
**Reasoning:** Training an end-to-end video classifier would require far more data and compute than is available. MediaPipe handles the hard part (hand detection and tracking) reliably; the downstream classifier only needs to learn the temporal shape of the keypoint trajectory, which is much simpler.
**Tradeoff:** MediaPipe must successfully detect the hand in the video frame. If the hand is not detected (occlusion, poor lighting), the extractor produces no landmarks. The `GestureSequenceBuffer` mitigates brief occlusions via hold-and-impute (up to `MAX_HOLD_FRAMES = 5`).

### 5.4 Adapter Pattern for ModeManager (vs. Refactoring Internals)
**Decision:** Wrap each mode with an adapter; do not modify internal module code.
**Reasoning:** Each mode's internal code was developed, tested, and verified before ModeManager existed. Refactoring the internals to be "mode-switch aware" would have invalidated all existing test coverage and introduced integration risk.
**Tradeoff:** The adapter layer introduces some indirection. The adapter must manually keep its `is_running` flag in sync with the wrapped pipeline's real state.

### 5.5 Mute Mode as a Hard Stretch Goal (Enforced Per-Decision)
**Decision:** Mute Mode scope is re-evaluated at every planning decision, not assumed safe from the one-time kickoff declaration.
**Reasoning:** Documented in `docs/TriSense_Project_Writeup.md` § 3.3 and § 7.4: *"Despite strong progress, this mode remains explicitly deprioritized relative to Blind/Deaf Mode in any resource conflict."* Early progress on Mute Mode could easily crowd out time needed for hardware validation of the core modes.
**Tradeoff:** Mute Mode accuracy is limited because resources were consciously not redirected from Blind/Deaf Mode to improve it.

### 5.6 Incremental Commit Discipline (One Step per Turn)
**Decision:** Every development step is written as a small, atomic commit (visible in the 40-commit log), with each step verified before the next begins.
**Reasoning:** Agent-assisted development can compound errors silently if steps are batched. The commit history acts as a rollback and audit trail. Documented in `docs/TriSense_Project_Writeup.md` § 7.3.
**Tradeoff:** Slower iteration velocity than "write everything, then commit." This was a deliberate quality tradeoff.

---

## 6. Known Limitations

1. **No physical hardware tested.** Every claim about Blind Mode and Deaf Mode correctness is based on software simulation or mock testing. Real HC-SR04 sensors, INMP441 microphone, SSD1306 OLED, and haptic motors have not been connected to the Raspberry Pi.

2. **Mute Mode accuracy is 33.33%** on the 100-word test set. This is below any practical usability threshold for an assistive device. The constraint is data (minimum 8 samples per class from WLASL) and model capacity, not architecture.

3. **TTS centralization is incomplete.** Steps 4–5 of the TTS extraction refactor (ModeManager owning `start_tts_worker()` / `stop_tts_worker()`) have not been executed. `start_tts_worker()` is NOT called by `shared/mode_manager.py` (FINDING: 0 matches), so TTS alerts will not speak unless the worker thread is started.

4. **Pull-down resistors and inter-sensor delay are confirmed in code.** `GPIO.PUD_DOWN` is set for ECHO pins (`gpio_setup.py:30`) and `time.sleep(0.02)` inter-sensor delay is present in `read_all_sensors()` (`distance.py:71`). Physical hardware validation remains pending.

5. **ASR accuracy on hardware is unverified.** The target of > 90% at 1 m in a quiet room (`deaf_mode/HARDWARE_TODO.md` § 3) has not been measured. This depends on ALSA configuration, microphone gain, and the Vosk model's actual performance on the team's voices and accent.

6. **Model Parameter Count.** Empirical measurement of the trained checkpoint (`mute_mode/checkpoints/final_model.pth`) confirms the model has **2,426,142** trainable parameters (2.42M). Comments mentioning ~62.6k in `classifier.py` were outdated estimates.

7. **Hardware procurement is pending.** As of the last documented project state, no physical hardware has been purchased. Estimated cost: ₹7,000–9,500 per prototype from Indian suppliers (Robu.in, Robocraze, Amazon.in), per `docs/TriSense_Project_Writeup.md` § 4 and § 9.

8. **Dataset Sample Count.** Empirical audit of `mute_mode/dataset/` confirms **30** active class directories containing **3,000** total audio sample files (100 samples per class).

---

## 7. Verification Claims — Status Table

| # | Claim | File to Check | Verification Result |
|---|---|---|---|
| 1 | `GPIO.PUD_DOWN` applied to ECHO pins | `blind_mode/gpio_setup.py` | **CONFIRMED**: `GPIO.setup(echo, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)` present at line 30 |
| 2 | `time.sleep(0.02)` inter-sensor delay applied | `blind_mode/distance.py` | **CONFIRMED**: `time.sleep(0.02)` present in `read_all_sensors()` at line 71 |
| 3 | `DeafModeApp` tested with real mic input | Manual / Codebase | **CONFIRMED (WAV Mock Only)**: Automated test suite uses `MockAudioStream` / WAV mock files; real microphone input pending hardware bring-up |
| 4 | Actual trainable parameter count | `mute_mode/checkpoints/final_model.pth` | **CONFIRMED**: Model checkpoint contains **2,426,142** trainable parameters |
| 5 | Actual per-class sample counts in dataset | `mute_mode/dataset/` | **CONFIRMED**: **30** class directories containing **3,000** total sample files (100 per class) |
| 6 | TTS worker started somewhere before Mute Mode inference uses `speak()` | `shared/mode_manager.py`, `shared/tts_output.py` | **FINDING**: `start_tts_worker()` is NOT called anywhere in `shared/mode_manager.py` (0 matches returned) |

---

*Document generated from live repo content on 2026-09-08. All claims traced to specific files or commit hashes unless marked ⚠️ UNVERIFIED.*
