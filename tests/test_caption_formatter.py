"""Unit tests for the Deaf Mode caption formatter (pure Python)."""

from deaf_mode.caption_formatter import CaptionFormatter


def test_empty_text_yields_no_lines():
    fmt = CaptionFormatter()
    assert fmt.format_caption("") == []
    assert fmt.format_caption("   ") == []


def test_capitalises_and_terminates_final_utterance():
    fmt = CaptionFormatter()
    assert fmt.format_caption("hello world", is_final=True) == ["Hello world."]
    assert fmt.format_caption("hello world", is_final=False) == ["Hello world"]


def test_existing_punctuation_is_not_doubled():
    fmt = CaptionFormatter()
    assert fmt.format_caption("is anyone there?", is_final=True) == ["Is anyone there?"]


def test_wraps_without_breaking_words_or_exceeding_width():
    fmt = CaptionFormatter(max_chars_per_line=20, max_lines=3)
    lines = fmt.format_caption("the quick brown fox jumps over the lazy dog today")
    assert all(len(line) <= 20 for line in lines)
    assert " ".join(lines).lower() == "the quick brown fox jumps over the lazy dog today"


def test_display_lines_keep_latest_and_mark_truncation():
    fmt = CaptionFormatter(max_chars_per_line=20, max_lines=2)
    text = "one two three four five six seven eight nine ten eleven twelve"
    visible = fmt.get_display_lines(text)
    assert len(visible) == 2
    assert visible[0].startswith("...")
    assert visible[-1].endswith("twelve")
    assert all(len(line) <= 20 for line in visible)


def test_display_string_is_newline_joined():
    fmt = CaptionFormatter(max_chars_per_line=10, max_lines=3)
    assert fmt.get_display_string("aaaa bbbb cccc") == "Aaaa bbbb\ncccc"
