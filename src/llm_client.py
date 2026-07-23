"""OpenRouter + Instructor client wrapper — the single doorway to the LLM.

Every step that hits the API goes through here so that policy lives in ONE place:

  * Provider    — OpenRouter via the OpenAI-compatible client (config-driven base URL).
  * Structure   — Instructor patches the client so responses are parsed into a Pydantic
                  model instead of raw text (structure-safe output).
  * Retries     — TWO layers, different failure modes (see below).
  * Rate limit  — a small courtesy delay after each call (Hard Rule #7).
  * Audit trail — every call's raw response (or error) is appended to logs/ (Rule #9,
                  decision #9): clean data in data/, verbose forensics in logs/.

TWO RETRY LAYERS (an interview favourite — do not conflate them):
  1. tenacity wraps the transport call and retries *network* failures — timeouts, 429s,
     dropped connections — with exponential backoff. It re-sends the same request.
  2. Instructor's own `max_retries` re-prompts the model on *schema-validation* failures,
     feeding the Pydantic error back so the model can fix its own output. It changes the
     conversation. For a LENIENT gen schema this rarely fires; it is our safety net.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Type, TypeVar

import instructor
from openai import (
    APIConnectionError,
    APITimeoutError,
    OpenAI,
    RateLimitError,
)
from pydantic import BaseModel
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from . import config

T = TypeVar("T", bound=BaseModel)

# Transport-level errors worth retrying (transient). Validation errors are NOT here —
# those are Instructor's job, not tenacity's.
_TRANSIENT_ERRORS = (APITimeoutError, RateLimitError, APIConnectionError)

_client: instructor.Instructor | None = None


def get_client() -> instructor.Instructor:
    """Lazily build one Instructor-patched OpenAI client pointed at OpenRouter.

    Lazy + cached: we only construct it (and assert the key exists) on first real use,
    so importing this module never forces a key to be present.
    """
    global _client
    if _client is None:
        config.assert_api_key()  # fail fast, friendly message (Rule: no key = clear error)
        base = OpenAI(
            base_url=config.OPENROUTER_BASE_URL,
            api_key=config.OPENROUTER_API_KEY,
            timeout=config.REQUEST_TIMEOUT_SECONDS,
        )
        _client = instructor.from_openai(base)
    return _client


def _log_raw(step: str, trace_id: str | None, payload: dict) -> None:
    """Append one line to the raw-response audit log (Rule #9 / decision #9)."""
    config.ensure_dirs()
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "step": step,
        "trace_id": trace_id,
        **payload,
    }
    with open(config.LOGS_DIR / "raw_responses.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


@retry(
    retry=retry_if_exception_type(_TRANSIENT_ERRORS),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,  # after 3 transport failures, surface the real error to the caller
)
def _call_with_completion(
    response_model: Type[T],
    *,
    model: str,
    temperature: float,
    messages: list[dict],
    max_retries: int,
) -> tuple[T, object]:
    """The actual API round-trip. `create_with_completion` returns BOTH the parsed model
    AND the raw completion, so we can log the raw response for the audit trail."""
    client = get_client()
    return client.chat.completions.create_with_completion(
        model=model,
        temperature=temperature,
        response_model=response_model,
        max_retries=max_retries,  # Instructor's schema-retry layer
        messages=messages,
    )


def generate_structured(
    response_model: Type[T],
    *,
    system: str,
    user: str,
    model: str | None = None,
    temperature: float | None = None,
    max_retries: int = 2,
    log_step: str = "generate",
    trace_id: str | None = None,
) -> T:
    """Ask the LLM for a structured object, with retries, audit logging, and rate-limit.

    Defaults to the generator model/temperature from config; callers (judge, corrector)
    override to run near-deterministic per Hard Rule #4.
    """
    model = model or config.GENERATOR_MODEL
    temperature = config.GENERATOR_TEMPERATURE if temperature is None else temperature
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]

    try:
        obj, completion = _call_with_completion(
            response_model,
            model=model,
            temperature=temperature,
            messages=messages,
            max_retries=max_retries,
        )
    except Exception as exc:  # Rule #6: never crash the run on a bad response — log + re-raise
        _log_raw(log_step, trace_id, {"model": model, "error": repr(exc)})
        raise

    # Audit trail: persist the raw completion so we can forensically inspect any record.
    raw = completion.model_dump() if hasattr(completion, "model_dump") else str(completion)
    _log_raw(log_step, trace_id, {"model": model, "raw": raw})

    time.sleep(config.API_CALL_DELAY_SECONDS)  # courtesy pause between calls (Rule #7)
    return obj
