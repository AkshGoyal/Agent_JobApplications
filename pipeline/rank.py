"""Relevance ranking: score stored jobs against the profile knowledge base.

Ranking is a separate step from ingest — jobs are always stored first, so a
failed ranking call never loses data. Re-runnable: `rank <id>` on an already
ranked job simply overwrites the score.
"""

import sqlite3
from dataclasses import dataclass

from pydantic import BaseModel, Field

import config
import llm
import profile_kb
from db import repo


class RankingResult(BaseModel):
    """Structured-output contract for the rank_job prompt."""

    score: int = Field(ge=0, le=100)
    rationale: str


@dataclass
class RankedJob:
    job_id: int
    score: int
    rationale: str


def rank_job(conn: sqlite3.Connection, job_id: int, *, client=None) -> RankedJob:
    """Rank one stored job against the profile; persists score + rationale."""
    job = repo.get_job(conn, job_id)
    if job is None:
        raise ValueError(f"no job with id {job_id}")

    result = llm.call(
        "rank_job",
        RankingResult,
        client=client,
        model=config.MODEL_RANK,
        profile_context=profile_kb.ranking_context(),
        company=job["company_name"],
        title=job["title"],
        location=job["location"] or "not stated",
        remote_type=job["remote_type"],
        jd_text=job["description_text"],
    )
    # Belt-and-braces: Field constraints already validate, but clamp anyway
    # so a future schema loosening can't write out-of-range scores.
    score = max(0, min(100, result.score))
    repo.set_ranking(conn, job_id, score, result.rationale)
    return RankedJob(job_id=job_id, score=score, rationale=result.rationale)


def rank_discovered(conn: sqlite3.Connection, *, client=None) -> list[RankedJob]:
    """Rank every job still in status 'discovered'."""
    jobs = repo.jobs_with_status(conn, "discovered")
    return [rank_job(conn, job["id"], client=client) for job in jobs]
