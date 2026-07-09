"""DB layer tests: migration idempotence and insert/query roundtrips."""

import sqlite3

import pytest

from db import database, repo


@pytest.fixture
def conn(tmp_path):
    c = database.connect(tmp_path / "test.db")
    yield c
    c.close()


def test_migration_is_idempotent(tmp_path):
    conn = sqlite3.connect(tmp_path / "test.db")
    conn.row_factory = sqlite3.Row
    first = database.migrate(conn)
    assert "0001_initial.sql" in first
    second = database.migrate(conn)
    assert second == []  # nothing re-applied


def test_expected_tables_exist(conn):
    tables = {
        row["name"]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {"company", "job", "generated_asset", "person", "outreach",
            "schema_version"} <= tables


def _insert_sample_job(conn, url="https://example.com/job/1", dedup="hash-1"):
    company_id = repo.get_or_create_company(conn, "Acme AI")
    return repo.insert_job(
        conn,
        company_id=company_id,
        title="AI Engineer",
        location="Bangalore",
        remote_type="hybrid",
        source="manual_paste",
        source_url=url,
        description_text="We are hiring an AI Engineer...",
        posted_at=None,
        dedup_hash=dedup,
    )


def test_company_lookup_is_case_insensitive(conn):
    first = repo.get_or_create_company(conn, "Acme AI")
    second = repo.get_or_create_company(conn, "ACME ai")
    assert first == second


def test_insert_and_get_job_roundtrip(conn):
    job_id = _insert_sample_job(conn)
    job = repo.get_job(conn, job_id)
    assert job["title"] == "AI Engineer"
    assert job["company_name"] == "Acme AI"
    assert job["status"] == "discovered"
    assert job["relevance_score"] is None


def test_find_job_by_dedup_matches_hash_and_url(conn):
    _insert_sample_job(conn)
    by_hash = repo.find_job_by_dedup(conn, "hash-1", "https://other.example")
    by_url = repo.find_job_by_dedup(conn, "other-hash", "https://example.com/job/1")
    assert by_hash is not None and by_url is not None
    assert repo.find_job_by_dedup(conn, "no-match", "https://no.match") is None


def test_set_ranking_updates_score_and_status(conn):
    job_id = _insert_sample_job(conn)
    repo.set_ranking(conn, job_id, 85, "Strong RAG experience match.")
    job = repo.get_job(conn, job_id)
    assert job["relevance_score"] == 85
    assert job["status"] == "ranked"


def test_list_jobs_filters_by_min_score_and_status(conn):
    a = _insert_sample_job(conn, url="https://e.com/a", dedup="a")
    b = _insert_sample_job(conn, url="https://e.com/b", dedup="b")
    repo.set_ranking(conn, a, 90, "Great fit.")
    repo.set_ranking(conn, b, 40, "Weak fit.")
    assert [r["id"] for r in repo.list_jobs(conn, min_score=70)] == [a]
    assert repo.list_jobs(conn, status="discovered") == []
    assert len(repo.list_jobs(conn, status="ranked")) == 2
