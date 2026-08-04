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
        Processes text into a full list of wrapped lines not exceeding max_chars_per_line.
        Returns ALL wrapped lines without truncating, ensuring no words are silently lost.
        The display layer can use this full list to scroll over time.
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

        return lines

    def get_display_lines(self, text: str, is_final: bool = False, show_ellipsis: bool = True) -> list:
        """
        Returns up to max_lines formatted lines for immediate OLED rendering.
        If the full caption exceeds max_lines, retains the latest max_lines and
        adds a leading '...' to the top visible line to indicate preceding cut content.
        """
        lines = self.format_caption(text, is_final=is_final)
        if len(lines) <= self.max_lines:
            return lines

        visible = lines[-self.max_lines:].copy()
        if show_ellipsis:
            top_line = "..." + visible[0].lstrip()
            if len(top_line) > self.max_chars_per_line:
                top_line = top_line[:self.max_chars_per_line]
            visible[0] = top_line
        return visible

    def get_display_string(self, text: str, is_final: bool = False, show_ellipsis: bool = True) -> str:
        """
        Returns a newline-separated string ready for console or OLED rendering.
        """
        lines = self.get_display_lines(text, is_final=is_final, show_ellipsis=show_ellipsis)
        return "\n".join(lines)
