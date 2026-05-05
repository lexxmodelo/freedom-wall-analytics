"""Phase 06 multi-language stopword flagging tests."""
from __future__ import annotations

from pathlib import Path

from preprocessing.phase06_stopwords import flag, _load_stopword_bundle

CONFIGS = Path(__file__).resolve().parents[1] / "configs"


def test_loads_all_languages():
    bundles = _load_stopword_bundle(str(CONFIGS))
    languages = {lang for lang, _ in bundles}
    # Should auto-discover at least these four
    assert {"tagalog", "english", "cebuano", "ilokano"} <= languages


def test_flags_tagalog_particles():
    bundles = _load_stopword_bundle(str(CONFIGS))
    counts = flag("ang ganda po naman talaga ng weather", bundles)
    assert "tagalog" in counts
    # `po` and `naman` are pragmatic particles
    assert counts["tagalog"].get("po", 0) >= 1
    assert counts["tagalog"].get("naman", 0) >= 1


def test_flags_cebuano_particles():
    bundles = _load_stopword_bundle(str(CONFIGS))
    counts = flag("basin naa mo na know kay og asa makapalit ang akong bike", bundles)
    assert "cebuano" in counts
    # Cebuano-distinctive: kay, og, asa, akong
    ceb = counts["cebuano"]
    assert ceb.get("kay", 0) >= 1
    assert ceb.get("og", 0) >= 1
    assert ceb.get("akong", 0) >= 1


def test_per_language_separation():
    """Tagalog particles in a Tagalog post don't show up under 'cebuano'
    even though some words (mga, sa, na) appear in both stopword lists."""
    bundles = _load_stopword_bundle(str(CONFIGS))
    counts = flag("ang ganda po naman talaga, ang gago kasi ng weather na to", bundles)
    # Tagalog should have substantive counts
    assert sum(counts.get("tagalog", {}).values()) >= 3
    # Cebuano may have a small overlap from shared particles (sa, na, mga)
    # but should NOT have Cebuano-specific markers like kay, og, akong
    ceb = counts.get("cebuano", {})
    assert ceb.get("kay", 0) == 0
    assert ceb.get("og", 0) == 0
    assert ceb.get("akong", 0) == 0


def test_empty_text_returns_empty():
    bundles = _load_stopword_bundle(str(CONFIGS))
    assert flag("", bundles) == {}
