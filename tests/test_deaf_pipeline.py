"""Deaf Mode adapter must not block switch_mode() and must flush the last utterance."""

import math
import struct
import time
import wave

from shared.mode_manager import DeafModePipeline


def _tone_wav(path, seconds=12.0, rate=16000):
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        frames = b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * 440 * i / rate)))
                          for i in range(int(seconds * rate)))
        wf.writeframes(frames)


def test_start_returns_immediately_and_stop_interrupts(tmp_path):
    wav = tmp_path / "long.wav"
    _tone_wav(wav)
    p = DeafModePipeline()
    t0 = time.monotonic()
    p.start(wav_path=str(wav), use_mock=True, real_time=True)  # 12 s of audio played in real time
    # start() may take a few seconds to load the Vosk model, but must not wait for the 12 s of audio
    assert time.monotonic() - t0 < 7.0, "start() blocked until the audio source ended"
    assert p.is_running
    time.sleep(0.5)
    t1 = time.monotonic()
    p.stop()
    assert time.monotonic() - t1 < 3.5
    assert not p.is_running


def test_mock_recogniser_final_result_flushed():
    from deaf_mode.main_loop import DeafModeApp

    class Streamer:
        use_mock = True
        callback = None

        def start(self, real_time=False):
            for _ in range(3):  # 3 blocks: the mock recogniser only finalises every 4th block
                self.callback(b"\x10\x27" * 4000, 4000, 0, None)

        def stop(self):
            pass

    class ASR:
        def accept_waveform(self, d):
            return False

        def partial_result(self):
            return "hello"

        def get_final_result(self):
            return "hello world"

    class Renderer:
        def __init__(self):
            self.history = []

        def update_caption(self, text, is_final=False):
            if is_final:
                self.history.append(text)

        def show_status(self, *a, **k):
            pass

        def get_history(self):
            return list(self.history)

    app = DeafModeApp(Streamer(), ASR(), Renderer())
    summary = app.run()
    assert summary["history"] == ["hello world"] and summary["utterances"] == 1
