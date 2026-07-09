"""Shared test helpers. Tests NEVER call the live API — always use FakeLLMClient."""

from types import SimpleNamespace

import pytest

from db import database


class FakeLLMClient:
    """Mimics anthropic.Anthropic just enough for llm.call().

    Takes one or more canned responses; each parse() call consumes the next
    one (the last response repeats). Records every call's kwargs in .calls.
    """

    def __init__(self, *responses):
        self._responses = list(responses)
        self.calls = []
        self.messages = self  # so client.messages.parse resolves to self.parse

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        if len(self._responses) > 1:
            return self._responses.pop(0)
        return self._responses[0]

    @property
    def last_prompt(self) -> str:
        return self.calls[-1]["messages"][0]["content"]


def make_response(parsed_output, stop_reason="end_turn"):
    """Build an object shaped like the SDK's parse() response."""
    return SimpleNamespace(
        parsed_output=parsed_output,
        stop_reason=stop_reason,
        usage=SimpleNamespace(input_tokens=100, output_tokens=50),
    )


@pytest.fixture
def conn(tmp_path):
    c = database.connect(tmp_path / "test.db")
    yield c
    c.close()
