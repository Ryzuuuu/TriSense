<div align="center">

<img src="assets/banner.svg" alt="TriSense Animated Hero Banner" width="100%" />

[![Typing SVG](https://readme-typing-svg.demolab.com?font=JetBrains+Mono&weight=600&size=16&pause=1000&color=00F0FF&center=true&vCenter=true&width=750&height=35&lines=Spatial+Haptics+%E2%80%A2+Offline+ASR+Subtitles+%E2%80%A2+3D+Sign+Language+Recognition;Embedded+Linux+%E2%80%A2+Raspberry+Pi+4+%E2%80%A2+Real-Time+Sensory+Augmentation;PyTorch+CNN%2BBiGRU+%E2%80%A2+MediaPipe+Hands%2BPose+%E2%80%A2+Vosk+KaldiRecognizer)](https://git.io/typing-svg)

<br />

[![CI](https://img.shields.io/github/actions/workflow/status/Ryzuuuu/TriSense/ci.yml?branch=main&style=for-the-badge&label=CI)](https://github.com/Ryzuuuu/TriSense/actions/workflows/ci.yml)
[![Python Version](https://img.shields.io/badge/python-3.11%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![PyTorch](https://img.shields.io/badge/PyTorch-2.x-EE4C2C?style=for-the-badge&logo=pytorch&logoColor=white)](https://pytorch.org/)
[![MediaPipe](https://img.shields.io/badge/MediaPipe-0.10%2B-008080?style=for-the-badge&logo=google&logoColor=white)](https://ai.google.dev/edge/mediapipe/solutions/guide)
[![Vosk ASR](https://img.shields.io/badge/Vosk_ASR-Offline_Kaldi-009688?style=for-the-badge&logo=linux&logoColor=white)](https://alphacephei.com/vosk/)
[![Hardware Target](https://img.shields.io/badge/Platform-Raspberry_Pi_4-C51A4A?style=for-the-badge&logo=raspberrypi&logoColor=white)](https://www.raspberrypi.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg?style=for-the-badge)](LICENSE)

---

</div>

## Overview

**TriSense** is a wearable, edge-embedded assistive platform for the **Raspberry Pi 4**. One device offers three switchable accessibility modes for people with visual, hearing or speech impairments:

| Mode | Who it helps | What it does |
| :--- | :--- | :--- |
| **Blind** | Visual impairment | Three ultrasonic sensors (left / center / right) measure obstacle distance and closing speed; haptic motors pulse by urgency, close obstacles trigger an alert even when nothing moves, and the device speaks a short warning. |
| **Deaf** | Hearing impairment | A microphone feeds an offline speech recogniser; live captions are formatted and shown on a small OLED. |
| **Mute** | Speech impairment | A camera feeds hand + upper-body landmark trackers; each sign is segmented automatically, classified among 100 ASL words (**64.5 % top-1 on the official WLASL test split**) and spoken aloud when the model is confident. |

Everything runs **on the device with no internet connection** (cloud APIs are never used at runtime). A thread-safe **Mode Manager** guarantees that only one mode owns the shared peripherals (camera, microphone, speaker, OLED, GPIO) at a time.

The whole stack also runs on a laptop: a bundled mock `RPi.GPIO`, WAV/video file inputs and an ASCII OLED let you develop and test without any hardware, and a browser-based **demo console** drives all three modes live with your microphone, your webcam and draggable obstacles.

---

## Features

- **Blind Mode** - 3-sensor HC-SR04 polling at 10 Hz, median-filtered distances, closing speed from real timestamps, time-to-collision **and** proximity alerts (a static wall still warns you), tiered non-blocking haptic pulses (150 / 300 / 500 ms) and spoken "Obstacle ahead / left / right" alerts, with echo time-outs so a dead sensor can never stall the loop.
- **Deaf Mode** - 16 kHz mono PCM streaming, offline Vosk recognition on a worker thread with partial and final results (the last sentence is flushed when audio ends), caption formatter (capitalisation, punctuation, 20-character wrapping, "..." overflow marker) and a 3-line rolling SSD1306 OLED viewport.
- **Mute Mode** - MediaPipe hand **and** pose landmarks (run in parallel), body-relative hand position plus wrist-relative handshape features, activity-based sign segmentation and a 182,245-parameter CNN + BiGRU classifier over a 100-word ASL vocabulary trained on 1,004 WLASL clips: **64.5 % top-1 / 81.9 % top-5** on the official test split (Phase 1: 33.3 % on a random split).
- **Mode Manager** - exclusive resource locking (`SPEAKER`, `CAMERA`, `MICROPHONE`, `DISPLAY`, `GPIO_SENSORS`, `GPIO_MOTORS`), serialised clean transitions that stop the old pipeline before the new one starts, and a keyboard trigger standing in for the planned GPIO mode button.
- **Shared TTS** - one text-to-speech worker owned by the Mode Manager, with per-phrase cool-downs, a bounded queue that is flushed on every mode switch, and console logging when no speech backend is installed.
- **Demo console** - Flask + Socket.IO web app: drag obstacles or run Blind scenarios, caption your own microphone, sign to your webcam or replay unseen WLASL test clips, hear everything the device says, and watch resource ownership live.
- **Tests** - fast hardware-free pytest suite plus per-module verification scripts (see [Testing](#testing)); CI runs lint and the unit tests on every push.

---

## Architecture

<div align="center">
  <img src="assets/architecture.svg" alt="TriSense Architecture Flow" width="100%" />
</div>

<br />

<div align="center">
  <img src="assets/mode_matrix.svg" alt="TriSense Mode Status Matrix" width="100%" />
</div>

The Mode Manager adapts each pipeline behind a common `start()` / `stop()` interface and declares which resources it needs:

| Mode | Resources acquired | Data flow |
| :--- | :--- | :--- |
| `BLIND` | `SPEAKER`, `GPIO_SENSORS`, `GPIO_MOTORS` | HC-SR04 x3 -> median filter -> closing speed -> time-to-collision + proximity -> haptic pulse / spoken alert |
| `DEAF` | `MICROPHONE`, `DISPLAY` | mic / WAV -> Vosk ASR -> caption formatter -> OLED renderer |
| `MUTE` | `CAMERA`, `SPEAKER` | camera / video -> MediaPipe hands + pose -> sign segmentation -> 32-frame resample -> CNN+BiGRU -> confidence gate -> TTS |

Requesting a mode whose resources are held by another mode raises `ResourceLockError`; `switch_mode()` always tears down the running pipeline first, and a pipeline that fails to start leaves the system in `IDLE` with every resource released.

---

## Core Sensory Pipelines

### 1. Blind Mode - Spatial Collision & Haptics
* **Hardware:** three HC-SR04 ultrasonic sensors, three NPN-driven vibration motors, and a speaker for spoken alerts.
* **Algorithm:** every 100 ms each sensor is read; readings outside 2-400 cm are dropped and the last three pass a median filter. The closing speed `(d_prev - d_now) / dt` uses the **measured** `dt` and is smoothed, speeds under 15 cm/s count as jitter, and time-to-collision `d / speed` selects the haptic pulse: `< 1.5 s` -> 150 ms, `< 1.0 s` -> 300 ms, `< 0.5 s` -> 500 ms. A **proximity** rule (150 ms under 60 cm, 300 ms under 30 cm) covers obstacles that are close but not moving. A centre TTC below 1.0 s or anything closer than 30 cm speaks "Obstacle ahead"; very close side obstacles speak "Obstacle left / right" (`blind_mode/engine.py`).
* **Robustness:** every echo wait is time-limited (30 ms); a timed-out reading becomes `None` and is ignored. Motors are driven by a non-blocking `HapticDriver`, so the sensing loop never stalls while a motor buzzes.

### 2. Deaf Mode - Offline Speech Subtitles
* **Hardware:** INMP441 I2S digital microphone (16 kHz, 16-bit mono PCM) and an SSD1306 128x64 I2C OLED.
* **ASR:** Kaldi-based **Vosk** (`vosk-model-small-en-us`) with streaming partial results and utterance endpointing. With a live microphone the audio callback only queues blocks and a worker thread runs Vosk, so no speech is dropped on a slow CPU.
* **Viewport:** automatic capitalisation and punctuation, 20-character word-safe wrapping, a leading `...` when older text scrolls off, and a 3-line rolling history.

### 3. Mute Mode - Sign Language Recognition (v2)
* **Landmarks:** MediaPipe `HandLandmarker` (21 3D keypoints per hand) **plus** `PoseLandmarker` for the upper body, so the model sees where the hands are and how they move, not only their shape (`mute_mode/holistic.py`, `mute_mode/features.py`).
* **Segmentation:** a sign starts when a hand appears and ends when the hands drop; the segment is resampled to 32 frames exactly as in training (`mute_mode/recognizer.py`).
* **Classifier:** `SignClassifierV2` - temporal separable CNN + BiGRU + attention pooling, **182,245 parameters (~0.7 MB)**, 100-word ASL vocabulary trained on 1,004 [WLASL](https://github.com/dxli94/WLASL) clips.
* **Accuracy (official WLASL test split):** **64.5 % top-1 / 81.9 % top-5** for the device model (Phase 1: 33.3 % on a random split). With the confidence gate it speaks on about half of the signs and is right 90.6 % of the time when it does. Details and ablations: [`docs/PHASE2_IMPROVEMENTS.md`](docs/PHASE2_IMPROVEMENTS.md).
* The Phase 1 recogniser (`classifier.py`, 68,324 parameters) is kept as a fallback when no v2 checkpoint is present.

### 4. Mode Manager - Resource Orchestration
* **Core:** `shared/mode_manager.py` - `ResourceGuard` (single-owner locks) and `ModeManager` (transitions, error recovery, shared TTS lifecycle).
* **Trigger:** `handle_key_input()` maps `1` / `2` / `3` to Blind / Deaf / Mute and `0` / `q` to idle - a desktop stand-in for the physical GPIO button planned for the Pi.

---

## Tech Stack

| Area | Technology |
| :--- | :--- |
| Language | Python 3.11+ |
| Sign recognition | PyTorch (CNN + BiGRU), MediaPipe Tasks `HandLandmarker` + `PoseLandmarker`, OpenCV, NumPy |
| Speech recognition | Vosk / Kaldi (offline), `sounddevice` |
| Speech output | `pyttsx3` (offline TTS) |
| Display & hardware | `luma.oled` + Pillow (SSD1306), `RPi.GPIO` (mocked on PCs) |
| Emulator | Flask, Flask-SocketIO |
| Quality | pytest, Ruff, GitHub Actions |

---

## Hardware Bill of Materials (BOM) & Pinout

| Peripheral | Controller / Protocol | Raspberry Pi 4 GPIO Pin | Function / Description |
| :--- | :--- | :--- | :--- |
| **HC-SR04 Left** | GPIO TTL | `GPIO 5` (Trig), `GPIO 6` (Echo) | Left spatial distance sensor (~30° left of center) |
| **HC-SR04 Center** | GPIO TTL | `GPIO 13` (Trig), `GPIO 16` (Echo) | Center spatial distance sensor (straight ahead) |
| **HC-SR04 Right** | GPIO TTL | `GPIO 26` (Trig), `GPIO 17` (Echo) | Right spatial distance sensor (~30° right of center) |
| **Haptic Motor Left** | GPIO (NPN transistor) | `GPIO 23` | Left tactile vibration alert |
| **Haptic Motor Center** | GPIO (NPN transistor) | `GPIO 24` | Center tactile vibration alert |
| **Haptic Motor Right** | GPIO (NPN transistor) | `GPIO 25` | Right tactile vibration alert |
| **INMP441 I2S Mic** | I2S Digital Audio | `GPIO 18` (CLK), `GPIO 19` (WS), `GPIO 20` (SD) | 16 kHz 16-bit Mono PCM digital input |
| **MAX98357A I2S Amp** | I2S Digital Audio | `GPIO 18` (BCLK), `GPIO 19` (LRC), `GPIO 21` (DIN) | I2S speaker amplifier for TTS output |
| **SSD1306 OLED** | I2C (`0x3C`) | `GPIO 2` (SDA), `GPIO 3` (SCL) | 128x64 subtitle & status display |
| **Raspberry Pi Camera V2** | CSI / USB Video | `CAM / USB 2.0` | Real-time video stream for MediaPipe |

> For complete hardware wiring, I2S overlay configuration (`/boot/config.txt`), and acoustic calibration steps, see [`blind_mode/HARDWARE_TODO.md`](blind_mode/HARDWARE_TODO.md) and [`deaf_mode/HARDWARE_TODO.md`](deaf_mode/HARDWARE_TODO.md).

---

## Getting Started

### 1. Install

```bash
git clone https://github.com/Ryzuuuu/TriSense.git
cd TriSense

python -m venv venv
source venv/bin/activate          # Linux / macOS
# .\venv\Scripts\Activate.ps1     # Windows PowerShell

pip install --upgrade pip
pip install -r requirements.txt   # use requirements-dev.txt to also get pytest + ruff
```

On the Raspberry Pi also run `pip install RPi.GPIO luma.oled`. On a PC the bundled mock `RPi.GPIO` is picked up automatically.

### 2. Models & sample data

Large or downloadable files are **not stored in git** (see `.gitignore`). Run the helpers from the repository root:

| File | Needed for | How to get it |
| :--- | :--- | :--- |
| `models/vosk-model-small-en-us/` (~40 MB) | Real Deaf Mode recognition | `python deaf_mode/download_model.py` |
| `mute_mode/models/hand_landmarker.task`, `pose_landmarker_lite.task` | Mute Mode landmarks | downloaded automatically on first use |
| `deaf_mode/real_speech.wav` | Deaf Mode demo / emulator input | `python deaf_mode/get_real_speech_sample.py` (or `generate_real_speech_wav.py` offline) |
| `mute_mode/raw_videos/` | Retraining, test clips in the demo console | `python mute_mode/wlasl_fetch.py` |
| `mute_mode/real_sign.mp4` | Mute Mode mock camera (tests, emulator) | any short clip of a signing hand saved at this path |

Without the Vosk model the ASR engine falls back to a mock recogniser, and without the WAV the Deaf Mode input is silence, so the unit tests and the rest of the system still run. The trained classifiers (`mute_mode/checkpoints/sign_v2.pth`, plus the Phase 1 model) and the extracted landmark datasets (`mute_mode/landmarks/` for v2, `mute_mode/dataset/` for v1) are included.

---

## Usage

### Demo console (web emulator)

```bash
python emulator_server.py
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000) in Chrome or Edge. Every panel drives the real ModeManager and pipelines; only the hardware is simulated.

| Mode | What you can show |
| :-- | :-- |
| **Blind** | Drag obstacles in front of the three sensors (or use sliders) and watch distance, closing speed, TTC, haptic pulses and spoken alerts. Scenario buttons: walking toward a wall, standing at a wall (proximity alert), side obstacle, person passing, noisy echo, dead sensor. |
| **Deaf** | Stream your **microphone** to the offline Vosk recogniser and see the exact 3-line OLED view plus a transcript, or play the recorded sample sentence. |
| **Mute** | Sign to your **webcam** or play one of the held-out WLASL **test clips** (with the true label shown). Landmarks are drawn live, the recording state shows when a sign is captured, and the top-3 predictions appear with a correct / wrong verdict. |

Everything the device would say is read aloud by the browser and logged, and ResourceGuard ownership updates live. Keys `0`-`3` switch modes. The page loads the Socket.IO client from a CDN, so the browser needs internet access the first time.

### Mode Manager from Python

```python
from shared.mode_manager import ModeManager

manager = ModeManager()
manager.switch_mode("BLIND")                                   # ultrasonic + haptics (mock GPIO on a PC)
manager.switch_mode("DEAF", wav_path="deaf_mode/real_speech.wav", use_mock=True)
manager.switch_mode("MUTE", use_mock=True)                     # classify the mock video stream
manager.handle_key_input("0")                                  # back to IDLE (same as switch_mode("IDLE"))
manager.shutdown()                                             # stop the active pipeline and the TTS worker
```

### Retraining the sign classifier

```bash
python mute_mode/wlasl_fetch.py --workers 16     # download every reachable WLASL clip for the 100 words
python mute_mode/build_landmarks.py --workers 8  # hands + upper body landmarks -> mute_mode/landmarks/
python mute_mode/train_v2.py --deploy            # official-split evaluation, then checkpoints/sign_v2.pth
python mute_mode/eval_live.py                    # stream test videos through the live recogniser
```
The extracted landmarks (`mute_mode/landmarks/`) are committed, so retraining does not require downloading the videos.

---

## Testing

```bash
# Fast, hardware-free unit tests (also run in CI)
pip install -r requirements-dev.txt
pytest
ruff check .
```

Each subsystem also ships an end-to-end verification script that exercises the real components (models, video and WAV files) with mock hardware. Run them from the repository root:

```bash
python blind_mode/synthetic_test.py            # ultrasonic maths, closing speed, haptic intensity
python deaf_mode/test_audio_stream.py          # 16 kHz PCM streaming
python deaf_mode/test_asr_engine.py            # Vosk (needs the model, see above)
python deaf_mode/test_caption_formatter.py
python deaf_mode/test_caption_renderer.py
python deaf_mode/test_oled_display.py
python deaf_mode/test_main_loop.py             # end-to-end Deaf Mode
python mute_mode/test_landmark_extractor.py    # needs mute_mode/real_sign.mp4
python mute_mode/test_sequence_buffer.py       # needs mute_mode/real_sign.mp4
python mute_mode/test_classifier_pipeline.py
python mute_mode/test_dataset_downloader.py
python shared/test_mode_manager.py             # resource locking and mode transitions (slow: loads PyTorch and MediaPipe)
python mute_mode/eval_live.py                  # streams held-out WLASL test videos through the live sign recogniser
```

The pytest suite (59 tests) covers the Blind Mode engine (real timestamps, outliers, proximity alerts), the haptic driver, the TTS queue, the non-blocking Deaf Mode adapter and the Mute Mode v2 features, classifier and segmentation.

---

## Repository Structure

```
TriSense/
├── blind_mode/                # Spatial Collision & Haptic Feedback Pipeline
│   ├── sensor_loop.py         # 10Hz ultrasonic sensor polling & alert loop
│   ├── distance.py            # HC-SR04 raw sensor read with echo timeout
│   ├── collision.py           # Closing speed & time-to-collision computation
│   ├── engine.py              # Filtering, real-time TTC, proximity alerts, speech decisions
│   ├── haptic.py              # TTC -> pulse mapping and non-blocking HapticDriver
│   ├── audio_alert.py         # Spoken-alert front end for the shared TTS worker
│   ├── gpio_setup.py          # BCM pin initialisation & cleanup
│   ├── config.py              # Pin map and timing constants
│   ├── mock_gpio.py           # Simulated HC-SR04 / GPIO (per-sensor distances, MOCK_DISTANCE)
│   ├── mock_lib/RPi/          # Drop-in RPi.GPIO shim used on non-Pi machines
│   ├── synthetic_test.py      # Synthetic sensor value automated test suite
│   ├── test_logger.py         # Live sensor read & CSV logging utility
│   └── HARDWARE_TODO.md       # Hardware wiring & GPIO deployment checklist
├── deaf_mode/                 # Offline Speech-to-Text OLED Subtitle Pipeline
│   ├── audio_stream.py        # 16kHz I2S / WAV / pushed PCM streamer (+ mock_audio.py)
│   ├── asr_engine.py          # Vosk offline Kaldi speech recognition
│   ├── caption_formatter.py   # Punctuation, capitalization, and line-wrapping
│   ├── caption_renderer.py    # OLED subtitle rendering coordinator
│   ├── oled_display.py        # SSD1306 I2C OLED driver + ASCII mock
│   ├── main_loop.py           # End-to-end Deaf mode loop (worker-thread ASR)
│   ├── download_model.py      # Fetches the Vosk model into models/
│   ├── get_real_speech_sample.py / generate_real_speech_wav.py   # Sample audio helpers
│   ├── test_*.py              # Per-component verification scripts
│   └── HARDWARE_TODO.md       # I2S INMP441 & I2C SSD1306 setup guide
├── mute_mode/                 # 3D Sign Language Recognition Pipeline
│   ├── holistic.py            # v2: MediaPipe hands + pose landmarks (parallel)
│   ├── features.py            # v2: body-frame + handshape features, augmentation
│   ├── classifier_v2.py       # v2: CNN + BiGRU + attention classifier (182k params)
│   ├── recognizer.py          # v2: live sign segmentation + prediction
│   ├── wlasl_fetch.py         # v2: parallel WLASL downloader (official splits)
│   ├── build_landmarks.py     # v2: landmark extraction for every downloaded clip
│   ├── train_v2.py            # v2: official-split training, ablations, deploy model
│   ├── eval_live.py           # v2: live-path evaluation on test videos
│   ├── landmarks/             # v2: extracted landmark sequences (1,003 clips)
│   ├── landmark_extractor.py  # v1: MediaPipe Hands 21 (X, Y, Z) keypoint extractor
│   ├── sequence_buffer.py     # v1: EMA temporal smoother & 30-frame FIFO buffer
│   ├── classifier.py          # v1: 1D-CNN + GRU classifier (~68.3k params, fallback)
│   ├── train_classifier.py    # v1: training script & load_checkpoint utility
│   ├── dataset_downloader.py  # v1: WLASL bulk video fetch & landmark dataset builder
│   ├── video_stream.py        # Camera / video file / pushed-frame streamers (+ mock_video.py)
│   ├── checkpoints/           # Trained weights (sign_v2.pth) + evaluation reports
│   ├── dataset/               # v1: extracted (30, 126) landmark tensors per word
│   ├── test_*.py              # Per-component verification scripts
│   └── DATASET_SOURCE.md      # WLASL provenance and citation
├── shared/                    # Common System Resources
│   ├── mode_manager.py        # Thread-safe multi-mode resource orchestrator
│   ├── tts_output.py          # Central text-to-speech worker
│   └── test_mode_manager.py   # Mode manager & resource locking verification
├── tests/                     # Fast pytest unit tests (no hardware or models)
├── emulator_server.py         # Flask-SocketIO demo console backend (serves templates/)
├── templates/index.html       # Demo console UI (obstacles, mic captions, webcam signs)
├── docs/                      # Academic deliverables: Phase-1 report, Review-1 deck,
│                              # research paper, build notes, PHASE2_IMPROVEMENTS.md
├── assets/                    # Animated SVG architecture & banner graphics
├── requirements.txt           # Runtime / emulator dependencies
├── requirements-dev.txt       # + pytest and ruff
├── pyproject.toml             # pytest and ruff configuration
├── .github/workflows/ci.yml   # Lint + unit tests on push and pull request
├── PROGRESS.md                # Living development roadmap & verification tracker
└── TriSense_Build_Plan.md     # Original build plan
```

---

## Project Status & Limitations

- **Software complete on mock hardware** for all three modes plus the Mode Manager; **not yet deployed on a physical Raspberry Pi** (see the `HARDWARE_TODO.md` checklists). Mute Mode now runs two MediaPipe models per frame (~6 fps on the development laptop), so Pi 4 frame rate still has to be measured.
- **Mute Mode is a word-level recogniser, not a translator:** 64.5 % top-1 on the official WLASL test split for 100 isolated words (2 to 17 training clips per word). It does not handle continuous signing, facial grammar or fingerspelling.
- Deaf Mode uses the small English Vosk model; recognition quality depends heavily on microphone placement and noise.
- The emulator is a local development server (Werkzeug), not a production deployment.

---

## Roadmap

- [x] **Phase 1A**: Blind Mode Software Pipeline & Haptic Mapping
- [x] **Phase 1B**: Deaf Mode Offline ASR Engine & OLED Subtitle Formatter
- [x] **Phase 1C**: Mute Mode - 100-word ASL Vocabulary (WLASL), 734 real training samples, 33.33% validation accuracy, fully integrated under ModeManager
- [x] **Phase 1D**: Mode Manager Resource Locking & Orchestration
- [x] **Phase 2A**: Bug-fix pass on all three modes, Mute Mode v2 (33.3 % -> 64.5 % top-1 on the official split) and a rebuilt live demo console - see `docs/PHASE2_IMPROVEMENTS.md`
- [ ] **Phase 2B**: Model Quantization (ONNX / TFLite INT8 Export) & Edge Latency Profiling
- [ ] **Phase 3**: Physical Raspberry Pi 4 GPIO Deployment & Field Validation

---

## License

Released under the [MIT License](LICENSE).

<div align="center">
  <p><b>TriSense</b> - Designed and Engineered for Linux Edge Computing</p>
</div>
