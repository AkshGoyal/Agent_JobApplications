"""The ONE wrapper for all LLM calls.

Every LLM call in this project goes through :func:`call`:
- prompts live as readable template files in prompts/ (``{{variable}}`` slots)
- output is validated against a Pydantic model via ``client.messages.parse``
- model name / max_tokens come from config.py only
- retries are handled by the anthropic SDK's built-in retry logic
- token usage is logged for inspectability
"""

import logging
import re
from typing import TypeVar

import anthropic
from pydantic import BaseModel

import config

log = logging.getLogger("jobsearch.llm")

T = TypeVar("T", bound=BaseModel)

_PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")

_client: anthropic.Anthropic | None = None


class LLMError(RuntimeError):
    """Raised when an LLM call fails to produce valid structured output."""


def get_client() -> anthropic.Anthropic:
    """Lazily create the shared client (reads ANTHROPIC_API_KEY from env)."""
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
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


def call(
    prompt_name: str,
    output_model: type[T],
    *,
    client: anthropic.Anthropic | None = None,
    **variables: object,
) -> T:
    """Render a prompt template and return a validated ``output_model`` instance.

    ``client`` is injectable so tests can pass a mock — tests must never hit
    the live API.
    """
    client = client or get_client()
    prompt = render_prompt(prompt_name, **variables)
    response = client.messages.parse(
        model=config.MODEL,
        max_tokens=config.MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
        output_format=output_model,
    )
    if getattr(response, "stop_reason", None) == "refusal":
        raise LLMError(f"LLM refused the '{prompt_name}' request")
    if response.parsed_output is None:
        raise LLMError(
            f"LLM returned no parseable {output_model.__name__} "
            f"for prompt '{prompt_name}' (stop_reason={response.stop_reason})"
        )
    usage = getattr(response, "usage", None)
    if usage is not None:
        log.info(
            "llm call prompt=%s model=%s input_tokens=%s output_tokens=%s",
            prompt_name, config.MODEL, usage.input_tokens, usage.output_tokens,
        )
    return response.parsed_output
