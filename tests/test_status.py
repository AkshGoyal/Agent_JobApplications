"""Status tracking: manual lifecycle transitions and the funnel report."""

import pytest

from db import repo


def _job(conn, n: int) -> int:
    company_id = repo.get_or_create_company(conn, "Acme AI")
    return repo.insert_job(
        conn,
        company_id=company_id,
        title=f"Role {n}",
        location="Bengaluru",
        remote_type="hybrid",
        source="manual_paste",
        source_url=f"https://example.com/job/{n}",
        description_text="JD text",
        posted_at=None,
        dedup_hash=f"hash-{n}",
    )


def test_lifecycle_matches_schema_check_constraint(conn):
    # Every status in STATUS_LIFECYCLE must be writable — if the schema CHECK
    # and the Python tuple drift apart, this raises IntegrityError.
    job_id = _job(conn, 1)
    for stage in repo.STATUS_LIFECYCLE:
        repo.set_status(conn, job_id, stage)
        assert repo.get_job(conn, job_id)["status"] == stage


def test_set_status_updates_timestamp(conn):
    job_id = _job(conn, 1)
    before = repo.get_job(conn, job_id)["status_updated_at"]
    repo.set_status(conn, job_id, "applied")
    job = repo.get_job(conn, job_id)
    assert job["status"] == "applied"
    assert job["status_updated_at"] >= before


def test_set_status_rejects_unknown_status(conn):
    job_id = _job(conn, 1)
    with pytest.raises(ValueError, match="unknown status"):
        repo.set_status(conn, job_id, "ghosted")
    assert repo.get_job(conn, job_id)["status"] == "discovered"


def test_set_status_rejects_unknown_job(conn):
    with pytest.raises(ValueError, match="no job with id"):
        repo.set_status(conn, 999, "applied")


def test_status_counts_funnel(conn):
    a, b, c = _job(conn, 1), _job(conn, 2), _job(conn, 3)
    repo.set_status(conn, a, "applied")
    repo.set_status(conn, b, "applied")
    repo.set_status(conn, c, "interview")
    assert repo.status_counts(conn) == {"applied": 2, "interview": 1}


def test_set_deadline_sets_and_clears(conn):
    job_id = _job(conn, 1)
    repo.set_deadline(conn, job_id, "2026-08-01")
    assert repo.get_job(conn, job_id)["application_deadline"] == "2026-08-01"
    repo.set_deadline(conn, job_id, None)
    assert repo.get_job(conn, job_id)["application_deadline"] is None


def test_set_deadline_rejects_invalid_date(conn):
    job_id = _job(conn, 1)
    with pytest.raises(ValueError, match="invalid deadline"):
        repo.set_deadline(conn, job_id, "not-a-date")
    with pytest.raises(ValueError, match="invalid deadline"):
        repo.set_deadline(conn, job_id, "08/01/2026")


def test_set_deadline_rejects_unknown_job(conn):
    with pytest.raises(ValueError, match="no job with id"):
        repo.set_deadline(conn, 999, "2026-08-01")
