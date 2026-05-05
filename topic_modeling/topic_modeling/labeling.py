"""NVIDIA NIM API client for topic labeling.

- Token-bucket rate limiter (configurable RPM, default 40).
- tenacity retries with exponential backoff on 429/5xx/timeouts.
- Prompt rendering from configs/prompts/labeling_prompt.txt with [KEYWORDS] /
  [DOCUMENTS] substitution.
- Response validation: strip quotes, enforce ≤5 words, ASCII-only check,
  lazy-label flag, intra-university dedup.
- Raw response caching to api_cache/labeling_responses/{UNIV}/{topic_id}.json.
"""
from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .io_utils import sha256_text, write_json
from .logging_setup import setup_logger
from .textprep import strip_placeholders

log = setup_logger(__name__)


class RateLimitError(Exception):
    """Raised on HTTP 429; carries optional retry_after seconds."""
    def __init__(self, retry_after: float | None = None):
        super().__init__(f"rate limited; retry_after={retry_after}")
        self.retry_after = retry_after


class TransientAPIError(Exception):
    """Raised on 5xx and network/timeout errors."""


# --- Token bucket ----------------------------------------------------------

class TokenBucket:
    """Simple thread-safe token bucket. Refills `rpm` tokens per minute."""

    def __init__(self, rpm: int):
        self.capacity = rpm
        self.tokens = float(rpm)
        self.refill_per_sec = rpm / 60.0
        self.last = time.monotonic()
        self.lock = threading.Lock()

    def acquire(self) -> None:
        while True:
            with self.lock:
                now = time.monotonic()
                elapsed = now - self.last
                self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_per_sec)
                self.last = now
                if self.tokens >= 1.0:
                    self.tokens -= 1.0
                    return
                wait = (1.0 - self.tokens) / self.refill_per_sec
            time.sleep(min(wait, 1.0))


# --- Prompt rendering ------------------------------------------------------

def load_prompt_template(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def load_acronyms_for_university(configs_dir: Path, univ_code: str) -> dict[str, str]:
    """Load configs/acronyms/<UNIV_CODE>.yaml and flatten units+offices into one
    {acronym: expansion} dict. Returns {} when no glossary exists."""
    p = configs_dir / "acronyms" / f"{univ_code}.yaml"
    if not p.exists():
        return {}
    import yaml
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    flat: dict[str, str] = {}
    for section in ("units", "offices"):
        section_data = data.get(section) or {}
        for k, v in section_data.items():
            flat[str(k)] = str(v)
    return flat


def parse_prompt(rendered: str) -> list[dict]:
    """Split a rendered prompt on the first 'USER:' marker into chat-completion
    messages. The prompt template uses 'SYSTEM:' / 'USER:' literal prefixes."""
    sys_idx = rendered.find("SYSTEM:")
    usr_idx = rendered.find("USER:")
    if sys_idx == -1 or usr_idx == -1:
        # Fall back to single-user prompt
        return [{"role": "user", "content": rendered.strip()}]
    sys_text = rendered[sys_idx + len("SYSTEM:"):usr_idx].strip()
    usr_text = rendered[usr_idx + len("USER:"):].strip()
    return [
        {"role": "system", "content": sys_text},
        {"role": "user", "content": usr_text},
    ]


def render_prompt(template: str, keywords: list[str], rep_docs: list[dict],
                  *, doc_truncate_chars: int = 280) -> str:
    kw_str = ", ".join(keywords)
    doc_lines = []
    for i, d in enumerate(rep_docs, start=1):
        # Strip anonymization placeholders before sending to NIM. The LLM gets
        # nothing useful from "[REDACTED_NAME]" and it crowds the prompt token
        # budget. Names and locations are already anonymized upstream — these
        # placeholders are pure visual noise to the model.
        text = strip_placeholders((d.get("text") or "").replace("\n", " ").strip())
        if len(text) > doc_truncate_chars:
            text = text[:doc_truncate_chars] + "…"
        doc_lines.append(f"{i}. {text}")
    docs_str = "\n".join(doc_lines) if doc_lines else "(no representative documents)"
    return template.replace("[KEYWORDS]", kw_str).replace("[DOCUMENTS]", docs_str)


def build_context_system_message(
    *,
    acronyms: dict[str, str] | None = None,
    temporal_hint: str | None = None,
) -> str | None:
    """Build an optional EXTRA system message prepended before the locked methodology
    prompt. Returns None when there's no extra context to add.

    The locked methodology prompt (configs/prompts/labeling_prompt.txt) stays
    verbatim — this is an additive system message, not a modification.
    """
    parts: list[str] = []
    if acronyms:
        lines = [f"  - {ac} = {expansion}" for ac, expansion in sorted(acronyms.items())]
        parts.append(
            "Domain glossary for this university (use these expansions when "
            "interpreting keywords or representative posts; do not invent "
            "alternative interpretations):\n" + "\n".join(lines)
        )
    if temporal_hint:
        parts.append(
            f"Temporal context: the posts in this cluster are concentrated in "
            f"{temporal_hint}. The discussion likely refers to a specific event, "
            f"policy change, or incident occurring in that timeframe. The label "
            f"should reflect that event when one is identifiable from the posts."
        )
    if not parts:
        return None
    return "\n\n".join(parts)


# --- Validation helpers ----------------------------------------------------

_LAZY_REGEX = re.compile(
    r"^(general(\s+\w+)?|various(\s+\w+)?|misc(ellaneous)?(\s+\w+)?|other(\s+\w+)?|"
    r"topic\s*\d+|noise|miscellaneous topics?|assorted)\s*$",
    re.IGNORECASE,
)
_LAZY_PHRASES = {
    "general discussion", "various topics", "miscellaneous", "miscellaneous topics",
    "general topics", "other topics", "assorted topics", "mixed topics", "no theme",
    "untitled", "general", "various", "miscellaneous discussion",
}


def is_lazy_label(label: str) -> bool:
    s = (label or "").strip()
    if not s:
        return True
    if _LAZY_REGEX.match(s):
        return True
    if s.lower() in _LAZY_PHRASES:
        return True
    return False


def has_non_ascii(label: str) -> bool:
    try:
        label.encode("ascii")
        return False
    except UnicodeEncodeError:
        return True


# Curated Tagalog/Taglish-only tokens that should never appear in an English label.
# Function words, particles, and common content words. Matched whole-word, case-insensitive.
_TAGLISH_TOKENS = frozenset({
    "ang", "ng", "mga", "sa", "ay", "po", "opo", "naman", "lang", "pala", "kasi", "kase",
    "yung", "yong", "ung", "iyong", "nyo", "niyo", "nyong",
    "para", "kasi", "talaga", "sobrang", "grabe", "diba",
    "hindi", "oo", "ako", "ikaw", "siya", "kami", "tayo", "kayo", "sila",
    "pero", "tapos", "kaya", "din", "rin", "daw", "raw", "nga", "yata",
    "buhay", "puso", "bahay", "salamat", "pasensya", "kuya", "ate", "lola", "lolo",
    "magulang", "pamilya", "mahal", "gusto", "ayaw",
    "mahirap", "madali", "maganda", "pangit", "masaya", "malungkot",
    "pwede", "puwede", "dapat", "kailangan",
    "saan", "kelan", "kailan", "bakit", "paano", "pano", "sino",
    "sana", "huhu", "hahaha",
})

_WORD_RE = None


def looks_taglish(label: str) -> bool:
    """Check whether the label contains Tagalog content/function words even if
    it is pure ASCII. Used to catch Taglish leakage that has_non_ascii() misses.
    """
    import re
    global _WORD_RE
    if _WORD_RE is None:
        _WORD_RE = re.compile(r"[a-zA-Z]+")
    for tok in _WORD_RE.findall(label or ""):
        if tok.lower() in _TAGLISH_TOKENS:
            return True
    return False


def strip_wrapping_quotes(label: str) -> tuple[str, bool]:
    s = label.strip()
    stripped = False
    while len(s) >= 2 and s[0] in ("\"", "'", "“", "”", "‘", "’") and s[-1] in ("\"", "'", "“", "”", "‘", "’"):
        s = s[1:-1].strip()
        stripped = True
    return s, stripped


def truncate_to_n_words(label: str, n: int) -> tuple[str, bool]:
    words = label.split()
    if len(words) <= n:
        return label, False
    return " ".join(words[:n]), True


# --- API client ------------------------------------------------------------

@dataclass
class NimClient:
    api_key: str
    endpoint: str
    model_id: str
    temperature: float = 0.1
    max_tokens: int = 20
    request_timeout: float = 30.0
    max_retries: int = 5
    backoff_min: float = 1.0
    backoff_max: float = 16.0
    rate_limiter: TokenBucket | None = None
    _client: Any = field(default=None, init=False, repr=False)

    def __post_init__(self):
        import httpx
        self._client = httpx.Client(
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            timeout=self.request_timeout,
        )

    def chat(self, messages: list[dict]) -> tuple[str, dict]:
        """Call the NIM chat-completions endpoint with retries.

        Returns (content_str, response_meta_dict). Raises after max_retries
        on persistent failures; raises immediately on auth errors.
        """
        import httpx

        body = {
            "model": self.model_id,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        attempt = 0
        backoff = self.backoff_min
        while True:
            attempt += 1
            if self.rate_limiter is not None:
                self.rate_limiter.acquire()
            try:
                resp = self._client.post(self.endpoint, json=body)
            except (httpx.TimeoutException, httpx.NetworkError) as e:
                log.warning("NIM transient error attempt %d: %s", attempt, e)
                if attempt >= self.max_retries:
                    raise TransientAPIError(str(e)) from e
                time.sleep(backoff)
                backoff = min(self.backoff_max, backoff * 2)
                continue

            if resp.status_code == 401:
                raise RuntimeError("NIM API key invalid (HTTP 401). Aborting.")
            if resp.status_code == 429:
                ra = resp.headers.get("retry-after")
                wait = float(ra) if ra and ra.replace(".", "", 1).isdigit() else backoff
                log.warning("NIM 429 attempt %d; sleeping %.1fs", attempt, wait)
                if attempt >= self.max_retries:
                    raise RateLimitError(retry_after=wait)
                time.sleep(wait)
                backoff = min(self.backoff_max, backoff * 2)
                continue
            if 500 <= resp.status_code < 600:
                log.warning("NIM 5xx attempt %d: %s", attempt, resp.status_code)
                if attempt >= self.max_retries:
                    raise TransientAPIError(f"HTTP {resp.status_code}: {resp.text[:200]}")
                time.sleep(backoff)
                backoff = min(self.backoff_max, backoff * 2)
                continue

            try:
                resp.raise_for_status()
            except httpx.HTTPStatusError as e:
                raise RuntimeError(f"NIM unexpected status {resp.status_code}: {resp.text[:200]}") from e

            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            meta = {
                "status_code": resp.status_code,
                "headers": {k: v for k, v in resp.headers.items()
                            if k.lower() in {"x-model-version", "x-request-id", "date"}},
                "usage": data.get("usage", {}),
                "model": data.get("model", self.model_id),
            }
            return content, meta

    def close(self) -> None:
        if self._client is not None:
            self._client.close()


# --- Topic labeling --------------------------------------------------------

def label_topic(
    client: NimClient,
    template: str,
    *,
    univ_code: str,
    topic_id: int,
    keywords: list[str],
    rep_docs: list[dict],
    cache_dir: Path,
    max_words: int = 5,
    acronyms: dict[str, str] | None = None,
    temporal_hint: str | None = None,
) -> dict:
    """Label one topic. Returns:
        {topic_id, label, flags, retries, response_meta, prompt_sha256}

    Optional `acronyms` and `temporal_hint` are injected as an extra SYSTEM
    message prepended to the locked methodology prompt — they help the LLM
    produce more specific labels (e.g., recognizing SEA as a school name,
    or framing event-driven topics with temporal context). The locked prompt
    template itself is never modified.
    """
    rendered = render_prompt(template, keywords, rep_docs)
    messages = parse_prompt(rendered)
    extra_system = build_context_system_message(acronyms=acronyms, temporal_hint=temporal_hint)
    if extra_system is not None:
        messages = [{"role": "system", "content": extra_system}] + messages
    prompt_hash = sha256_text(rendered)   # hash the LOCKED prompt only, not the extras
    flags: list[str] = []
    retries = 0

    try:
        raw, meta = client.chat(messages)
    except (RateLimitError, TransientAPIError) as e:
        log.error("Topic %s/%s: API gave up: %s", univ_code, topic_id, e)
        return {
            "topic_id": int(topic_id), "label": "Unlabeled",
            "flags": ["API_GIVEUP"], "retries": 0,
            "response_meta": {"error": str(e)}, "prompt_sha256": prompt_hash,
        }

    label, was_quoted = strip_wrapping_quotes(raw)
    if was_quoted:
        flags.append("STRIPPED_QUOTES")

    if has_non_ascii(label) or looks_taglish(label):
        flags.append("TAGLISH_OUTPUT")
        retries += 1
        retry_messages = [{"role": "system", "content": "Reply in English only."}] + messages
        try:
            raw2, meta2 = client.chat(retry_messages)
            label2, was_q2 = strip_wrapping_quotes(raw2)
            if not has_non_ascii(label2) and not looks_taglish(label2):
                label = label2
                meta = meta2
                if was_q2:
                    flags.append("STRIPPED_QUOTES")
                flags.remove("TAGLISH_OUTPUT")
                flags.append("RESOLVED_TAGLISH_ON_RETRY")
        except (RateLimitError, TransientAPIError) as e:
            log.warning("Retry-on-Taglish failed for %s/%s: %s", univ_code, topic_id, e)

    label, truncated = truncate_to_n_words(label, max_words)
    if truncated:
        flags.append("OVERLENGTH")

    if is_lazy_label(label):
        flags.append("LAZY_LABEL")

    if not label.strip():
        label = "Unlabeled"
        flags.append("MALFORMED_OUTPUT")

    cache_response(cache_dir, univ_code, topic_id, rendered, raw, label, flags, meta, prompt_hash)

    return {
        "topic_id": int(topic_id),
        "label": label,
        "flags": flags,
        "retries": retries,
        "response_meta": meta,
        "prompt_sha256": prompt_hash,
    }


def cache_response(cache_dir: Path, univ_code: str, topic_id: int,
                   rendered_prompt: str, raw_response: str, final_label: str,
                   flags: list[str], meta: dict, prompt_hash: str) -> None:
    out_dir = cache_dir / univ_code
    out_dir.mkdir(parents=True, exist_ok=True)
    write_json(out_dir / f"{topic_id}.json", {
        "univ_code": univ_code,
        "topic_id": int(topic_id),
        "rendered_prompt": rendered_prompt,
        "prompt_sha256": prompt_hash,
        "raw_response": raw_response,
        "final_label": final_label,
        "flags": flags,
        "response_meta": meta,
    })


def dedupe_labels_intra_univ(labels: list[dict],
                             keywords: dict[int, list[tuple[str, float]]]) -> list[dict]:
    """If two topics share an identical label, append a disambiguating top-keyword."""
    by_label: dict[str, list[dict]] = {}
    for r in labels:
        by_label.setdefault(r["label"], []).append(r)
    for lbl, group in by_label.items():
        if len(group) <= 1 or lbl == "Unlabeled":
            continue
        for r in group:
            tid = r["topic_id"]
            kws = keywords.get(tid, [])
            disambig = kws[0][0] if kws else f"t{tid}"
            new_label = f"{lbl} ({disambig})"
            r["label"] = new_label
            r.setdefault("flags", []).append("DISAMBIGUATED")
    return labels
