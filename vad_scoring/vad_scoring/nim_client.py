"""NVIDIA NIM API client for VAD scoring.

Adapted from topic_modeling/topic_modeling/labeling.py:
  - TokenBucket: thread-safe rate limiter (configurable RPM, default 20).
  - NimClient: chat-completions caller with exponential-backoff retries on
    429/5xx/timeout, immediate halt on 401, and a circuit breaker that pauses
    for `circuit_breaker_pause_minutes` after `circuit_breaker_consecutive_failures`
    successive failed batches.

VAD-specific differences from labeling.py:
  - max_tokens raised (default 600) to fit a 5-post JSON array response
    (~80-120 tokens per post including {V,A,D,sarcasm} + IDs + bookkeeping).
  - Circuit breaker tracks consecutive batch failures across the whole pipeline,
    not just retries within a single request — this protects against thrash when
    NIM has a regional outage.
  - All raw responses are surfaced via a callback so the pipeline can persist
    them to api_cache/raw_responses_<rid>.jsonl (mandatory for reproducibility
    per methodology_changes.md §4.2).
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from .logging_setup import setup_logger

log = setup_logger(__name__)


class RateLimitError(Exception):
    """Raised on HTTP 429; carries optional retry_after seconds."""
    def __init__(self, retry_after: float | None = None):
        super().__init__(f"rate limited; retry_after={retry_after}")
        self.retry_after = retry_after


class TransientAPIError(Exception):
    """Raised on 5xx and network/timeout errors."""


class AuthError(RuntimeError):
    """Raised on HTTP 401/403. Pipeline must halt immediately — no retry."""


class CircuitOpenError(Exception):
    """Raised when the circuit breaker is open. Caller should pause."""


# --- Token bucket ----------------------------------------------------------

class TokenBucket:
    """Simple thread-safe token bucket. Refills `rpm` tokens per minute.

    Verbatim from topic_modeling.labeling.TokenBucket. The vad_scoring pipeline
    constructs this with rpm=effective_rpm (default 20) — half the NIM free-tier
    ceiling, leaving headroom for transient bursts.
    """

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


# --- Circuit breaker -------------------------------------------------------

class CircuitBreaker:
    """Trips after `threshold` consecutive failures; stays open for `pause_seconds`.

    The pipeline calls record_success() / record_failure() around each batch.
    Before each batch it calls check() which raises CircuitOpenError when the
    breaker is open and the pause window has not yet elapsed.
    """

    def __init__(self, threshold: int = 10, pause_seconds: float = 300.0):
        self.threshold = threshold
        self.pause_seconds = pause_seconds
        self.consecutive_failures = 0
        self.opened_at: float | None = None
        self.lock = threading.Lock()

    def record_success(self) -> None:
        with self.lock:
            self.consecutive_failures = 0
            self.opened_at = None

    def record_failure(self) -> bool:
        """Returns True if the breaker just tripped this call."""
        with self.lock:
            self.consecutive_failures += 1
            if self.consecutive_failures >= self.threshold and self.opened_at is None:
                self.opened_at = time.monotonic()
                log.error(
                    "Circuit breaker TRIPPED after %d consecutive failures. "
                    "Pausing for %.0f seconds.",
                    self.consecutive_failures, self.pause_seconds,
                )
                return True
            return False

    def check(self) -> None:
        """Raises CircuitOpenError if the breaker is open AND the pause has not elapsed."""
        with self.lock:
            if self.opened_at is None:
                return
            elapsed = time.monotonic() - self.opened_at
            if elapsed < self.pause_seconds:
                remaining = self.pause_seconds - elapsed
                raise CircuitOpenError(f"breaker open; resumes in {remaining:.0f}s")
            # Pause window elapsed: half-open. Reset and let the next call try.
            log.warning("Circuit breaker pause elapsed; entering half-open state.")
            self.consecutive_failures = 0
            self.opened_at = None


# --- API client ------------------------------------------------------------

@dataclass
class NimClient:
    api_key: str
    endpoint: str
    model_id: str
    temperature: float = 0.1
    max_tokens: int = 600
    request_timeout: float = 30.0
    max_retries: int = 5
    backoff_min: float = 1.0
    backoff_max: float = 16.0
    rate_limiter: TokenBucket | None = None
    breaker: CircuitBreaker | None = None
    on_raw_response: Callable[[dict], None] | None = None
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

    def chat(self, messages: list[dict], *, request_meta: dict | None = None) -> tuple[str, dict]:
        """Call the NIM chat-completions endpoint with retries.

        Returns (content_str, response_meta_dict).
        Raises AuthError on 401/403 (caller must halt).
        Raises CircuitOpenError if the breaker is open and not yet recovered.
        Raises RateLimitError or TransientAPIError after max_retries.
        """
        import httpx

        if self.breaker is not None:
            self.breaker.check()

        body = {
            "model": self.model_id,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        attempt = 0
        backoff = self.backoff_min
        last_exc: Exception | None = None
        while True:
            attempt += 1
            if self.rate_limiter is not None:
                self.rate_limiter.acquire()
            try:
                resp = self._client.post(self.endpoint, json=body)
            except (httpx.TimeoutException, httpx.NetworkError) as e:
                last_exc = e
                log.warning("NIM transient error attempt %d: %s", attempt, e)
                if attempt >= self.max_retries:
                    if self.breaker is not None:
                        self.breaker.record_failure()
                    raise TransientAPIError(str(e)) from e
                time.sleep(backoff)
                backoff = min(self.backoff_max, backoff * 2)
                continue

            if resp.status_code in (401, 403):
                # Auth failures never recover via retry — halt immediately.
                raise AuthError(
                    f"NIM API key rejected (HTTP {resp.status_code}). "
                    "Check NVIDIA_NIM_API_KEY env var or .env file."
                )
            if resp.status_code == 429:
                ra = resp.headers.get("retry-after")
                wait = float(ra) if ra and ra.replace(".", "", 1).isdigit() else backoff
                log.warning("NIM 429 attempt %d; sleeping %.1fs", attempt, wait)
                if attempt >= self.max_retries:
                    if self.breaker is not None:
                        self.breaker.record_failure()
                    raise RateLimitError(retry_after=wait)
                time.sleep(wait)
                backoff = min(self.backoff_max, backoff * 2)
                continue
            if 500 <= resp.status_code < 600:
                log.warning("NIM 5xx attempt %d: %s", attempt, resp.status_code)
                if attempt >= self.max_retries:
                    if self.breaker is not None:
                        self.breaker.record_failure()
                    raise TransientAPIError(f"HTTP {resp.status_code}: {resp.text[:200]}")
                time.sleep(backoff)
                backoff = min(self.backoff_max, backoff * 2)
                continue

            try:
                resp.raise_for_status()
            except httpx.HTTPStatusError as e:
                if self.breaker is not None:
                    self.breaker.record_failure()
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

            if self.on_raw_response is not None:
                self.on_raw_response({
                    "request_meta": request_meta or {},
                    "messages": messages,
                    "raw_content": content,
                    "response_meta": meta,
                    "attempt": attempt,
                })
            if self.breaker is not None:
                self.breaker.record_success()
            return content, meta

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
