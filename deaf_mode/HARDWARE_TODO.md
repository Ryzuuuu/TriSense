# TriSense Deaf Mode — Hardware Validation Checklist

This checklist covers physical testing for the Deaf Mode captioning pipeline once the Raspberry Pi 4, INMP441 I2S microphone, and SSD1306 OLED display are assembled.

## 🔌 1. I2S Microphone Wiring & ALSA Config (`audio_stream.py`)
- [ ] **Enable I2S Bus**: Verify `dtparam=i2s=on` is set in `/boot/config.txt` and check GPIO wiring (SD, SCK, WS; L/R pin tied to GND for mono left channel).
- [ ] **ALSA Capture Test**: Run `arecord -l` to confirm the INMP441 microphone appears as an input device.
- [ ] **Live Sample Test**: Run `test_main_loop.py` on the Pi with `use_mock=False` on `AudioStreamer`.
  - *Pass:* `sounddevice.RawInputStream` captures 16 kHz 16-bit mono PCM blocks cleanly without ALSA buffer underruns.
  - *Fail:* Audio drops or device busy errors. *Fix:* Verify ALSA card index in `~/.asoundrc` or increase `block_size` in `config.py`.

## 🖥️ 2. I2C OLED Display Wiring & Address Check (`oled_display.py`)
- [ ] **I2C Bus Detection**: Run `i2cdetect -y 1`.
  - *Pass:* Display responds at address `0x3C` (or `0x3D`).
  - *Fail:* Nothing detected. *Fix:* Check 3.3V power, GND, and SDA/SCL pull-ups; ensure I2C is enabled in `raspi-config`.
- [ ] **Hardware Render Test**: Run `test_oled_display.py` with hardware mode enabled.
  - *Pass:* Status banner and 3-line wrapped subtitles render crisply on the physical 128x64 display without flickering.
  - *Fail:* Blank screen or corrupted pixels. *Fix:* Verify bus speed (`dtparam=i2c_arm_baudrate=400000`) and display resolution parameters.

## 🎙️ 3. Acoustic & Noise Field Testing (`asr_engine.py`)
- [ ] **Quiet Room Test**: Speak 10 target phrases at normal conversational volume 1 meter from the mic.
  - *Pass:* Vosk (`vosk-model-small-en-us`) transcribes spoken words with > 90% accuracy.
  - *Fail:* Missing words or distorted phonetics. *Fix:* Adjust input capture gain using `alsamixer`.
- [ ] **Ambient Noise Test**: Test speech recognition with moderate background chatter or room fan noise.
  - *Pass:* Speech is recognized cleanly without triggering false partial transcriptions from steady noise.
  - *Fail:* Constant garbage transcriptions. *Fix:* Adjust RMS energy threshold in the audio preprocessing stream.

## ⚡ 4. End-to-End Latency & UI Verification (`main_loop.py`)
- [ ] **Live Walkthrough**: Run `main_loop.py` (`DeafModeApp`) and speak continuous sentences while walking.
  - *Pass:* Partial subtitles appear on the OLED within ~300 ms of speaking, wrap cleanly at 20 characters, show the leading `...` ellipsis when scrolling, and log completed sentences to session history.
  - *Fail:* Visual lag accumulates over time. *Fix:* Ensure I2C screen refresh rate is throttled appropriately so ALSA audio buffers never block.
