"""Phase 03: Noise reduction and regex cleaning.

Removes:
- "Submitted:" prefixes
- "...See more" suffixes and trailing ellipses
- URLs, emails, phone numbers, stray digit runs (student IDs)
- Lone surrogate code points (decoding artifacts)

Normalizes:
- 4+ repeated chars → exactly 3 (preserves emphasis like "sooo bad")
- Whitespace runs → single space
"""
from __future__ import annotations

from typing import Iterable

from .regex_lib import PATTERNS, char_repeat_collapse


def clean_noise(text: str) -> str:
    text = PATTERNS["lone_surrogate"].sub("", text)
    text = PATTERNS["submitted_prefix"].sub("", text)
    text = PATTERNS["see_more"].sub("", text)
    text = PATTERNS["url"].sub("", text)
    text = PATTERNS["email"].sub("", text)
    text = PATTERNS["phone_ph"].sub("", text)
    text = PATTERNS["student_id"].sub("", text)
    # Strip residual hashtags that survived phase02. Phase02 replaces
    # school-related ones with region tags; anything left here is noise
    # (campaign/sports tags like #UAAPSeason88, #DLSU, #AnimoLaSalle).
    text = PATTERNS["any_hashtag"].sub("", text)
    text = char_repeat_collapse(text)
    text = PATTERNS["ellipsis_trail"].sub("", text)
    text = PATTERNS["whitespace"].sub(" ", text).strip()
    return text


def run(posts: Iterable[dict]):
    for post in posts:
        if post is None:
            yield None
            continue
        post["text"] = clean_noise(post["text"])
        yield post
