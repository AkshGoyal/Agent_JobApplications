"""Repository functions — all SQL for company and job lives here."""

import sqlite3
from datetime import date

# The job status lifecycle, in funnel order. Mirrors the CHECK constraint in
# db/migrations/0001_initial.sql — keep the two in sync.
STATUS_LIFECYCLE = (
    "discovered",
    "ranked",
    "shortlisted",
    "materials_ready",
    "applied",
    "in_process",
    "interview",
    "offer",
    "rejected",
    "dropped",
)


# --- company ----------------------------------------------------------------

def get_or_create_company(conn: sqlite3.Connection, name: str) -> int:
    """Return the id of the company with this name (case-insensitive), creating it if needed."""
    row = conn.execute(
        "SELECT id FROM company WHERE name = ? COLLATE NOCASE", (name,)
    ).fetchone()
    if row:
        return row["id"]
    cur = conn.execute("INSERT INTO company (name) VALUES (?)", (name,))
    conn.commit()
    return cur.lastrowid


# --- job --------------------------------------------------------------------

def find_job_by_dedup(
    conn: sqlite3.Connection, dedup_hash: str, source_url: str
) -> sqlite3.Row | None:
    """Return an existing job matching either the dedup hash or the exact URL."""
    return conn.execute(
        "SELECT * FROM job WHERE dedup_hash = ? OR source_url = ? LIMIT 1",
        (dedup_hash, source_url),
    ).fetchone()


def insert_job(
    conn: sqlite3.Connection,
    *,
    company_id: int,
    title: str,
    location: str | None,
    remote_type: str,
    source: str,
    source_url: str,
    description_text: str,
    posted_at: str | None,
    dedup_hash: str,
) -> int:
    cur = conn.execute(
        """INSERT INTO job (company_id, title, location, remote_type, source,
                            source_url, description_text, posted_at, dedup_hash)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (company_id, title, location, remote_type, source,
         source_url, description_text, posted_at, dedup_hash),
    )
    conn.commit()
    return cur.lastrowid


def get_job(conn: sqlite3.Connection, job_id: int) -> sqlite3.Row | None:
    return conn.execute(
        """SELECT job.*, company.name AS company_name
           FROM job JOIN company ON company.id = job.company_id
           WHERE job.id = ?""",
        (job_id,),
    ).fetchone()


def list_jobs(
    conn: sqlite3.Connection,
    *,
    min_score: int | None = None,
    status: str | None = None,
) -> list[sqlite3.Row]:
    query = """SELECT job.id, job.relevance_score, company.name AS company_name,
                      job.title, job.location, job.status, job.application_deadline
               FROM job JOIN company ON company.id = job.company_id"""
    clauses, params = [], []
    if min_score is not None:
        clauses.append("job.relevance_score >= ?")
        params.append(min_score)
    if status is not None:
        clauses.append("job.status = ?")
        params.append(status)
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY job.relevance_score DESC NULLS LAST, job.id"
    return conn.execute(query, params).fetchall()


def jobs_with_status(conn: sqlite3.Connection, status: str) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT job.*, company.name AS company_name
           FROM job JOIN company ON company.id = job.company_id
           WHERE job.status = ? ORDER BY job.id""",
        (status,),
    ).fetchall()


def set_status(conn: sqlite3.Connection, job_id: int, status: str) -> None:
    """Record a human-driven status transition (e.g. applied, interview).

    Transitions to 'applied' and beyond are always made by the user — never
    automatically (see PROJECT_SPEC.md).
    """
    if status not in STATUS_LIFECYCLE:
        raise ValueError(
            f"unknown status '{status}' — must be one of: "
            + ", ".join(STATUS_LIFECYCLE)
        )
    cur = conn.execute(
        """UPDATE job SET status = ?, status_updated_at = datetime('now')
           WHERE id = ?""",
        (status, job_id),
    )
    if cur.rowcount == 0:
        raise ValueError(f"no job with id {job_id}")
    conn.commit()


def set_deadline(conn: sqlite3.Connection, job_id: int, deadline: str | None) -> None:
    """Set or clear a job's application deadline. ``deadline`` must be an ISO
    date string (YYYY-MM-DD) or None to clear it."""
    if deadline is not None:
        try:
            date.fromisoformat(deadline)
        except ValueError:
            raise ValueError(f"invalid deadline '{deadline}' — expected YYYY-MM-DD")
    cur = conn.execute(
        "UPDATE job SET application_deadline = ? WHERE id = ?", (deadline, job_id)
    )
    if cur.rowcount == 0:
        raise ValueError(f"no job with id {job_id}")
    conn.commit()


def status_counts(conn: sqlite3.Connection) -> dict[str, int]:
    """Jobs per status, for the funnel report. Only non-empty statuses appear."""
    rows = conn.execute("SELECT status, COUNT(*) AS n FROM job GROUP BY status")
    return {row["status"]: row["n"] for row in rows}


# --- generated_asset ---------------------------------------------------------

def insert_generated_asset(
    conn: sqlite3.Connection,
    job_id: int,
    kind: str,
    prompt_context_hash: str,
    content: str,
) -> int:
    """Log a generated CV/cover-letter/answer draft. `kind` must match the
    table's CHECK constraint: 'cv_bullets', 'cover_letter', 'form_answer'."""
    cur = conn.execute(
        """INSERT INTO generated_asset (job_id, kind, prompt_context_hash, content)
           VALUES (?, ?, ?, ?)""",
        (job_id, kind, prompt_context_hash, content),
    )
    conn.commit()
    return cur.lastrowid


def list_generated_assets(conn: sqlite3.Connection, job_id: int) -> list[sqlite3.Row]:
    """All generated assets for a job, newest first."""
    return conn.execute(
        """SELECT * FROM generated_asset WHERE job_id = ?
           ORDER BY created_at DESC, id DESC""",
        (job_id,),
    ).fetchall()


def set_ranking(
    conn: sqlite3.Connection, job_id: int, score: int, rationale: str
) -> None:
    """Record a relevance ranking and advance status discovered → ranked."""
    conn.execute(
        """UPDATE job
           SET relevance_score = ?, relevance_rationale = ?,
               status = 'ranked', status_updated_at = datetime('now')
           WHERE id = ?""",
        (score, rationale, job_id),
    )
    conn.commit()
