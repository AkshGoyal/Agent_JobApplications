"""Ingest pipeline: extract → normalize → dedup → store.

Storing never depends on ranking — a failed ranking call can never lose a
pasted JD (ranking is a separate step; see pipeline/rank.py).
"""

import sqlite3
from dataclasses import dataclass

from db import repo
from pipeline import dedup, normalize
from sources import manual_paste
from sources.manual_paste import RawPosting


@dataclass
class IngestResult:
    job_id: int
    duplicate: bool
    posting: RawPosting


def ingest_pasted_job(
    conn: sqlite3.Connection, url: str, jd_text: str, *, client=None
) -> IngestResult:
    """Ingest one manually pasted job. Returns the new job id, or the existing
    job id with ``duplicate=True`` when the posting is already stored."""
    if not url.strip():
        raise ValueError("a job URL is required")
    if not jd_text.strip():
        raise ValueError("the pasted job description is empty")

    raw = manual_paste.capture(url.strip(), jd_text, client=client)
    posting = normalize.normalize(raw)
    fingerprint = dedup.dedup_hash(posting.company_name, posting.title, posting.location)

    existing = repo.find_job_by_dedup(conn, fingerprint, posting.source_url)
    if existing is not None:
        return IngestResult(job_id=existing["id"], duplicate=True, posting=posting)

    company_id = repo.get_or_create_company(conn, posting.company_name)
    job_id = repo.insert_job(
        conn,
        company_id=company_id,
        title=posting.title,
        location=posting.location,
        remote_type=posting.remote_type,
        source=posting.source,
        source_url=posting.source_url,
        description_text=posting.description_text,
        posted_at=posting.posted_at,
        dedup_hash=fingerprint,
    )
    return IngestResult(job_id=job_id, duplicate=False, posting=posting)
