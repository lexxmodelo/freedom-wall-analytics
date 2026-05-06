"""Parser tests: JSON repair ladder + ID coercion + range-agnostic acceptance."""
from __future__ import annotations

import pytest

from vad_scoring.parser import ParseError, parse_response


def test_clean_array_round_trip():
    text = '[{"id":"a","V":3,"A":7,"D":2,"sarcasm":false}]'
    out = parse_response(text)
    assert out == [{"id": "a", "V": 3, "A": 7, "D": 2, "sarcasm": False}]


def test_five_records():
    posts = [{"id": f"p{i}", "V": 5, "A": 5, "D": 5, "sarcasm": False} for i in range(5)]
    import json
    out = parse_response(json.dumps(posts))
    assert len(out) == 5
    assert [r["id"] for r in out] == [f"p{i}" for i in range(5)]


def test_array_buried_in_prose():
    text = (
        "Here are the scores you asked for:\n\n"
        '[{"id":"abc","V":2,"A":8,"D":3,"sarcasm":false},'
        '{"id":"def","V":7,"A":4,"D":6,"sarcasm":true}]\n\n'
        "Hope this helps!"
    )
    out = parse_response(text)
    assert len(out) == 2
    assert out[0]["id"] == "abc"
    assert out[1]["sarcasm"] is True


def test_string_numerics_coerced():
    text = '[{"id":"a","V":"3","A":"7","D":"2","sarcasm":"true"}]'
    out = parse_response(text)
    assert out[0]["V"] == 3
    assert out[0]["A"] == 7
    assert out[0]["D"] == 2
    assert out[0]["sarcasm"] is True


def test_float_score_kept_for_validator_to_clamp():
    text = '[{"id":"a","V":3.7,"A":7,"D":2,"sarcasm":false}]'
    out = parse_response(text)
    assert isinstance(out[0]["V"], (int, float))


def test_post_id_aliased_as_id():
    text = '[{"post_id":"a","V":1,"A":1,"D":1,"sarcasm":false}]'
    out = parse_response(text)
    assert out[0]["id"] == "a"


def test_single_object_wrapped():
    text = '{"id":"a","V":1,"A":1,"D":1,"sarcasm":false}'
    out = parse_response(text)
    assert len(out) == 1


def test_empty_response_raises():
    with pytest.raises(ParseError):
        parse_response("")


def test_no_array_raises():
    with pytest.raises(ParseError):
        parse_response("Sorry, I cannot answer that.")


def test_missing_id_raises():
    text = '[{"V":1,"A":1,"D":1,"sarcasm":false}]'
    with pytest.raises(ParseError):
        parse_response(text)


def test_missing_dimension_raises():
    text = '[{"id":"a","V":1,"A":1,"sarcasm":false}]'
    with pytest.raises(ParseError):
        parse_response(text)


def test_bool_in_score_field_raises():
    text = '[{"id":"a","V":true,"A":1,"D":1,"sarcasm":false}]'
    with pytest.raises(ParseError):
        parse_response(text)
