"""Contract tests for the rank_job prompt's I/O — mocked client, no live API."""

import pytest
from pydantic import ValidationError

import llm
from db import repo
from pipeline import ingest, rank
from pipeline.rank import RankingResult
from sources.manual_paste import ExtractedJobFields
from tests.conftest import FakeLLMClient, make_response
from tests.test_extraction_contract import FIELDS, SAMPLE_JD, SAMPLE_URL


def _stored_job(conn) -> int:
    client = FakeLLMClient(make_response(FIELDS))
    return ingest.ingest_pasted_job(conn, SAMPLE_URL, SAMPLE_JD, client=client).job_id


def test_rank_prompt_contains_profile_and_job(conn):
    job_id = _stored_job(conn)
    client = FakeLLMClient(
        make_response(RankingResult(score=85, rationale="Strong RAG overlap."))
    )
    ranked = rank.rank_job(conn, job_id, client=client)

    # Input contract: prompt carries the profile targets and the JD.
    prompt = client.last_prompt
    assert "targets:" in prompt                     # profile facts present
    assert "Acme AI Labs" in prompt                 # job company present
    assert "retrieval-augmented" in prompt          # JD text present
    assert client.calls[-1]["config"].response_schema is RankingResult

    # Output contract: score + rationale persisted, status advanced.
    assert ranked.score == 85
    job = repo.get_job(conn, job_id)
    assert job["relevance_score"] == 85
    assert job["relevance_rationale"] == "Strong RAG overlap."
    assert job["status"] == "ranked"


def test_ranking_result_rejects_out_of_range_scores():
    with pytest.raises(ValidationError):
        RankingResult(score=101, rationale="x")
    with pytest.raises(ValidationError):
        RankingResult(score=-1, rationale="x")


def test_rank_job_raises_on_unparseable_output(conn):
    job_id = _stored_job(conn)
    client = FakeLLMClient(make_response(None))
    with pytest.raises(llm.LLMError):
        rank.rank_job(conn, job_id, client=client)
    # Failure must not corrupt the job row.
    job = repo.get_job(conn, job_id)
    assert job["status"] == "discovered"
    assert job["relevance_score"] is None


def test_rank_job_unknown_id(conn):
    with pytest.raises(ValueError):
        rank.rank_job(conn, 999, client=FakeLLMClient(make_response(None)))


def test_rank_discovered_ranks_all_pending(conn):
    first = _stored_job(conn)
    other_fields = ExtractedJobFields(
        company_name="Other Corp",
        title="AI Product Manager",
        location="Mumbai",
        remote_type="onsite",
    )
    second = ingest.ingest_pasted_job(
        conn,
        "https://example.com/job/2",
        "Other Corp is hiring an AI Product Manager in Mumbai...",
        client=FakeLLMClient(make_response(other_fields)),
    ).job_id

    ranker = FakeLLMClient(
        make_response(RankingResult(score=90, rationale="Great fit.")),
        make_response(RankingResult(score=40, rationale="Weak fit.")),
    )
    ranked = rank.rank_discovered(conn, client=ranker)
    assert [(r.job_id, r.score) for r in ranked] == [(first, 90), (second, 40)]
    # Nothing left in 'discovered'; a second run ranks nothing.
    assert rank.rank_discovered(conn, client=ranker) == []
