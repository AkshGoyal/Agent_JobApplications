"""Shared test helpers. Tests NEVER call the live API — always use FakeLLMClient."""

from types import SimpleNamespace

import pytest

from db import database


class FakeLLMClient:
    """Mimics google.genai.Client just enough for llm.call().

    Takes one or more canned responses; each generate_content() call consumes
    the next one (the last response repeats). Records every call's kwargs in
    .calls. Tests inject this so they NEVER hit the live API.
    """

    def __init__(self, *responses):
        self._responses = list(responses)
        self.calls = []
        self.models = self  # so client.models.generate_content resolves here

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        if len(self._responses) > 1:
            return self._responses.pop(0)
        return self._responses[0]

    @property
    def last_prompt(self) -> str:
        return self.calls[-1]["contents"]


def make_response(parsed, finish_reason="STOP", blocked=False):
    """Build an object shaped like the google-genai generate_content response."""
    prompt_feedback = SimpleNamespace(
        block_reason="SAFETY" if blocked else None
    )
    candidate = SimpleNamespace(
        finish_reason=SimpleNamespace(name=finish_reason),
    )
    return SimpleNamespace(
        parsed=parsed,
        candidates=[candidate],
        prompt_feedback=prompt_feedback,
        usage_metadata=SimpleNamespace(
            prompt_token_count=100, candidates_token_count=50
        ),
    )


@pytest.fixture
def conn(tmp_path):
    c = database.connect(tmp_path / "test.db")
    yield c
    c.close()
