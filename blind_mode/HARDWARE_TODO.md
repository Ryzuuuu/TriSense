# TriSense Blind Mode — Hardware Validation Checklist

This checklist contains all the tests that could not be completed during software-logic validation. Run these in order once the Raspberry Pi and physical components arrive.

## 🔌 1. GPIO & Basic Wiring Check
- [ ] **Run `gpio_setup.py`**: Ensure no `RPi.GPIO` warnings or errors are thrown during initialization.
- [ ] **Floating Pin Check**: Run `sensor_loop.py` with all ECHO wires intentionally *unplugged*.
  - *Pass:* Terminal shows `---` for distances.
  - *Fail:* Terminal shows chaotic jumping numbers. *Fix:* Add `pull_up_down=GPIO.PUD_DOWN` to the ECHO pin setup in `gpio_setup.py`.

## 📏 2. Ultrasonic Sensor Calibration (`distance.py`)
- [ ] **Run `distance.py` (center only)**: Place a flat object at exactly 50 cm, 100 cm, and 150 cm.
  - *Pass:* Distance reads accurately within ±2 cm.
- [ ] **Close-Range OS Context Switch Test**: Quickly move your hand from 20 cm to 2 cm.
  - *Pass:* Distance reads accurately or returns `None` (timeout).
  - *Fail:* Distance jumps to a massive/negative number (OS missed the pulse). *Fix:* Treat <10 cm as an immediate collision zone, or upgrade to `pigpio` if critical.
- [ ] **Sensor Cross-Talk Check**: Run `distance.py` (all three sensors) in an empty room or corner.
  - *Pass:* All sensors report >200 cm cleanly.
  - *Fail:* Sensors report ghost objects close by. *Fix:* Add a `time.sleep(0.02)` delay between reading each sensor in `read_all_sensors()`.

## 📳 3. Haptic Motor Drivers (`haptic.py`)
- [ ] **Run `haptic.py`**:
  - *Pass:* All three motors buzz sequentially (Left → Center → Right) with strong, distinct vibrations.
  - *Fail:* Motor is weak or silent. *Fix:* Check NPN transistor base resistor and ensure the motor is drawing from the 5V rail, not the 3.3V GPIO pin.
- [ ] **Thread Overlap Test**: Run `sensor_loop.py` and hold an object very close (< 0.5s TTC) to one sensor for 3 seconds.
  - *Pass:* The motor buzzes solidly and intensely.
  - *Fail:* The motor stutters erratically or sounds weak (threads are overlapping and killing each other's pulses). *Fix:* Refactor `pulse_motor()` to be stateful or use a queue.

## 🔊 4. Audio Alert (`audio_alert.py`)
- [ ] **Run `audio_alert.py`**:
  - *Pass:* Audio plays clearly out of the Pi's audio jack/speaker, and properly obeys the 2.0s cooldown.
- [ ] **ALSA Driver Lock-Up Check**: Run `sensor_loop.py` and repeatedly trigger the center audio alert for a few minutes.
  - *Pass:* Audio continues to work, and Ctrl+C exits cleanly.
  - *Fail:* Audio stops working after one alert, or Ctrl+C hangs forever. *Fix:* Ditch `pyttsx3` and use `os.system("espeak 'Obstacle ahead'")` directly.

## 🏃 5. Full System Walking Test (`test_logger.py`)
- [ ] **Run the obstacle course**: Put on the belt and walk a controlled course blindfolded while running `test_logger.py`.
- [ ] **Analyse Results**: Open the resulting CSV and calculate:
  - False-Positive Rate (Alert triggered with no obstacle).
  - False-Negative Rate (Obstacle hit with no alert).
  - *Goal:* < 10% false-alert rate at 1.5 m.
