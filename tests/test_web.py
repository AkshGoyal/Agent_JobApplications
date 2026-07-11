"""Web API tests — TestClient with the Gemini client mocked, fully offline."""

import pytest
from fastapi.testclient import TestClient

import config
import llm
from pipeline.answer import AnswerResult
from pipeline.rank import RankingResult
from sources.manual_paste import ExtractedJobFields
from tests.conftest import FakeLLMClient, make_response
from tests.tailor_test_helpers import valid_cover_letter_result, valid_cv_result
from web.app import app

FIELDS = ExtractedJobFields(
    company_name="Acme AI Labs",
    title="AI Engineer",
    location="Bengaluru, Karnataka, India",
    remote_type="hybrid",
    posted_at="2026-06-25",
)
RANKING = RankingResult(score=88, rationale="Strong RAG overlap.")


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "web.db")
    monkeypatch.setenv(config.API_KEY_ENV_VAR, "fake-key-for-tests")
    return TestClient(app)


def _mock_llm(monkeypatch, *responses):
    fake = FakeLLMClient(*responses)
    monkeypatch.setattr(llm, "get_client", lambda: fake)
    return fake


def _add_job(client, monkeypatch, rank=True, url="https://e.com/j/1"):
    _mock_llm(monkeypatch, make_response(FIELDS), make_response(RANKING))
    return client.post(
        "/api/jobs", json={"url": url, "jd_text": "We are hiring...", "rank": rank}
    )


def test_index_serves_html(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "Job Search Assistant" in res.text


def test_add_job_stores_and_ranks(client, monkeypatch):
    res = _add_job(client, monkeypatch)
    assert res.status_code == 200
    body = res.json()
    assert body["duplicate"] is False and body["warning"] is None
    assert body["job"]["company_name"] == "Acme AI Labs"
    assert body["job"]["relevance_score"] == 88
    assert body["job"]["status"] == "ranked"


def test_add_duplicate_reports_existing(client, monkeypatch):
    first = _add_job(client, monkeypatch).json()
    dup = _add_job(client, monkeypatch, url="https://other.example/x").json()
    assert dup["duplicate"] is True
    assert dup["job_id"] == first["job_id"]


def test_add_rejects_empty_jd(client, monkeypatch):
    _mock_llm(monkeypatch, make_response(FIELDS))
    res = client.post("/api/jobs", json={"url": "https://e.com", "jd_text": "  "})
    assert res.status_code == 400


def test_ranking_failure_still_stores_with_warning(client, monkeypatch):
    _mock_llm(monkeypatch, make_response(FIELDS), make_response(None))
    res = client.post(
        "/api/jobs", json={"url": "https://e.com/j/9", "jd_text": "JD", "rank": True}
    )
    body = res.json()
    assert res.status_code == 200
    assert "ranking failed" in body["warning"]
    assert body["job"]["status"] == "discovered"  # paste never lost


def test_missing_api_key_returns_503(client, monkeypatch):
    monkeypatch.delenv(config.API_KEY_ENV_VAR)
    res = client.post("/api/jobs", json={"url": "https://e.com", "jd_text": "JD"})
    assert res.status_code == 503
    assert config.API_KEY_ENV_VAR in res.json()["detail"]


def test_list_show_and_filters(client, monkeypatch):
    job_id = _add_job(client, monkeypatch).json()["job_id"]
    assert client.get("/api/jobs").json()[0]["id"] == job_id
    assert client.get("/api/jobs", params={"min_score": 90}).json() == []
    assert client.get(f"/api/jobs/{job_id}").json()["description_text"]
    assert client.get("/api/jobs/999").status_code == 404


def test_status_endpoint_and_report(client, monkeypatch):
    job_id = _add_job(client, monkeypatch).json()["job_id"]
    res = client.post(f"/api/jobs/{job_id}/status", json={"status": "applied"})
    assert res.status_code == 200 and res.json()["status"] == "applied"
    assert client.post(f"/api/jobs/{job_id}/status",
                       json={"status": "ghosted"}).status_code == 400
    assert client.post("/api/jobs/999/status",
                       json={"status": "applied"}).status_code == 404
    report = client.get("/api/report").json()
    assert report["counts"] == {"applied": 1} and report["total"] == 1


def test_rank_endpoint(client, monkeypatch):
    job_id = _add_job(client, monkeypatch, rank=False).json()["job_id"]
    _mock_llm(monkeypatch, make_response(RANKING))
    res = client.post(f"/api/jobs/{job_id}/rank")
    assert res.status_code == 200
    assert res.json()["relevance_score"] == 88
    assert client.post("/api/jobs/999/rank").status_code == 404


def test_tailor_endpoint(client, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "OUTPUT_DIR", tmp_path / "output")
    job_id = _add_job(client, monkeypatch, rank=False).json()["job_id"]
    _mock_llm(monkeypatch, make_response(valid_cv_result()), make_response(valid_cover_letter_result()))

    res = client.post(f"/api/jobs/{job_id}/tailor")
    assert res.status_code == 200
    body = res.json()
    assert "Aspect Ratio" in body["cv_markdown"]
    assert body["warnings"] == []
    assert body["job"]["status"] == "materials_ready"

    assert client.post("/api/jobs/999/tailor").status_code == 404


def test_answer_endpoint(client, monkeypatch):
    job_id = _add_job(client, monkeypatch, rank=False).json()["job_id"]
    _mock_llm(monkeypatch, make_response(AnswerResult(source="generated", answer="I built a RAG system.")))

    res = client.post(f"/api/jobs/{job_id}/answer", json={"question": "Tell us about a project."})
    assert res.status_code == 200
    body = res.json()
    assert body["source"] == "generated"
    assert "RAG" in body["answer"]

    assert client.post("/api/jobs/999/answer", json={"question": "Q?"}).status_code == 404


def test_assets_endpoint_lists_generated_materials(client, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "OUTPUT_DIR", tmp_path / "output")
    job_id = _add_job(client, monkeypatch, rank=False).json()["job_id"]

    assert client.get(f"/api/jobs/{job_id}/assets").json() == []

    _mock_llm(monkeypatch, make_response(valid_cv_result()), make_response(valid_cover_letter_result()))
    client.post(f"/api/jobs/{job_id}/tailor")

    assets = client.get(f"/api/jobs/{job_id}/assets").json()
    assert {a["kind"] for a in assets} == {"cv_bullets", "cover_letter"}
    assert client.get("/api/jobs/999/assets").status_code == 404
