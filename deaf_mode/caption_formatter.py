# deaf_mode/caption_formatter.py
# -----------------------------------------------------------------------------
# Transcription Punctuation & Sentence-Break Processor for TriSense Deaf Mode.
# Transforms raw lowercase Vosk ASR streams into readable, properly wrapped
# subtitle captions suitable for OLED display rendering.
# -----------------------------------------------------------------------------


class CaptionFormatter:
    """
    Formats raw speech recognition text for display on a small screen (OLED).
    
    Parameters:
      max_chars_per_line: int (default 20, standard for 128x64 OLED fonts)
      max_lines         : int (default 3, max visible text lines on OLED)
    """
    def __init__(self, max_chars_per_line=20, max_lines=3):
        self.max_chars_per_line = max_chars_per_line
        self.max_lines = max_lines

    def format_caption(self, text: str, is_final: bool = False) -> list:
        """
        Processes text into a list of display lines not exceeding max_chars_per_line.
        Always retains up to the most recent max_lines for scrolling live captions.
        """
        if not text or not text.strip():
            return []

        cleaned = " ".join(text.strip().split())
        
        # Capitalize first letter
        if len(cleaned) > 0:
            cleaned = cleaned[0].upper() + cleaned[1:]

        # Append trailing period for completed sentence utterances
        if is_final and not cleaned.endswith((".", "!", "?")):
            cleaned += "."

        # Smart word wrapping without breaking words
        words = cleaned.split(" ")
        lines = []
        current_line = ""

        for word in words:
            if not current_line:
                current_line = word
            elif len(current_line) + 1 + len(word) <= self.max_chars_per_line:
                current_line += " " + word
            else:
                lines.append(current_line)
                current_line = word

        if current_line:
            lines.append(current_line)

        # If more lines than fit on screen, keep the latest max_lines (scrolling subtitle)
        if len(lines) > self.max_lines:
            lines = lines[-self.max_lines:]

        return lines

    def get_display_string(self, text: str, is_final: bool = False) -> str:
        """
        Returns a newline-separated string ready for console or OLED rendering.
        """
        lines = self.format_caption(text, is_final=is_final)
        return "\n".join(lines)
