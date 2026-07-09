"""Repository functions — all SQL for company and job lives here."""

import sqlite3


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
                      job.title, job.location, job.status
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
