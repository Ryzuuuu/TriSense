# deaf_mode/oled_display.py
# -----------------------------------------------------------------------------
# OLED Display Abstraction Layer for TriSense Deaf Mode (Step 2.1).
# Provides a unified interface for rendering subtitle captions and headers on
# a physical 128x64 I2C OLED (via luma.oled / PIL) or an ASCII MockOLEDDisplay
# for headless testing and desktop verification.
# -----------------------------------------------------------------------------

import os
import sys

try:
    from PIL import Image, ImageDraw, ImageFont
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False

try:
    from luma.core.interface.serial import i2c
    from luma.oled.device import ssd1306
    _HAS_LUMA = True
except (ImportError, OSError):
    _HAS_LUMA = False


class MockOLEDDisplay:
    """
    Headless ASCII simulated OLED Display for desktop verification and testing.
    Simulates a 128x64 display viewport (20 characters across, 4 text rows: 1 header + 3 lines).
    """
    def __init__(self, width=128, height=64):
        self.width = width
        self.height = height
        self.current_header = ""
        self.current_lines = []
        self.frame_count = 0
        self.is_cleared = True

    def clear(self):
        self.current_header = ""
        self.current_lines = []
        self.is_cleared = True

    def display_text_lines(self, lines: list, header: str = None):
        self.current_header = header if header is not None else ""
        self.current_lines = list(lines)
        self.is_cleared = False
        self.frame_count += 1

    def render_ascii(self) -> str:
        """
        Returns an ASCII art box representing the physical OLED display screen.
        """
        box_width = 22  # 20 chars + 2 borders
        top_border = "+" + "-" * (box_width - 2) + "+"
        bottom_border = top_border
        
        row_strings = [top_border]
        
        # Header row
        header_text = (self.current_header[:20]).ljust(20)
        row_strings.append(f"|{header_text}|")
        row_strings.append("|" + "-" * 20 + "|")
        
        # Up to 3 subtitle lines
        for i in range(3):
            if i < len(self.current_lines):
                line_text = (self.current_lines[i][:20]).ljust(20)
            else:
                line_text = " " * 20
            row_strings.append(f"|{line_text}|")
            
        row_strings.append(bottom_border)
        return "\n".join(row_strings)

    def close(self):
        self.clear()


class HardwareOLEDDisplay:
    """
    Physical OLED driver using luma.oled (SSD1306 128x64 over I2C).
    """
    def __init__(self, width=128, height=64, i2c_port=1, i2c_address=0x3C):
        if not (_HAS_PIL and _HAS_LUMA):
            raise RuntimeError("PIL and luma.oled are required for hardware OLED support.")
        
        self.width = width
        self.height = height
        self.serial = i2c(port=i2c_port, address=i2c_address)
        self.device = ssd1306(self.serial, width=width, height=height)
        self.font = ImageFont.load_default()
        self.current_header = ""
        self.current_lines = []

    def clear(self):
        self.device.clear()
        self.current_header = ""
        self.current_lines = []

    def display_text_lines(self, lines: list, header: str = None):
        self.current_header = header if header is not None else ""
        self.current_lines = list(lines)
        
        image = Image.new("1", (self.width, self.height), 0)
        draw = ImageDraw.Draw(image)
        
        y_offset = 2
        if self.current_header:
            draw.text((2, y_offset), self.current_header, font=self.font, fill=255)
            y_offset += 14
            draw.line((0, y_offset - 2, self.width, y_offset - 2), fill=255)
            
        for line in self.current_lines[:3]:
            draw.text((2, y_offset), line, font=self.font, fill=255)
            y_offset += 14
            
        self.device.display(image)

    def render_ascii(self) -> str:
        # Fallback representation for inspection
        mock = MockOLEDDisplay(self.width, self.height)
        mock.display_text_lines(self.current_lines, header=self.current_header)
        return mock.render_ascii()

    def close(self):
        self.clear()


class OLEDDisplay:
    """
    TriSense Deaf Mode OLED Display abstraction.
    Automatically uses hardware OLED if luma.oled + I2C are present,
    otherwise falls back to MockOLEDDisplay unless use_mock is explicitly set.
    """
    def __init__(self, width=128, height=64, use_mock=None):
        self.width = width
        self.height = height
        
        if use_mock is None:
            use_mock = not (_HAS_PIL and _HAS_LUMA)
            
        if use_mock:
            self._driver = MockOLEDDisplay(width=width, height=height)
            self.mode = "MockOLEDDisplay"
        else:
            try:
                self._driver = HardwareOLEDDisplay(width=width, height=height)
                self.mode = "HardwareOLEDDisplay"
            except Exception as e:
                print(f"[OLED] Hardware init failed ({e}). Falling back to MockOLEDDisplay.")
                self._driver = MockOLEDDisplay(width=width, height=height)
                self.mode = "MockOLEDDisplay"

    def clear(self):
        self._driver.clear()

    def display_text_lines(self, lines: list, header: str = None):
        """
        Displays up to 3 subtitle lines with an optional top status header.
        """
        self._driver.display_text_lines(lines, header=header)

    def render_ascii(self) -> str:
        """
        Returns ASCII box representation of current display contents.
        """
        return self._driver.render_ascii()

    def get_current_lines(self) -> list:
        return getattr(self._driver, "current_lines", [])

    def get_current_header(self) -> str:
        return getattr(self._driver, "current_header", "")

    def close(self):
        self._driver.close()
