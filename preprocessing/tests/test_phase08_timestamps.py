"""Phase 08 timestamp tests."""
from __future__ import annotations

from preprocessing.phase08_timestamps import to_unix_pht


def test_parses_hkt_suffix():
    """The exact format the scraper emits."""
    ts = to_unix_pht("May 4, 2026 8:30:00 AM HKT", None)
    assert ts is not None
    assert isinstance(ts, int)


def test_handles_null_inputs():
    assert to_unix_pht(None, None) is None
    assert to_unix_pht("", "") is None


def test_skips_image_descriptions():
    """When timestamp_raw contains an OCR'd image description rather than a date."""
    ts = to_unix_pht(
        "May be an image of drink and text that says 'PC FORMULA SOLD!'",
        None,
    )
    assert ts is None


def test_falls_back_to_iso():
    ts = to_unix_pht(None, "2026-05-04T08:30:00")
    assert ts is not None
