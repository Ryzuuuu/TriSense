# TriSense — Complete Build Plan
### DSN4091 Capstone Project | Aug 2026 – Mar 2027

This is the step-by-step execution plan for the whole project — what to buy, what to install, what to build in what order, and how to test it, from Week 1 to the final Review-4 demo.

**Golden rule for the whole project**: Blind Mode and Deaf Mode are **hard deliverables** — they must work, no excuses. Mute Mode is a **stretch goal** — build it only after the first two are solid. Every phase below is ordered to protect this rule.

---

## 0. Before You Touch Any Code — Setup Week (Week 1, Aug)

### 0.1 Order hardware immediately
Don't wait — shipping + soldering + debugging always takes longer than expected. Order the full BOM from the earlier list (Robu.in / Robocraze / Amazon.in) in the **first three days** of the project. Order **2 of everything cheap** (sensors, motors) — they're the parts most likely to get damaged during wiring practice.

### 0.2 Set up your dev environment (do this while hardware ships)
1. Flash **Raspberry Pi OS (64-bit, Bookworm)** onto the microSD card using **Raspberry Pi Imager** (from raspberrypi.com/software). Enable SSH + Wi-Fi during imaging so you can work headless.
2. Boot the Pi, connect via SSH: `ssh pi@<pi-ip-address>`
3. Update the system:
   ```bash
   sudo apt update && sudo apt full-upgrade -y
   sudo raspi-config   # enable Camera, I2C, SPI, Serial (from Interface Options)
   ```
4. Install core packages:
   ```bash
   sudo apt install -y python3-pip python3-venv git i2c-tools libatlas-base-dev
   python3 -m venv ~/trisense-env
   source ~/trisense-env/bin/activate
   pip install opencv-python-headless mediapipe numpy RPi.GPIO smbus2 sounddevice vosk pyttsx3
   ```
5. Create a shared **GitHub repo** (`trisense`) — every member pushes to their own branch, merges into `main` weekly. Set up folders now:
   ```
   trisense/
     blind_mode/
     deaf_mode/
     mute_mode/
     shared/         <- mode manager, GPIO helpers, config
     models/         <- trained/quantized model files
     docs/
   ```
6. Do a **"hello world" GPIO test** — blink an LED or buzz a motor from Python. If this works, your Pi + wiring foundation is solid.

### 0.3 Assign ownership (from the report's contribution table)
| Person | Module | Also responsible for |
|---|---|---|
| Member 1 | Blind Mode | Ultrasonic + depth sensing, collision-time math |
| Member 2 | Deaf Mode | ASR integration, caption display |
| Member 3 | Mute Mode | Landmark extraction, sign classifier |
| Member 4 | Edge optimization | Quantization, mode manager, power management |
| Member 5 | Integration | Enclosure, wiring harness, testing framework |

---

## Phase 1 — Blind Mode + Deaf Mode (Weeks 2–9, Aug–Oct) — target: Review 2

### 1A. Blind Mode — Build Steps

**Step 1: Wire the ultrasonic sensors (Week 2)**
- HC-SR04 pins: `VCC → 5V`, `GND → GND`, `TRIG → GPIO pin`, `ECHO → GPIO pin (via voltage divider — ECHO outputs 5V, Pi GPIO is 3.3V, use two resistors ~1kΩ/2kΩ to step down or a logic-level shifter)`
- Mount 3 sensors across the belt: left (~30° left), center (straight), right (~30° right)
- Suggested GPIO mapping:

| Sensor | TRIG | ECHO |
|---|---|---|
| Left | GPIO 5 | GPIO 6 |
| Center | GPIO 13 | GPIO 19 |
| Right | GPIO 26 | GPIO 21 |

**Step 2: Basic distance reading (Week 2–3)**
```python
import RPi.GPIO as GPIO
import time

def get_distance(trig, echo):
    GPIO.output(trig, True)
    time.sleep(0.00001)
    GPIO.output(trig, False)
    start = time.time()
    while GPIO.input(echo) == 0:
        start = time.time()
    while GPIO.input(echo) == 1:
        stop = time.time()
    elapsed = stop - start
    distance = (elapsed * 34300) / 2   # speed of sound in cm/s
    return distance
```
Test: print live distance readings from all 3 sensors. Wave your hand in front of each — confirm accurate readings within ±2cm at 10-100cm range.

**Step 3: Collision-time estimation (Week 3–4)**
- Take two consecutive distance readings ~100ms apart per sensor → compute closing speed = (d1 - d2) / time_delta
- Time-to-collision = current_distance / closing_speed (only meaningful if closing speed > 0, i.e., object getting closer)
- If time-to-collision < 1.5 seconds (tunable threshold) → trigger alert for that direction

**Step 4: Haptic + audio output (Week 4–5)**
- Wire 3 mini vibration motors via NPN transistor drivers (motors need more current than GPIO can supply directly) to 3 more GPIO pins
- On alert: pulse the motor on the corresponding side (left obstacle → left motor buzzes), pulse faster as time-to-collision shrinks
- Add a simple `pyttsx3` or pre-recorded audio clip ("Obstacle ahead") for center-critical alerts

**Step 5: Add camera-based depth cues (Week 5–6, enhancement)**
- Use `MiDaS-small` (lightweight monocular depth model, TensorFlow Lite version) or simpler: use camera only to classify obstacle type (person/wall/vehicle) via a small pretrained MobileNet, fusing with ultrasonic distance for the final decision
- If time is tight, **skip this and ship ultrasonic-only for Review 2** — it's a fully working, demoable system on its own

**Step 6: Test & validate (Week 7–8)**
- Walking test: blindfolded team member (in a safe, controlled space) navigates a simple obstacle course using only haptic feedback
- Log false-positive rate (alerts with no real obstacle) and false-negative rate (missed obstacles)
- Target for Review 2: reliable detection within 1.5m, <10% false-alert rate

### 1B. Deaf Mode — Build Steps

**Step 1: Wire the microphone (Week 2)**
- INMP441 uses I2S protocol: `SD → GPIO20`, `SCK → GPIO18`, `WS → GPIO19`, `L/R → GND`, `VDD → 3.3V`, `GND → GND`
- Enable I2S in `/boot/config.txt`: add `dtoverlay=googlevoicehat-soundcard` (or the specific INMP441 overlay per your seller's guide)
- Test recording: `arecord -D plughw:1,0 -c1 -r 16000 -f S16_LE -t wav -V mono test.wav`, play it back to confirm clean audio capture

**Step 2: Install offline ASR engine (Week 3)**
- Use **Vosk** (lightweight, fully offline, good Pi performance) — download the small English model (~50MB) from alphacephei.com/vosk/models
```python
from vosk import Model, KaldiRecognizer
import sounddevice as sd
import queue, json

model = Model("model/vosk-model-small-en-us")
q = queue.Queue()

def callback(indata, frames, time, status):
    q.put(bytes(indata))

rec = KaldiRecognizer(model, 16000)
with sd.RawInputStream(samplerate=16000, blocksize=8000, dtype='int16', channels=1, callback=callback):
    while True:
        data = q.get()
        if rec.AcceptWaveform(data):
            result = json.loads(rec.Result())
            print(result['text'])
```
**Step 3: Wire the OLED display (Week 4)**
- SSD1306 0.96" I2C: `VCC → 3.3V`, `GND → GND`, `SCL → GPIO3 (SCL)`, `SDA → GPIO2 (SDA)`
- Test with `i2cdetect -y 1` — confirm the display shows up at address `0x3C`
- Use `luma.oled` Python library to render scrolling text captions

**Step 4: Connect ASR output to display (Week 5)**
- Pipe recognized text into a rolling caption buffer (last ~3 lines) displayed on the OLED, updating in near real-time
- Add basic punctuation/sentence-break heuristics so captions don't run together illegibly

**Step 5: Test & validate (Week 6–7)**
- Test in a quiet room first, then progressively noisier environments
- Measure: word error rate (compare transcribed vs. actual spoken script) and caption latency (time from speech to text appearing)
- Target for Review 2: usable captions in normal conversational settings, latency under ~1.5 seconds

### Milestone: Review 2 (Oct 1–10)
By this point you should have: Blind Mode giving reliable haptic obstacle alerts, and Deaf Mode showing live captions — both running on your laptop or an early Pi setup. This alone satisfies "quality of initial implementation" fully, independent of Mute Mode's progress.

---

## Phase 2 — Edge Optimization + Integration + Mute Mode Start (Weeks 10–17, Oct–Dec) — target: Review 3

### 2A. Move everything onto the actual Raspberry Pi hardware (Week 10–11)
- If Phase 1 was developed on laptops, now port all code to run natively on the Pi 4
- Profile each pipeline's CPU/RAM usage (`htop`, `time` command) — identify bottlenecks

### 2B. Quantize your models (Week 11–13)
- Convert any TensorFlow/PyTorch models to **TensorFlow Lite** with post-training int8 quantization:
```python
import tensorflow as tf
converter = tf.lite.TFLiteConverter.from_saved_model("model_dir")
converter.optimizations = [tf.lite.Optimize.DEFAULT]
tflite_model = converter.convert()
open("model_quantized.tflite", "wb").write(tflite_model)
```
- Re-test accuracy after quantization — some drop is expected (~1-3%), but should stay well within usable range
- Re-measure latency — this is the step that determines whether Mute Mode is even viable on the Pi

### 2C. Build the Mode Manager (Week 12–13)
- A single Python service that:
  - Reads the mode-select button (or app command via a simple local Flask/MQTT endpoint)
  - Starts/stops the correct pipeline (Blind / Deaf / Mute) — only one active at a time to conserve compute
  - Manages shared resources: camera, speaker, GPIO
```python
import RPi.GPIO as GPIO

MODES = ["blind", "deaf", "mute"]
current_mode = 0
BUTTON_PIN = 17

def mode_switch_callback(channel):
    global current_mode
    current_mode = (current_mode + 1) % len(MODES)
    print(f"Switched to: {MODES[current_mode]}")
    # stop current pipeline process, start new one

GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.add_event_detect(BUTTON_PIN, GPIO.FALLING, callback=mode_switch_callback, bouncetime=300)
```

### 2D. Start Mute Mode (Week 12 onward, in parallel with 2A-2C)
**Step 1: Data pipeline (Week 12–13)**
- Use **MediaPipe Holistic** to extract hand + arm landmarks from webcam frames (21 keypoints per hand, normalized x/y/z coordinates) — this is far lighter than classifying raw pixels
```python
import mediapipe as mp
mp_holistic = mp.solutions.holistic
holistic = mp_holistic.Holistic(min_detection_confidence=0.5)

results = holistic.process(frame_rgb)
left_hand = results.left_hand_landmarks
right_hand = results.right_hand_landmarks
```
**Step 2: Pick a small starting vocabulary (Week 13)**
- Do NOT attempt full sign language. Start with 10-15 common words/phrases (e.g., "hello," "thank you," "help," "yes," "no," "water," "food," "stop") — expand later only if time allows
- Use **WLASL** (word-level ASL dataset) or record your own labeled samples (30-50 samples per sign, multiple team members signing for variety)

**Step 3: Train the classifier (Week 14–15)**
- Landmark sequence → small CNN-LSTM or even simpler: a 1D-CNN over a fixed-length window (e.g., 30 frames) of landmark coordinates
- Keep the model small (a few hundred thousand parameters, not millions) — this is the difference between running on a Pi and not
- Train on Google Colab (free GPU) — save the final model, then quantize and transfer to the Pi

**Step 4: Wire the speech output (Week 15)**
- MAX98357A I2S amp: `LRC → GPIO19`, `BCLK → GPIO18`, `DIN → GPIO21`, `GND → GND`, `VIN → 5V`
- On sign classification, use `pyttsx3` (offline TTS) to speak the recognized word/phrase through the speaker

**Step 5: Test Mute Mode in isolation (Week 16–17)**
- Test recognition accuracy on your fixed vocabulary — target >80% on your own test signers before Review 3
- If accuracy is poor or latency is too high by Week 16, **do not panic** — this was flagged as the stretch goal from day one. Present it honestly as "in progress, X% accuracy on Y-word vocabulary" at Review 3 rather than forcing a rushed, broken demo.

### 2E. Physical integration (Week 14–17, parallel)
- Design/print or assemble a belt-mount enclosure housing the Pi, battery pack, camera, and sensor array
- Route all wiring neatly; use a perfboard or small PCB to avoid a breadboard rat's nest for the final unit
- Wire the 18650 battery pack + TP4056 charging module + boost converter to power the Pi cleanly (confirm voltage stability under load — brownouts are a common Pi failure mode)

### Milestone: Review 3 (Dec 7–15)
Target: Blind Mode + Deaf Mode running smoothly **on the actual edge hardware** (not laptop), with real latency/accuracy numbers from testing. Mute Mode shown at whatever stage it has reached — full transparency about what works and what's still in progress.

---

## Phase 3 — Full Integration + Polish (Weeks 18–25, Jan–Feb) — target: Review 4

### 3A. Bring all three modes onto one physical device (Week 18–20)
- Confirm mode-switching works reliably and quickly (<2 sec transition)
- Stress-test: run each mode for 30+ minutes continuously, watch for memory leaks, overheating, or crashes
- Add a heatsink/small fan to the Pi if thermal throttling appears during sustained inference

### 3B. Expand Mute Mode vocabulary if ahead of schedule (Week 18–21)
- Only attempt this if Blind+Deaf+basic Mute are already rock solid — don't risk the guaranteed deliverables for a bigger vocabulary

### 3C. Full system testing (Week 21–23)
- Write a test checklist covering: each mode's core function, mode switching, battery life under real use, and edge-case handling (e.g., very close obstacles, background noise, poor lighting for camera-based modes)
- Get 3-5 people outside the team to try the device and give feedback — genuine usability signal for your report's "results and discussion" section

### 3D. Finalize documentation (Week 23–25)
- Update the Phase-1 report into the full Phase-2 report with actual results, screenshots, and validated metrics replacing the "proposed evaluation plan" placeholders
- Prepare the Review-4 demo script: decide exactly what you'll show, in what order, and who explains which module

### Milestone: Review 4 (Feb 22–26)
Target: All three modes working live, on the physical device, switching in front of the panel — the full "wow" demo.

---

## Testing Checklist (use every phase)

| Test | Blind Mode | Deaf Mode | Mute Mode |
|---|---|---|---|
| Core function works standalone | ☐ | ☐ | ☐ |
| Works on actual Pi hardware (not laptop) | ☐ | ☐ | ☐ |
| Latency measured and acceptable | ☐ | ☐ | ☐ |
| Accuracy/error-rate measured | ☐ | ☐ | ☐ |
| Works after 30+ min continuous run | ☐ | ☐ | ☐ |
| Tested by someone outside the team | ☐ | ☐ | ☐ |
| Battery life under real load measured | ☐ | ☐ | ☐ |

## Risk Watch-list (check monthly)

1. **Mute Mode accuracy stuck low by Week 15** → cut vocabulary further, don't add features; consider presenting it as "future work" rather than forcing a bad demo.
2. **Pi overheating/throttling during multi-mode operation** → add heatsink/fan; profile which pipeline is the CPU hog.
3. **Battery not lasting a full demo session** → recheck boost converter output under load; consider a slightly larger battery pack (still cheap).
4. **Team member falls behind on their module** → the shared-backbone architecture means Member 4/5 (edge optimization/integration) can absorb some slack since their work touches every module — reassign early, don't wait until the week before a review.
