# deaf_mode/main_loop.py
# -----------------------------------------------------------------------------
# Deaf Mode Main Processing Loop for TriSense (Step 3.1).
# Wires together the REAL AudioStreamer -> real ASREngine -> real CaptionFormatter
# -> real OLEDDisplay / CaptionRenderer into an end-to-end real-time subtitle pipeline.
# -----------------------------------------------------------------------------

import time
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

    def _audio_callback(self, indata, frames, time_info, status):
        """
        Invoked by AudioStreamer for every captured block of audio PCM frames.
        """
        if indata is None or len(indata) == 0:
            return

        is_endpoint = self.asr_engine.accept_waveform(indata)
        
        if is_endpoint:
            text = self.asr_engine.result()
            if text and text.strip():
                self.renderer.update_caption(text, is_final=True)
                self.total_utterances += 1
                if self.on_caption_update:
                    self.on_caption_update(text, True)
        else:
            partial = self.asr_engine.partial_result()
            if partial and partial.strip():
                self.renderer.update_caption(partial, is_final=False)
                if self.on_caption_update:
                    self.on_caption_update(partial, False)

        self.total_blocks_processed += 1

    def run(self, real_time=False) -> dict:
        """
        Starts the Deaf Mode audio streaming and recognition loop.
        Returns a summary dictionary with execution statistics upon stream completion.
        """
        self.is_running = True
        self.renderer.show_status("Deaf Mode Running...", header="TriSense ASR [REC]")

        self.audio_streamer.start(real_time=real_time)

        self.is_running = False
        self.renderer.show_status("Deaf Mode Stopped.", header="TriSense [IDLE]")
        
        return {
            "blocks_processed": self.total_blocks_processed,
            "utterances": self.total_utterances,
            "history": self.renderer.get_history()
        }

    def close(self):
        """
        Cleans up underlying audio and display resources.
        """
        self.is_running = False
        if hasattr(self.audio_streamer, "stop"):
            self.audio_streamer.stop()
        if hasattr(self.renderer, "clear"):
            self.renderer.clear()
