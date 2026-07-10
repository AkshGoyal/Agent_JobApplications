"""Normalization of extracted job fields.

Deterministic cleanup only — the raw description_text is never touched.
"""

import re
from dataclasses import replace

from sources.manual_paste import RawPosting

REMOTE_TYPES = {"onsite", "hybrid", "remote", "unknown"}

_REMOTE_ALIASES = {
    "on-site": "onsite",
    "on site": "onsite",
    "in-office": "onsite",
    "in office": "onsite",
    "wfh": "remote",
    "work from home": "remote",
}


def clean_text(value: str | None) -> str | None:
    """Strip and collapse internal whitespace; empty strings become None."""
    if value is None:
        return None
    cleaned = re.sub(r"\s+", " ", value).strip()
    return cleaned or None


def normalize_remote_type(value: str | None) -> str:
    """Map free-form remote-type text onto the schema's enum."""
    if not value:
        return "unknown"
    candidate = re.sub(r"\s+", " ", value).strip().lower()
    candidate = _REMOTE_ALIASES.get(candidate, candidate)
    return candidate if candidate in REMOTE_TYPES else "unknown"


def normalize(raw: RawPosting) -> RawPosting:
    """Return a cleaned copy of the posting (description_text stays verbatim)."""
    return replace(
        raw,
        company_name=clean_text(raw.company_name) or raw.company_name,
        title=clean_text(raw.title) or raw.title,
        location=clean_text(raw.location),
        remote_type=normalize_remote_type(raw.remote_type),
        posted_at=clean_text(raw.posted_at),
    )
