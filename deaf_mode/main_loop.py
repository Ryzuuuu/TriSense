# deaf_mode/main_loop.py
# -----------------------------------------------------------------------------
# Deaf Mode Main Processing Loop for TriSense (Step 3.1).
# Wires together the REAL AudioStreamer -> real ASREngine -> real CaptionFormatter
# -> real OLEDDisplay / CaptionRenderer into an end-to-end real-time subtitle pipeline.
#
# Fixes over v1:
#   * audio blocks are handed to a worker thread through a queue. Running Vosk
#     inside the sounddevice callback blocks the audio thread and causes input
#     overflows (dropped speech) on a Raspberry Pi.
#   * with a live microphone run() now blocks until stop() is called. In v1 it
#     returned immediately and painted "Deaf Mode Stopped" while still listening.
#   * the last utterance is flushed with FinalResult() when the stream ends, so
#     the final sentence of a recording is no longer silently lost.
#   * hardware buffers are converted to bytes before reaching Vosk.
# -----------------------------------------------------------------------------

import queue
import threading

from deaf_mode.audio_stream import AudioStreamer
from deaf_mode.asr_engine import ASREngine
from deaf_mode.caption_renderer import CaptionRenderer


class DeafModeApp:
    """
    Orchestrates live audio capture, offline speech recognition, caption
    formatting, and OLED subtitle rendering for TriSense Deaf Mode.
    """
    def __init__(self, audio_streamer: AudioStreamer, asr_engine: ASREngine,
                 renderer: CaptionRenderer, on_caption_update=None):
        self.audio_streamer = audio_streamer
        self.asr_engine = asr_engine
        self.renderer = renderer
        self.on_caption_update = on_caption_update

        # Attach our pipeline callback to the audio streamer
        self.audio_streamer.callback = self._audio_callback
        self.is_running = False
        self.total_blocks_processed = 0
        self.total_utterances = 0
        self._q: "queue.Queue" = queue.Queue(maxsize=64)
        self._stop = threading.Event()
        self._threaded = False

    # -- audio side ---------------------------------------------------------
    def _audio_callback(self, indata, frames, time_info, status):
        """Invoked by AudioStreamer for every captured block of PCM frames."""
        if indata is None or len(indata) == 0:
            return
        data = bytes(indata)
        if self._threaded:
            try:
                self._q.put_nowait(data)
            except queue.Full:  # recogniser fell behind: drop the oldest block, keep latency bounded
                try:
                    self._q.get_nowait()
                except queue.Empty:
                    pass
                self._q.put_nowait(data)
        else:
            self._process_block(data)

    # -- recognition side ---------------------------------------------------
    def _emit(self, text, is_final):
        self.renderer.update_caption(text, is_final=is_final)
        if self.on_caption_update:
            self.on_caption_update(text, is_final)

    def _process_block(self, data: bytes):
        if self.asr_engine.accept_waveform(data):
            text = self.asr_engine.result()
            if text and text.strip():
                self.total_utterances += 1
                self._emit(text, True)
        else:
            partial = self.asr_engine.partial_result()
            if partial and partial.strip():
                self._emit(partial, False)
        self.total_blocks_processed += 1

    def _flush_final(self):
        text = self.asr_engine.get_final_result()
        if text and text.strip():
            self.total_utterances += 1
            self._emit(text, True)

    def _worker(self):
        while not self._stop.is_set() or not self._q.empty():
            try:
                data = self._q.get(timeout=0.1)
            except queue.Empty:
                continue
            self._process_block(data)

    def run(self, real_time=False) -> dict:
        """
        Starts Deaf Mode. For a WAV / mock source this returns when the source
        ends. For a live microphone it blocks until stop()/close() is called.
        Returns a summary dictionary with execution statistics.
        """
        self.is_running = True
        self._stop.clear()
        self.renderer.show_status("Deaf Mode Running...", header="TriSense ASR [REC]")

        live = not self.audio_streamer.use_mock
        if live:
            self._threaded = True
            worker = threading.Thread(target=self._worker, daemon=True, name="deaf-asr-worker")
            worker.start()
            self.audio_streamer.start(real_time=real_time)
            if not self.audio_streamer.use_mock:   # still live (no fallback to mock happened)
                self._stop.wait()
            self._stop.set()
            worker.join(timeout=2.0)
            self._threaded = False
        else:
            self.audio_streamer.start(real_time=real_time)  # blocking until the source ends

        self._flush_final()
        self.is_running = False
        self.renderer.show_status("Deaf Mode Stopped.", header="TriSense [IDLE]")

        return {
            "blocks_processed": self.total_blocks_processed,
            "utterances": self.total_utterances,
            "history": self.renderer.get_history()
        }

    def stop(self):
        self._stop.set()
        if hasattr(self.audio_streamer, "stop"):
            self.audio_streamer.stop()

    def close(self):
        """Cleans up underlying audio and display resources."""
        self.stop()
        self.is_running = False
        if hasattr(self.renderer, "clear"):
            self.renderer.clear()
