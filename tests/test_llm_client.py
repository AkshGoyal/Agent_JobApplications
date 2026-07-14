"""Client construction: retry must be configured, or a single transient error
(e.g. 503 UNAVAILABLE) fails the whole call — google-genai does not retry by
default the way the Anthropic SDK did.

Constructing genai.Client() with a fake key does not touch the network, so
this is safe to run offline like every other test.
"""

import config
import llm
from pipeline.rank import RankingResult
from tests.conftest import FakeLLMClient, make_response

RESULT = RankingResult(score=50, rationale="ok")
RANK_VARS = dict(
    profile_context="p", company="c", title="t",
    location="l", remote_type="remote", jd_text="jd",
)


def test_call_defaults_to_global_model_and_max_tokens():
    client = FakeLLMClient(make_response(RESULT))
    llm.call("rank_job", RankingResult, client=client, **RANK_VARS)
    assert client.calls[-1]["model"] == config.MODEL
    assert client.calls[-1]["config"].max_output_tokens == config.MAX_TOKENS


def test_call_respects_per_task_model_and_max_tokens_overrides():
    client = FakeLLMClient(make_response(RESULT))
    llm.call(
        "rank_job", RankingResult, client=client,
        model="some-other-model", max_tokens=9999, **RANK_VARS,
    )
    assert client.calls[-1]["model"] == "some-other-model"
    assert client.calls[-1]["config"].max_output_tokens == 9999


def test_get_client_configures_retry_on_transient_errors(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key-for-construction-test")
    llm._client = None  # this test owns the module-level singleton
    try:
        client = llm.get_client()
        retry_options = client._api_client._http_options.retry_options
        assert retry_options is not None, (
            "no retry_options set — a single 503/429/timeout will fail the "
            "whole request instead of being retried"
        )
    finally:
        llm._client = None  # don't leak a client built with a fake key
