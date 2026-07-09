"""Contract tests for the extract_job prompt's I/O — mocked client, no live API."""

from pathlib import Path

import pytest

import config
import llm
from pipeline import ingest
from sources import manual_paste
from sources.manual_paste import ExtractedJobFields
from tests.conftest import FakeLLMClient, make_response

SAMPLE_JD = (Path(__file__).parent / "fixtures" / "sample_jd.txt").read_text()
SAMPLE_URL = "https://www.linkedin.com/jobs/view/1234567890"

FIELDS = ExtractedJobFields(
    company_name="Acme AI Labs",
    title="AI Engineer",
    location="Bengaluru, Karnataka, India",
    remote_type="hybrid",
    posted_at="2026-06-25",
)


def test_capture_sends_url_and_jd_and_keeps_text_verbatim():
    client = FakeLLMClient(make_response(FIELDS))
    posting = manual_paste.capture(SAMPLE_URL, SAMPLE_JD, client=client)

    # Input contract: the rendered prompt carries the URL and full JD text.
    assert SAMPLE_URL in client.last_prompt
    assert "Acme AI Labs is building retrieval-augmented" in client.last_prompt
    assert client.calls[-1]["model"] == config.MODEL
    assert client.calls[-1]["output_format"] is ExtractedJobFields

    # Output contract: fields land on the posting; JD is stored verbatim.
    assert posting.company_name == "Acme AI Labs"
    assert posting.remote_type == "hybrid"
    assert posting.description_text == SAMPLE_JD
    assert posting.source == "manual_paste"


def test_capture_raises_on_unparseable_output():
    client = FakeLLMClient(make_response(None))
    with pytest.raises(llm.LLMError):
        manual_paste.capture(SAMPLE_URL, SAMPLE_JD, client=client)


def test_capture_raises_on_refusal():
    client = FakeLLMClient(make_response(None, stop_reason="refusal"))
    with pytest.raises(llm.LLMError):
        manual_paste.capture(SAMPLE_URL, SAMPLE_JD, client=client)


def test_render_prompt_rejects_variable_mismatch():
    with pytest.raises(ValueError):
        llm.render_prompt("extract_job", url=SAMPLE_URL)  # missing jd_text, today


def test_ingest_stores_then_detects_duplicates(conn):
    client = FakeLLMClient(make_response(FIELDS))

    first = ingest.ingest_pasted_job(conn, SAMPLE_URL, SAMPLE_JD, client=client)
    assert first.duplicate is False

    # Same role pasted again from a *different* URL → dedup by fingerprint.
    other_url = "https://www.linkedin.com/jobs/view/999"
    second = ingest.ingest_pasted_job(conn, other_url, SAMPLE_JD, client=client)
    assert second.duplicate is True
    assert second.job_id == first.job_id

    # Same URL again → dedup by exact URL as well.
    third = ingest.ingest_pasted_job(conn, SAMPLE_URL, SAMPLE_JD, client=client)
    assert third.duplicate is True
    assert third.job_id == first.job_id


def test_ingest_rejects_empty_input(conn):
    client = FakeLLMClient(make_response(FIELDS))
    with pytest.raises(ValueError):
        ingest.ingest_pasted_job(conn, SAMPLE_URL, "   \n", client=client)
    with pytest.raises(ValueError):
        ingest.ingest_pasted_job(conn, "  ", SAMPLE_JD, client=client)
    assert client.calls == []  # nothing reached the LLM
