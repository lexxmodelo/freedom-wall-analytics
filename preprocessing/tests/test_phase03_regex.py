"""Phase 03 regex tests."""
from __future__ import annotations

from preprocessing.phase03_noise_regex import clean_noise


def test_strips_submitted_prefix():
    assert clean_noise("Submitted: hello") == "hello"


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
