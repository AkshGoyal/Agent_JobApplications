"""Deduplication of job postings.

A job is a duplicate if it has the same normalized (company, title, location)
fingerprint — this catches the same role pasted from two different URLs. The
ingest step additionally checks for an exact source_url match.
"""

import hashlib


def dedup_hash(company: str, title: str, location: str | None) -> str:
    """Stable fingerprint over normalized company|title|location."""
    parts = [
        (company or "").strip().lower(),
        (title or "").strip().lower(),
        (location or "").strip().lower(),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
