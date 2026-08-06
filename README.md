<div align="center">

<img src="assets/banner.svg" alt="TriSense Animated Hero Banner" width="100%" />

[![Typing SVG](https://readme-typing-svg.demolab.com?font=JetBrains+Mono&weight=600&size=16&pause=1000&color=00F0FF&center=true&vCenter=true&width=750&height=35&lines=Spatial+Haptics+%E2%80%A2+Offline+ASR+Subtitles+%E2%80%A2+3D+Sign+Language+Recognition;Embedded+Linux+%E2%80%A2+Raspberry+Pi+4+%E2%80%A2+Real-Time+Sensory+Augmentation;PyTorch+1D-CNN%2BGRU+%E2%80%A2+MediaPipe+Hands+%E2%80%A2+Vosk+KaldiRecognizer)](https://git.io/typing-svg)

<br />

[![Python Version](https://img.shields.io/badge/python-3.12%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![PyTorch](https://img.shields.io/badge/PyTorch-2.5%2B-EE4C2C?style=for-the-badge&logo=pytorch&logoColor=white)](https://pytorch.org/)
[![MediaPipe](https://img.shields.io/badge/MediaPipe-1.0%2B-008080?style=for-the-badge&logo=google&logoColor=white)](https://ai.google.dev/edge/mediapipe/solutions/guide)
[![Vosk ASR](https://img.shields.io/badge/Vosk_ASR-Offline_Kaldi-009688?style=for-the-badge&logo=linux&logoColor=white)](https://alphacephei.com/vosk/)
[![Hardware Target](https://img.shields.io/badge/Platform-Raspberry_Pi_4-C51A4A?style=for-the-badge&logo=raspberrypi&logoColor=white)](https://www.raspberrypi.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg?style=for-the-badge)](LICENSE)

---

</div>

## Overview

**TriSense** is an open-source, edge-embedded Linux multi-modal sensory augmentation platform designed for **Raspberry Pi 4**. It combines real-time spatial ultrasonic sensing, offline speech-to-text transcription, and 3D sign language recognition into a unified, modular, low-latency assistive hardware-software ecosystem.

Unlike traditional assistive technologies that rely on cloud APIs or isolated single-function microcontrollers, TriSense operates entirely **at the edge** with zero internet dependency, utilizing shared hardware resources orchestrated by a thread-safe, priority-scheduling mode manager.

---

## Sensory Augmentation Architecture

<div align="center">
  <img src="assets/architecture.svg" alt="TriSense Architecture Flow" width="100%" />
</div>

<br />

<div align="center">
  <img src="assets/mode_matrix.svg" alt="TriSense Mode Status Matrix" width="100%" />
</div>

---

## Core Sensory Pipelines

### 1. Blind Mode — Spatial Collision & Haptics Engine
* **Hardware Interface:** HC-SR04 Ultrasonic Distance Sensor array + PWM Haptic Vibration Drivers & Piezo Audio Alert.
* **Algorithm:** High-frequency 20Hz polling loop mapping spatial distance into linear-mapped vibration pulse intensities and variable audible warning frequencies.
* **Dynamic Range Zones:** Implements multi-threshold collision detection (`SAFE`, `WARN`, `CRITICAL`) with pre-emptive jitter damping and zero-latency haptic feedback.

### 2. Deaf Mode — Offline Speech Subtitle Viewport
* **Hardware Interface:** INMP441 I2S Digital Microphone (16 kHz, 16-bit Mono PCM) + SSD1306 128×64 I2C OLED Display.
* **ASR Engine:** Offline Kaldi-based **Vosk** speech recognition (`vosk-model-small-en-us`) supporting streaming partial transcriptions and word-boundary detection.
* **Viewport Formatter:** Automatic punctuation and capitalization, 20-character line wrapping, ellipsis (`...`) overflow indication, and 3-line rolling subtitle display history.

### 3. Mute Mode — 3D Sign Language Recognition Pipeline
* **Landmark Extractor:** Real-time 3D hand tracking via **MediaPipe Hands** (`HandLandmarker`), extracting 21 $(X, Y, Z)$ spatial keypoints per hand normalized relative to wrist origin and bounding scale.
* **Temporal Smoothing & Buffer:** Exponential Moving Average (EMA, $\alpha=0.6$) coordinate jitter suppression combined with a 30-frame rolling FIFO sequence buffer (`GestureSequenceBuffer`) and hold-last-good-value occlusion imputation.
* **Edge Neural Classifier:** Lightweight **1D-CNN + GRU** hybrid classifier (`SignLanguageClassifier`, **62,604 trainable parameters**) for **100-word** American Sign Language (ASL) vocabulary classification (trained on the WLASL dataset).

### 4. Mode Manager — Resource Orchestration
* **Software Core:** Thread-safe supervisor (`shared/mode_manager.py`) governing mutually exclusive access to shared peripheral resources (Camera, Audio I2S/Speaker, OLED I2C).
* **Hardware Interrupts:** GPIO button interrupt trigger (with keyboard input simulation for local desktop development) for seamless mode switching.

---

## Hardware Bill of Materials (BOM) & Pinout

| Peripheral | Controller / Protocol | Raspberry Pi 4 GPIO Pin | Function / Description |
| :--- | :--- | :--- | :--- |
| **HC-SR04 Ultrasonic** | GPIO TTL | `GPIO 23` (Trig), `GPIO 24` (Echo) | 20Hz spatial distance polling array |
| **Haptic Motor / Alert** | GPIO PWM | `GPIO 18` (PWM0) | Pulse-width modulated tactile alert |
| **INMP441 I2S Mic** | I2S Digital Audio | `GPIO 18` (CLK), `GPIO 19` (WS), `GPIO 20` (SD) | 16 kHz 16-bit Mono PCM digital input |
| **SSD1306 OLED** | I2C (`0x3C`) | `GPIO 2` (SDA), `GPIO 3` (SCL) | 128×64 subtitle & status display |
| **Raspberry Pi Camera V2** | CSI / USB Video | `CAM / USB 2.0` | Real-time video stream for MediaPipe |

> For complete hardware wiring, I2S overlay configuration (`/boot/config.txt`), and acoustic calibration steps, see [`blind_mode/HARDWARE_TODO.md`](blind_mode/HARDWARE_TODO.md) and [`deaf_mode/HARDWARE_TODO.md`](deaf_mode/HARDWARE_TODO.md).

---

## Quick Start & Verification Suite

### 1. Local Environment Setup
```bash
# Clone the repository
git clone https://github.com/Ryzuuuu/TriSense.git
cd TriSense

# Create and activate Python 3.12+ virtual environment
python -m venv venv
# On Linux/macOS:
source venv/bin/activate
# On Windows PowerShell:
.\venv\Scripts\Activate.ps1

# Install project dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

### 2. Run Modular Verification Suites
Each sensory module includes an automated verification test suite that executes locally without requiring physical Raspberry Pi GPIO peripherals:

```bash
# Verify Blind Mode (Ultrasonic Math & Haptic PWM Driver)
python blind_mode/test_blind_mode.py

# Verify Deaf Mode (16kHz PCM Stream, Vosk ASR, and OLED Subtitle Renderer)
python deaf_mode/test_deaf_mode.py
python deaf_mode/test_step3_1.py

# Verify Mute Mode (3D Landmark Extraction, EMA Jitter Filter, & 1D-CNN+GRU Classifier)
python mute_mode/test_landmark_extractor.py
python mute_mode/test_sequence_buffer.py
python mute_mode/test_classifier_pipeline.py

# Verify Mode Manager (Resource Locking & State Transitions)
python shared/mode_manager.py
```

---

## Repository Structure

```
TriSense/
├── blind_mode/                # Spatial Collision & Haptic Feedback Pipeline
│   ├── sensor_loop.py         # 20Hz Ultrasonic sensor & PWM alert loop
│   ├── haptic_driver.py       # PWM intensity & frequency mapping
│   ├── HARDWARE_TODO.md       # Hardware wiring & GPIO deployment checklist
│   └── test_blind_mode.py     # Blind mode automated test suite
├── deaf_mode/                 # Offline Speech-to-Text OLED Subtitle Pipeline
│   ├── audio_stream.py        # 16kHz I2S / WAV PCM block streamer
│   ├── asr_engine.py          # Vosk offline Kaldi speech recognition
│   ├── caption_formatter.py   # Punctuation, capitalization, and line-wrapping
│   ├── oled_display.py        # SSD1306 I2C OLED viewport driver
│   ├── main_loop.py           # End-to-end Deaf mode main event loop
│   ├── HARDWARE_TODO.md       # I2S INMP441 & I2C SSD1306 setup guide
│   └── test_deaf_mode.py      # Deaf mode automated test suite
├── mute_mode/                 # 3D Sign Language Recognition Pipeline
│   ├── landmark_extractor.py  # MediaPipe Hands 21 (X, Y, Z) keypoint extractor
│   ├── sequence_buffer.py     # EMA temporal smoother & 30-frame FIFO buffer
│   ├── classifier.py          # 1D-CNN + GRU edge PyTorch classifier (~62.6k params)
│   ├── train_classifier.py    # Training script structure & smoke-test loader
│   ├── dataset_downloader.py  # WLASL video fetching & landmark dataset builder
│   ├── video_stream.py        # Camera & video file input streamer
│   └── test_*.py              # Modular test suites for extraction, buffer, classifier & downloader
├── shared/                    # Common System Resources
│   └── mode_manager.py        # Thread-safe multi-mode resource orchestrator
├── assets/                    # Animated SVG architecture & banner graphics
├── PROGRESS.md                # Living development roadmap & verification tracker
└── README.md                  # Project engineering documentation
```

---

## Roadmap

- [x] **Phase 1A**: Blind Mode Software Pipeline & Haptic Mapping
- [x] **Phase 1B**: Deaf Mode Offline ASR Engine & OLED Subtitle Formatter
- [x] **Phase 1C**: Mute Mode 3D Landmark Extraction, 100-word WLASL Dataset, & Edge Classifier
- [x] **Phase 1D**: Mode Manager Resource Locking & Orchestration
- [ ] **Phase 2**: Model Quantization (ONNX / TFLite INT8 Export) & Edge Latency Profiling
- [ ] **Phase 3**: Physical Raspberry Pi 4 GPIO Deployment & Field Validation

---

<div align="center">
  <p><b>TriSense</b> — Designed and Engineered for Linux Edge Computing</p>
</div>
