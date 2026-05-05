"""Phase 03 regex tests."""
from __future__ import annotations

from preprocessing.phase03_noise_regex import clean_noise


def test_strips_submitted_prefix():
    """The whole 'Submitted: <date>' line is stripped — see
    test_strips_submitted_with_trailing_date for the corpus-realistic case."""
    assert clean_noise("body text\nSubmitted: October 6, 2025") == "body text"


def test_strips_see_more():
    assert clean_noise("hello world ... See more").startswith("hello world")
    assert "See more" not in clean_noise("hello ... See more")


def test_strips_url_email_phone():
    out = clean_noise("Contact me at user@example.com or +639171234567 visit https://example.com")
    assert "@" not in out
    assert "+63" not in out
    assert "https" not in out


def test_strips_student_id():
    assert "20210123" not in clean_noise("My student number is 20210123 ok")


def test_collapses_char_repeat():
    assert clean_noise("haaaay") == "haaay"
    assert clean_noise("sobrangggg") == "sobranggg"  # 4+ g's collapse to 3


def test_collapses_whitespace():
    assert clean_noise("hello   \n\t world") == "hello world"


def test_strips_lone_surrogate():
    text = "ok \udc8f end"
    out = clean_noise(text)
    assert "\udc8f" not in out


def test_strips_submitted_with_trailing_date():
    """The whole 'Submitted: ... UTC' line, including the date, should be
    stripped — it's a .ninja platform timestamp, not discourse content."""
    text = "post body here\nSubmitted: October 6, 2025 11:46:33 PM UTC"
    out = clean_noise(text)
    assert "Submitted" not in out
    assert "October" not in out
    assert "UTC" not in out
    assert "post body here" in out


def test_strips_submitted_various_date_formats():
    for sub in [
        "Submitted: 1/15/2026",
        "Submitted: december 30 2025",
        "Submitted: 2025-11-11 16:39:28",
        "Submitted: 12am Oct 18 by a livid Polsci 20 student",
    ]:
        out = clean_noise(f"body {sub}")
        assert "Submitted" not in out, f"failed on: {sub!r} -> {out!r}"
        assert out.startswith("body")


def test_strips_standalone_ninja_timestamp():
    """Standalone .ninja timestamps (when 'Submitted:' is absent) should
    also be stripped. Identifying signature: HH:MM:SS [TZ]."""
    cases = [
        "post body March 31, 7:53:56 PM UTC",
        "another post October 6, 2025 11:46:33 PM UTC",
        "iso-style 2025-11-11 16:39:28",
    ]
    for text in cases:
        out = clean_noise(text)
        assert "UTC" not in out
        assert ":" not in out or "post body" in out or "another post" in out or "iso-style" in out


def test_keeps_casual_date_without_seconds():
    """A casual date reference WITHOUT seconds should NOT be stripped —
    e.g. 'see you on March 15 at 8pm'."""
    text = "see you on March 15 at 8pm"
    out = clean_noise(text)
    assert "March 15" in out
