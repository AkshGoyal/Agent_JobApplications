"""generated_asset repo functions: insert + list roundtrip."""

from db import repo


def _job(conn) -> int:
    company_id = repo.get_or_create_company(conn, "Acme AI")
    return repo.insert_job(
        conn,
        company_id=company_id,
        title="AI Engineer",
        location="Bengaluru",
        remote_type="hybrid",
        source="manual_paste",
        source_url="https://example.com/job/1",
        description_text="JD text",
        posted_at=None,
        dedup_hash="hash-asset-1",
    )


def test_insert_and_list_generated_assets(conn):
    job_id = _job(conn)
    cv_id = repo.insert_generated_asset(conn, job_id, "cv_bullets", "hash-a", "# CV")
    letter_id = repo.insert_generated_asset(
        conn, job_id, "cover_letter", "hash-a", "Dear hiring manager..."
    )
    assert cv_id != letter_id

    rows = repo.list_generated_assets(conn, job_id)
    assert {r["kind"] for r in rows} == {"cv_bullets", "cover_letter"}
    assert all(r["job_id"] == job_id for r in rows)


def test_list_generated_assets_empty_for_unknown_job(conn):
    assert repo.list_generated_assets(conn, 999) == []


def test_generated_asset_kind_check_constraint(conn):
    import sqlite3

    import pytest

    job_id = _job(conn)
    with pytest.raises(sqlite3.IntegrityError):
        repo.insert_generated_asset(conn, job_id, "not_a_real_kind", "h", "x")
