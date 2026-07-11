"""Client construction: retry must be configured, or a single transient error
(e.g. 503 UNAVAILABLE) fails the whole call — google-genai does not retry by
default the way the Anthropic SDK did.

Constructing genai.Client() with a fake key does not touch the network, so
this is safe to run offline like every other test.
"""

import llm


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
