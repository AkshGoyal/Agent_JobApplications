"""Manual paste source — Phase 1's only job source.

The user copies a job description from LinkedIn (or anywhere) themselves and
pastes it into the CLI. We NEVER scrape or log into LinkedIn. The LLM's only
job here is extracting structured fields; the pasted text itself is stored
verbatim.
"""

from dataclasses import dataclass
from datetime import date
from typing import Literal

from pydantic import BaseModel

import llm

SOURCE_NAME = "manual_paste"


class ExtractedJobFields(BaseModel):
    """Structured-output contract for the extract_job prompt."""

    company_name: str
    title: str
    location: str | None = None
    remote_type: Literal["onsite", "hybrid", "remote", "unknown"] = "unknown"
    posted_at: str | None = None  # ISO date YYYY-MM-DD


@dataclass
class RawPosting:
    """A job posting as captured from a source, before normalization."""

    source: str
    source_url: str
    description_text: str  # verbatim pasted JD — never rewritten
    company_name: str
    title: str
    location: str | None
    remote_type: str
    posted_at: str | None


def capture(url: str, jd_text: str, *, client=None) -> RawPosting:
    """Build a RawPosting from a URL + pasted JD via LLM field extraction."""
    fields = llm.call(
        "extract_job",
        ExtractedJobFields,
        client=client,
        url=url,
        jd_text=jd_text,
        today=date.today().isoformat(),
    )
    return RawPosting(
        source=SOURCE_NAME,
        source_url=url,
        description_text=jd_text,
        company_name=fields.company_name,
        title=fields.title,
        location=fields.location,
        remote_type=fields.remote_type,
        posted_at=fields.posted_at,
    )
