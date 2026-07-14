"""The ONE wrapper for all LLM calls.

Every LLM call in this project goes through :func:`call`:
- prompts live as readable template files in prompts/ (``{{variable}}`` slots)
- output is validated against a Pydantic model via Gemini structured output
  (``response_schema`` + ``response_mime_type="application/json"``)
- model name / max_tokens come from config.py only
- retries on transient errors (429/5xx, timeouts) are configured explicitly
  via HttpRetryOptions — google-genai makes a single attempt by default,
  unlike the Anthropic SDK, so this must be set or a 503 fails immediately
- token usage is logged for inspectability

Swapping the LLM provider is contained to this file plus config.py — the
pipeline call sites and prompt templates never import an SDK directly.
"""

import logging
import re
from typing import TypeVar

from google import genai
from google.genai import types
from pydantic import BaseModel

import config

log = logging.getLogger("jobsearch.llm")

T = TypeVar("T", bound=BaseModel)

_PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")

# finish_reasons that mean "no usable structured answer" — treated as errors.
_BAD_FINISH_REASONS = {"SAFETY", "RECITATION", "MAX_TOKENS", "PROHIBITED_CONTENT"}

_client: genai.Client | None = None


class LLMError(RuntimeError):
    """Raised when an LLM call fails to produce valid structured output."""


def get_client() -> genai.Client:
    """Lazily create the shared client (reads GEMINI_API_KEY from env).

    Without explicit retry_options, google-genai makes exactly one attempt
    and raises immediately — no retry on 429/5xx like the Anthropic SDK gives
    for free. HttpRetryOptions() with no args uses the library's own sane
    defaults (5 attempts, ~1-60s exponential backoff with jitter, retrying
    408/429/500/502/503/504 and connect/timeout errors) — exactly the
    transient-overload case ("model is currently experiencing high demand").
    """
    global _client
    if _client is None:
        _client = genai.Client(
            http_options=types.HttpOptions(
                retry_options=types.HttpRetryOptions(),
            )
        )
    return _client


def render_prompt(prompt_name: str, **variables: object) -> str:
    """Render prompts/<name>.md, requiring an exact match between template
    placeholders and provided variables (catches drift between code and prompt).
    """
    template = (config.PROMPTS_DIR / f"{prompt_name}.md").read_text()
    expected = set(_PLACEHOLDER.findall(template))
    provided = set(variables)
    if expected != provided:
        raise ValueError(
            f"prompt '{prompt_name}': template placeholders {sorted(expected)} "
            f"do not match provided variables {sorted(provided)}"
        )
    # Single-pass substitution: substituted values are never re-scanned.
    return _PLACEHOLDER.sub(lambda m: str(variables[m.group(1)]), template)


def _finish_reason_name(response) -> str | None:
    """Best-effort name of the first candidate's finish_reason (enum or str)."""
    candidates = getattr(response, "candidates", None) or []
    if not candidates:
        return None
    reason = getattr(candidates[0], "finish_reason", None)
    if reason is None:
        return None
    return getattr(reason, "name", str(reason))


def call(
    prompt_name: str,
    output_model: type[T],
    *,
    client: genai.Client | None = None,
    model: str | None = None,
    max_tokens: int | None = None,
    **variables: object,
) -> T:
    """Render a prompt template and return a validated ``output_model`` instance.

    ``client`` is injectable so tests can pass a mock — tests must never hit
    the live API. ``model``/``max_tokens`` let each pipeline step pick its own
    settings (config.MODEL_EXTRACT, MAX_TOKENS_TAILOR, ...); omitted, they
    fall back to the global config.MODEL / config.MAX_TOKENS.
    """
    client = client or get_client()
    model = model or config.MODEL
    max_tokens = max_tokens or config.MAX_TOKENS
    prompt = render_prompt(prompt_name, **variables)
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=output_model,
            max_output_tokens=max_tokens,
        ),
    )

    # A blocked prompt / safety stop is Gemini's equivalent of a refusal.
    block_reason = getattr(
        getattr(response, "prompt_feedback", None), "block_reason", None
    )
    if block_reason:
        raise LLMError(f"LLM blocked the '{prompt_name}' request ({block_reason})")

    finish = _finish_reason_name(response)
    # Log finish_reason unconditionally so a MAX_TOKENS cutoff is visible in
    # the logs even before (or without) the raise below.
    log.info("llm call prompt=%s model=%s finish_reason=%s", prompt_name, model, finish)
    if finish in _BAD_FINISH_REASONS:
        raise LLMError(
            f"LLM did not complete the '{prompt_name}' request (finish_reason={finish})"
        )

    parsed = getattr(response, "parsed", None)
    if parsed is None:
        raise LLMError(
            f"LLM returned no parseable {output_model.__name__} "
            f"for prompt '{prompt_name}' (finish_reason={finish})"
        )

    usage = getattr(response, "usage_metadata", None)
    if usage is not None:
        log.info(
            "llm call prompt=%s model=%s input_tokens=%s output_tokens=%s",
            prompt_name, model,
            getattr(usage, "prompt_token_count", None),
            getattr(usage, "candidates_token_count", None),
        )
    return parsed
