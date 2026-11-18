# TriSense Phase 2: what changed and why

This note lists every change made after the Phase 1 review, the bug or weakness
behind it, and how it was verified. All numbers come from scripts in this
repository and can be reproduced with the commands at the end.

## 1. Mute Mode: why accuracy was 33% and what fixed it

The Phase 1 report blamed "too little data". Reading the pipeline showed four
concrete problems, three of which had nothing to do with data volume.

| # | Problem in v1 | Effect | Fix in v2 |
|---|---------------|--------|-----------|
| 1 | Every hand was normalised to its own wrist and size, and no body landmarks were used | The model only saw finger shape. Where the hand is (chin, forehead, chest) and how it moves were thrown away, although in ASL those cues separate many signs (MOTHER vs FATHER, for example) | MediaPipe Pose is added. Features keep each hand's position and trajectory in a body centred frame (mid shoulders, scaled by shoulder width) **and** the wrist relative handshape (`mute_mode/features.py`) |
| 2 | Only the first 60 frames of a clip were read and the last 30 of those kept, ignoring WLASL's `frame_start`/`frame_end` | For clips cut from longer videos the sign was often not in the window at all, so those samples carried the wrong label | The WLASL frame window is respected, leading and trailing frames without hands are trimmed, and the whole sign is resampled to 32 frames |
| 3 | Downloader stopped at 8 clips per word (`MAX_CLIPS_PER_WORD = 8`), and YouTube and Yale Signbank downloads silently failed | ~7 clips per word | All reachable clips are fetched in parallel; YouTube now downloads video only (no ffmpeg needed) and Signbank uses its new HTTPS host (`mute_mode/wlasl_fetch.py`) |
| 4 | Random 80/20 split of 734 clips, so the same signer appeared in train and validation, and some validation classes had a single clip | The 33.33% figure was noisy and not comparable to published WLASL results | Official WLASL train / val / test split, model chosen on val, test touched once, top 1 and top 5 reported (`mute_mode/train_v2.py`) |

The live pipeline was also rebuilt. v1 classified a fixed 30 frame window and
cleared it after each guess. v2 (`mute_mode/recognizer.py`) starts a sign when a
hand appears and ends it when the hands drop, then resamples the segment exactly
as in training. Thresholds are in seconds, so it behaves the same at 25 fps on a
laptop and about 8 fps on a Pi 4.

Model: `SignClassifierV2` (temporal depthwise separable CNN, BiGRU, attention
pooling). 182,245 parameters, about 0.7 MB in float32.

### Results

All numbers use the official WLASL split (677 train, 171 val, 155 test clips;
2 to 17 clips per word, median 10). Only 1,004 of the 1,843 listed clips for the
100 words could still be downloaded; the rest are dead links.

| Model | Evaluation | Top 1 | Top 5 |
|-------|-----------|-------|-------|
| v1 (Phase 1) | random 80/20 split of 734 clips, same signers on both sides | 33.3% | not reported |
| **v2, device model** (`checkpoints/sign_v2.pth`, trained on train+val) | official test split | **64.5%** | **81.9%** |
| v2, model selected on val (mean of 3 seeds) | official test split | 61.9% ± 2.6 | 79.6% |
| v2 live path (`eval_live.py`, 60 test videos streamed frame by frame) | official test split | 61.7% | 78.3% (top 3) |

With the confidence gate (0.45) the live recogniser speaks on 32 of 60 test
signs and is correct on **90.6%** of the ones it speaks. When unsure it stays
silent instead of voicing a wrong word.

Ablation (3 seeds each, same split):

| Variant | Val top 1 | Test top 1 | Test top 5 |
|---------|-----------|------------|------------|
| Full features (hands in body frame + handshape + upper body) | 69.8% | 61.9% ± 2.6 | 79.6% |
| Handshape only (v1 style features) | 64.3% | 60.2% ± 3.6 | 79.1% |
| Full features, no augmentation (1 seed) | 63.2% | 58.7% | 78.1% |

Reading this honestly: most of the jump from 33% comes from the data pipeline
(correct sign windows, all reachable clips) together with the new model, its
training recipe and augmentation. Body relative hand position helps
consistently on validation (+5.5 points) but only slightly on the test set
(+1.7 points), which is within the noise of a 155 clip test set.

For context, published pose based results on the official WLASL100 benchmark
(about 2,000 clips) are roughly 55% (Pose TGCN) to 63% (SPOTER). Those use a
different 100 word list, so the numbers are not directly comparable, but they
show the v2 result is in the expected range for pose based recognisers.

## 2. Blind Mode

| Problem | Effect | Fix |
|---------|--------|-----|
| ModeManager's Blind adapter called `pulse_motor()` inline | The sensing loop froze for up to 500 ms per motor (1.5 s with three) whenever an alert fired | Non blocking `HapticDriver` with one background thread (`blind_mode/haptic.py`) |
| Closing speed divided by a hard coded 0.1 s | Real loop time was longer (sensor reads, blocking pulses), so speed was overestimated and TTC underestimated, giving false "imminent" alerts | Engine uses measured timestamps (`blind_mode/engine.py`) |
| No filtering of echoes | A single bad echo looked like an object jumping closer | 3 sample median filter, out of range rejection (2 to 400 cm), smoothed speed with a 15 cm/s dead band |
| Alerts only from time to collision | A user standing still next to a wall got **no warning**, because speed was zero | Proximity alerts: 150 ms pulse below 60 cm, 300 ms pulse plus speech below 30 cm |
| Overlapping pulse threads on one motor | A later thread switched the motor off in the middle of an earlier pulse | Per motor busy window, so pulses are distinct and their length encodes urgency |
| Echo timing used `time.time()` | Wall clock, can jump | `time.perf_counter()` |

The standalone `sensor_loop.py` and the ModeManager adapter now share the same
engine, so they can no longer behave differently.

## 3. Deaf Mode

| Problem | Effect | Fix |
|---------|--------|-----|
| ModeManager ran the Deaf app inside `start()` | `switch_mode("DEAF")` did not return until the audio ended. With a live microphone that is never, so the device could not leave Deaf Mode | App runs in a background thread; `stop()` ends it |
| With a microphone, `run()` returned immediately | OLED showed "Deaf Mode Stopped" while still listening | `run()` blocks until stopped |
| Vosk ran inside the audio callback | On a Pi this blocks the audio thread and drops speech | Callback only queues audio; a worker thread runs Vosk |
| `FinalResult()` never called | The last sentence of a recording was lost if Vosk had not yet seen an endpoint | Final result is flushed when the stream ends |
| `ASR_MOCK` defaulted to on and the model path was relative | The real recogniser was skipped unless env vars were set, and the model was only found when started from the repo root | Real Vosk whenever the model exists; absolute default path |
| `test_main_loop.py` imported a function that does not exist | The end to end test could not run | Fixed, with an offline TTS fallback for the sample WAV |

Verified: the end to end test now transcribes a spoken sample with the real Vosk
model ("hello tries and team and obstacle is a head on your left please stop now"
for "hello TriSense team, an obstacle is ahead on your left, please stop now").

## 4. Shared services

* **TTS cooldown** was stamped when speech *finished*, so a 10 Hz loop queued the
  same warning many times during the first utterance. It is now stamped per phrase
  when queued, the queue is bounded, and it is flushed on every mode switch.
* **Windows**: pyttsx3 failed in the worker thread ("CoInitialize has not been
  called"); COM is now initialised in that thread.
* **ModeManager** switches are serialised with a lock (button, keyboard and web UI
  can fire at once).

## 5. Demo console

The Phase 1 web emulator could only show fixed inputs: one distance for every
sensor (an environment variable), one WAV file, and a mock video that was not in
the repository. It has been rebuilt (`emulator_server.py`, `templates/index.html`):

* Blind: live, per sensor obstacle distances (drag or slide) and scripted scenarios,
  fed to the real HC-SR04 driver through the mock GPIO, which now simulates each
  sensor separately and times echoes from the trigger's falling edge
* Deaf: browser microphone streamed as 16 kHz PCM to Vosk through a new push audio source
* Mute: webcam or held out test clips sent to the real recogniser through a push video
  source, with landmark overlay, sign state, top 3 predictions and a running score
* device speech mirrored to the browser, live ResourceGuard ownership, event log

Fixes found while building it: mode switches crashed on Windows consoles that cannot
print the arrow characters in the GPIO setup log; the first sign after entering Mute
Mode was lost while MediaPipe initialised (now warmed up on start); and pose and hand
inference now run in parallel, raising the live recogniser from about 4.4 to 6.4
frames per second on the development laptop.

## 6. Tests

New unit tests: `tests/test_blind_engine.py`, `tests/test_tts_and_haptics.py`,
`tests/test_deaf_pipeline.py`, `tests/test_mute_v2.py`. The pytest suite now has 59 tests (was 38) and all pass, as do `ruff`, `blind_mode/synthetic_test.py`, `deaf_mode/test_main_loop.py` (with the real Vosk model) and `shared/test_mode_manager.py` (with the v2 recogniser).

## Reproduce

```
python mute_mode/wlasl_fetch.py --workers 16      # download WLASL clips for the 100 words
python mute_mode/build_landmarks.py --workers 8   # hands + pose landmarks
python mute_mode/train_v2.py --deploy             # evaluate, then train the device model
python mute_mode/train_v2.py --features shape_only   # ablation: v1 style features
pytest
```
