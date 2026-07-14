"""Contract tests for tailor_job — mocked client, no live API.

Grounding is enforced at the schema level (entry_id/section are Literal[...]
built from cv_canonical_structure.yaml), so the strongest test of "never
invents a section/entry" is that constructing an invalid suggestion raises
ValidationError before it could ever reach the LLM response path.
"""

import pytest
from pydantic import ValidationError

import llm
from db import repo
from pipeline import tailor
from tests.conftest import FakeLLMClient, make_response
from tests.tailor_test_helpers import valid_cover_letter_result, valid_cv_result


def _job(conn) -> int:
    company_id = repo.get_or_create_company(conn, "Acme AI Labs")
    return repo.insert_job(
        conn,
        company_id=company_id,
        title="AI Engineer",
        location="Bengaluru",
        remote_type="hybrid",
        source="manual_paste",
        source_url="https://e.com/tailor-1",
        description_text="We build production RAG systems using hybrid retrieval.",
        posted_at=None,
        dedup_hash="tailor-hash-1",
    )


def test_entry_id_is_schema_constrained_to_known_entries():
    """The core grounding guarantee: an invented entry is impossible to
    construct, not merely discouraged by prompt wording."""
    _CVTailoringResult, CVSuggestion = tailor.build_cv_models()
    with pytest.raises(ValidationError):
        CVSuggestion(
            entry_id="an_entry_that_does_not_exist",
            section="Professional Experience",
            original_bullet="x",
            suggested_bullet="y",
            rationale="z",
        )


def test_section_is_also_schema_constrained():
    _CVTailoringResult, CVSuggestion = tailor.build_cv_models()
    with pytest.raises(ValidationError):
        CVSuggestion(
            entry_id="aspect_ratio_analyst",
            section="Made Up Section",
            original_bullet="x",
            suggested_bullet="y",
            rationale="z",
        )


def test_tailor_job_writes_files_asset_rows_and_advances_status(conn, tmp_path, monkeypatch):
    import config
    monkeypatch.setattr(config, "OUTPUT_DIR", tmp_path / "output")

    job_id = _job(conn)
    client = FakeLLMClient(
        make_response(valid_cv_result()),
        make_response(valid_cover_letter_result()),
    )

    result = tailor.tailor_job(conn, job_id, client=client)

    # Both tailor calls use the tailor-specific model + raised token cap
    # (generation needs headroom — a 2048 cap truncates long responses).
    import config as config_module
    for call_kwargs in client.calls:
        assert call_kwargs["model"] == config_module.MODEL_TAILOR
        assert call_kwargs["config"].max_output_tokens == config_module.MAX_TOKENS_TAILOR

    assert result.warnings == []
    assert result.cv_path.exists()
    assert result.cover_letter_path.exists()
    assert "aspect_ratio_analyst" not in result.cv_path.read_text()  # renders entry names, not ids
    assert "Aspect Ratio" in result.cv_path.read_text()

    assets = repo.list_generated_assets(conn, job_id)
    assert {a["kind"] for a in assets} == {"cv_bullets", "cover_letter"}

    job = repo.get_job(conn, job_id)
    assert job["status"] == "materials_ready"


def test_cover_letter_signature_is_deterministic_not_llm_written(conn, tmp_path, monkeypatch):
    import config
    monkeypatch.setattr(config, "OUTPUT_DIR", tmp_path / "output")
    import profile_kb

    job_id = _job(conn)
    client = FakeLLMClient(
        make_response(valid_cv_result()),
        make_response(valid_cover_letter_result()),
    )
    result = tailor.tailor_job(conn, job_id, client=client)

    letter = result.cover_letter_path.read_text()
    name = profile_kb.load_facts()["identity"]["name"]
    assert f"Sincerely,\n{name}" in letter
    # The mocked cover-letter body never contains the candidate's real name —
    # confirms the signature line was appended by code, not the LLM.
    assert name not in valid_cover_letter_result().body


def test_bullet_drift_produces_a_warning_but_still_succeeds(conn, tmp_path, monkeypatch):
    import config
    monkeypatch.setattr(config, "OUTPUT_DIR", tmp_path / "output")

    job_id = _job(conn)
    cv_result, CVSuggestion = tailor.build_cv_models()
    drifted = cv_result(
        suggestions=[
            CVSuggestion(
                entry_id="aspect_ratio_analyst",
                section="Professional Experience",
                original_bullet="This text does not match any real bullet at all.",
                suggested_bullet="Something else entirely.",
                rationale="n/a",
            )
        ],
        notes=None,
    )
    client = FakeLLMClient(make_response(drifted), make_response(valid_cover_letter_result()))

    result = tailor.tailor_job(conn, job_id, client=client)
    assert len(result.warnings) == 1
    assert "aspect_ratio_analyst" in result.warnings[0]
    # Still succeeded — soft check only.
    job = repo.get_job(conn, job_id)
    assert job["status"] == "materials_ready"


def test_tailor_job_raises_and_writes_nothing_on_llm_failure(conn, tmp_path, monkeypatch):
    import config
    monkeypatch.setattr(config, "OUTPUT_DIR", tmp_path / "output")

    job_id = _job(conn)
    client = FakeLLMClient(make_response(None))  # unparseable
    with pytest.raises(llm.LLMError):
        tailor.tailor_job(conn, job_id, client=client)

    assert repo.list_generated_assets(conn, job_id) == []
    assert not (config.OUTPUT_DIR).exists()
    job = repo.get_job(conn, job_id)
    assert job["status"] == "discovered"


def test_tailor_job_unknown_job_id(conn):
    with pytest.raises(ValueError):
        tailor.tailor_job(conn, 999, client=FakeLLMClient(make_response(None)))
