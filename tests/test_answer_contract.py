"""Contract tests for answer_question — mocked client, no live API.

Uses the real profile/canned_answers.yaml (like the profile_kb tests) since
the defense-in-depth check specifically needs to verify against real blank
vs. filled fields.
"""

import pytest

from db import repo
from pipeline.answer import AnswerResult, answer_question
from tests.conftest import FakeLLMClient, make_response


def _job(conn) -> int:
    company_id = repo.get_or_create_company(conn, "Acme AI Labs")
    return repo.insert_job(
        conn,
        company_id=company_id,
        title="AI Engineer",
        location="Bengaluru",
        remote_type="hybrid",
        source="manual_paste",
        source_url="https://e.com/answer-1",
        description_text="JD text",
        posted_at=None,
        dedup_hash="answer-hash-1",
    )


def test_canned_answer_with_filled_field_is_used_verbatim(conn):
    job_id = _job(conn)
    client = FakeLLMClient(
        make_response(
            AnswerResult(
                source="canned",
                canned_field="logistics.notice_period",
                answer="2 months",
            )
        )
    )
    record = answer_question(conn, job_id, "What is your notice period?", client=client)
    assert record.source == "canned"
    assert record.answer == "2 months"

    assets = repo.list_generated_assets(conn, job_id)
    assert len(assets) == 1
    assert assets[0]["kind"] == "form_answer"
    assert assets[0]["content"] == "2 months"


def test_canned_claim_on_blank_field_is_overridden_to_needs_input(conn):
    """Defense in depth: even if the model wrongly claims source='canned' for
    a field that's actually blank in canned_answers.yaml, code overrides it —
    never trust the model's self-report."""
    job_id = _job(conn)
    client = FakeLLMClient(
        make_response(
            AnswerResult(
                source="canned",
                canned_field="standard_questions.biggest_weakness",
                answer="I sometimes take on too much.",  # model hallucinated this
            )
        )
    )
    record = answer_question(conn, job_id, "What is your biggest weakness?", client=client)
    assert record.source == "needs_input"
    assert record.answer is None
    assert "biggest_weakness" in record.note
    assert "blank" in record.note

    # Still logged for audit, with the note as content (not the fabricated answer).
    assets = repo.list_generated_assets(conn, job_id)
    assert assets[0]["content"] == record.note


def test_canned_field_that_does_not_exist_is_treated_as_blank(conn):
    job_id = _job(conn)
    client = FakeLLMClient(
        make_response(
            AnswerResult(source="canned", canned_field="not.a.real.field", answer="x")
        )
    )
    record = answer_question(conn, job_id, "Some question", client=client)
    assert record.source == "needs_input"


def test_generated_answer_is_persisted(conn):
    job_id = _job(conn)
    client = FakeLLMClient(
        make_response(
            AnswerResult(
                source="generated",
                answer="I built a production RAG system at Aspect Ratio using hybrid retrieval.",
            )
        )
    )
    record = answer_question(
        conn, job_id, "Tell us about a relevant project.", client=client
    )
    assert record.source == "generated"
    assert "RAG" in record.answer
    assets = repo.list_generated_assets(conn, job_id)
    assert assets[0]["content"] == record.answer


def test_needs_input_from_model_is_persisted_with_note(conn):
    job_id = _job(conn)
    client = FakeLLMClient(
        make_response(
            AnswerResult(
                source="needs_input",
                note="Where do you see yourself in 5 years is not in your canned answers.",
            )
        )
    )
    record = answer_question(conn, job_id, "Where do you see yourself in 5 years?", client=client)
    assert record.source == "needs_input"
    assert record.answer is None
    assets = repo.list_generated_assets(conn, job_id)
    assert assets[0]["content"] == record.note


def test_answer_question_rejects_empty_question(conn):
    job_id = _job(conn)
    with pytest.raises(ValueError):
        answer_question(conn, job_id, "   ", client=FakeLLMClient(make_response(None)))


def test_answer_question_unknown_job(conn):
    with pytest.raises(ValueError):
        answer_question(conn, 999, "Q?", client=FakeLLMClient(make_response(None)))
