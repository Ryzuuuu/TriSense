# deaf_mode/caption_renderer.py
# -----------------------------------------------------------------------------
# 3-Line Rolling Caption UI Renderer for TriSense Deaf Mode (Step 2.2).
# Orchestrates raw speech transcription strings (ASREngine), caption formatting
# (CaptionFormatter), and OLED rendering (OLEDDisplay) into a cohesive live
# visual subtitle experience.
# -----------------------------------------------------------------------------

import os
import sys

# Ensure parent directory is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from deaf_mode.caption_formatter import CaptionFormatter
from deaf_mode.oled_display import OLEDDisplay


class CaptionRenderer:
    """
    Manages live visual subtitle captioning on the TriSense OLED display.
    """
    def __init__(self, display: OLEDDisplay, formatter: CaptionFormatter = None,
                 default_header: str = "TriSense ASR [REC]"):
        self.display = display
        self.formatter = formatter if formatter is not None else CaptionFormatter(max_chars_per_line=20, max_lines=3)
        self.default_header = default_header
        self.history = []
        self.current_caption = ""

    def update_caption(self, text: str, is_final: bool = False, header: str = None) -> list:
        """
        Formats and renders a speech recognition string (partial or final) onto
        the OLED display.
        """
        header_to_use = header if header is not None else self.default_header
        lines = self.formatter.get_display_lines(text, is_final=is_final, show_ellipsis=True)
        self.display.display_text_lines(lines, header=header_to_use)
        self.current_caption = text
        
        if is_final and text.strip():
            self.history.append(text.strip())
            
        return lines

    def show_status(self, message: str, header: str = "TriSense [STATUS]") -> list:
        """
        Displays a system status notification or alert banner on the OLED.
        """
        lines = self.formatter.get_display_lines(message, is_final=True, show_ellipsis=False)
        self.display.display_text_lines(lines, header=header)
        return lines

    def clear(self):
        """
        Clears OLED display buffer and resets current caption text.
        """
        self.display.clear()
        self.current_caption = ""

    def get_history(self) -> list:
        """
        Returns the list of completed sentence utterances logged during this session.
        """
        return list(self.history)
