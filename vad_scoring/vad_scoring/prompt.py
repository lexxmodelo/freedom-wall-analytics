"""VAD prompt builder.

Reproduces the locked SYSTEM/USER prompt from methodology_changes.md §3.4 verbatim,
with three few-shot anchors injected from configs/few_shot_examples.json.

The output of build_messages() is a list[dict] of chat-completions messages,
ready to pass to NimClient.chat(). The SYSTEM prompt is fixed; the USER prompt
contains the 3 anchors followed by the 5 posts to score.

prompt_sha256 (in vad_config.json) is computed by sha256_text(build_user_prompt(
empty batch placeholder)) so it captures the locked anchors and instructions
without varying per-batch.
"""
from __future__ import annotations

import json
from typing import Any

from .io_utils import sha256_text


SYSTEM_PROMPT = (
    "You are a psycholinguistic analyst specializing in Filipino student "
    "discourse. You score social media posts on the Self-Assessment Manikin "
    "(SAM) scale across three dimensions:\n"
    "- Valence (V): 1 = extremely negative, 9 = extremely positive\n"
    "- Arousal (A): 1 = calm/passive, 9 = excited/agitated\n"
    "- Dominance (D): 1 = helpless/controlled, 9 = empowered/in-control\n\n"
    "You also detect sarcasm and irony in Taglish text."
)

USER_HEADER = (
    "Score the following 5 posts. Each post has an ID and an assigned topic for "
    "context.\n"
)

USER_INSTRUCTIONS = (
    "IMPORTANT: Before scoring, internally assess whether each post uses sarcasm, "
    "irony, or exaggeration. If sarcasm is detected, score based on the TRUE "
    "underlying emotion, not the surface text.\n\n"
    "Respond with ONLY a JSON array of 5 objects:\n"
    '[{"id":"...","V":int,"A":int,"D":int,"sarcasm":bool}, ...]'
)


def render_few_shot_block(examples: list[dict]) -> str:
    """Render the 3 anchors as in-prompt few-shot exemplars.

    Each anchor becomes one INPUT line followed by an EXPECTED line, so the
    model sees the exact mapping from (topic, text) → JSON object.
    """
    lines = ["Few-shot anchors (these are reference scorings, do not re-score them):", ""]
    for i, ex in enumerate(examples, start=1):
        topic = ex.get("topic", "Unclassified")
        text = ex.get("text", "").replace("\n", " ").strip()
        scores = ex.get("scores", {})
        scored = {
            "id": ex.get("id", f"anchor_{i}"),
            "V": scores.get("V"),
            "A": scores.get("A"),
            "D": scores.get("D"),
            "sarcasm": scores.get("sarcasm", False),
        }
        lines.append(f'Example {i} [ID: {scored["id"]}] (Topic: {topic}): "{text}"')
        lines.append(f"  → {json.dumps(scored, ensure_ascii=False)}")
    lines.append("")
    return "\n".join(lines)


def render_post_block(posts: list[dict]) -> str:
    """Render the batch of N posts in the format the prompt expects.

    Each post is one line: `Post K [ID: <id>] (Topic: <label>): "<text>"`
    Text is single-line (newlines collapsed to spaces) and is NOT truncated here
    — truncation is the batcher's responsibility before this function is called.
    """
    lines: list[str] = []
    for i, p in enumerate(posts, start=1):
        text = (p.get("text") or "").replace("\n", " ").replace("\r", " ").strip()
        topic = p.get("topic_label", "Unclassified")
        lines.append(f'Post {i} [ID: {p["post_id"]}] (Topic: {topic}): "{text}"')
    return "\n".join(lines)


def build_user_prompt(posts: list[dict], few_shot_examples: list[dict]) -> str:
    """Build the USER message body for one batch."""
    return (
        USER_HEADER + "\n"
        + render_few_shot_block(few_shot_examples) + "\n"
        + render_post_block(posts) + "\n\n"
        + USER_INSTRUCTIONS
    )


def build_messages(posts: list[dict], few_shot_examples: list[dict]) -> list[dict]:
    """Construct the chat-completions messages array for one batch."""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_user_prompt(posts, few_shot_examples)},
    ]


def compute_prompt_sha256(few_shot_examples: list[dict]) -> str:
    """SHA-256 of the locked prompt skeleton + few-shot anchors.

    Excludes the per-batch posts so the hash is stable across runs as long as
    the SYSTEM prompt, USER instructions, and anchors stay the same.
    """
    skeleton = SYSTEM_PROMPT + "\n\n" + USER_HEADER + "\n" + render_few_shot_block(few_shot_examples) + "\n" + USER_INSTRUCTIONS
    return sha256_text(skeleton)
