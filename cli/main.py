"""Job search assistant CLI.

    python -m cli.main ingest paste --url <URL> [--file jd.txt] [--rank]
    python -m cli.main ingest gmail [--days 7] [--rank]
    python -m cli.main rank [JOB_ID]
    python -m cli.main list [--min-score 70] [--status discovered]
    python -m cli.main show <JOB_ID>
    python -m cli.main status <JOB_ID> <NEW_STATUS>
    python -m cli.main status-report
    python -m cli.main tailor <JOB_ID>
    python -m cli.main answer <JOB_ID> "question text"
    python -m cli.main deadline <JOB_ID> <YYYY-MM-DD|clear>
    python -m cli.main opportunities scan [--focus "text"]
    python -m cli.main opportunities list [--status new]
    python -m cli.main opportunities status <ID> <new|saved|dismissed>
"""

import sys
from pathlib import Path
from typing import Optional

import typer

import config
import llm
from db import database, repo
from pipeline import answer as answer_pipeline
from pipeline import ingest as ingest_pipeline
from pipeline import opportunities as opportunities_pipeline
from pipeline import rank as rank_pipeline
from pipeline import tailor as tailor_pipeline
from sources import gmail_alerts

app = typer.Typer(no_args_is_help=True, help="Personal job search assistant (Phase 1).")
ingest_app = typer.Typer(help="Capture jobs into the database.")
app.add_typer(ingest_app, name="ingest")
opportunities_app = typer.Typer(help="Market-intelligence scan: startups, AI news, learning gaps.")
app.add_typer(opportunities_app, name="opportunities")


def _connect():
    return database.connect()


def _require_api_key() -> None:
    if not config.api_key_present():
        typer.echo(
            f"error: {config.API_KEY_ENV_VAR} is not set — export it first "
            "(the key is never stored anywhere).",
            err=True,
        )
        raise typer.Exit(1)


def _print_ranked(ranked: rank_pipeline.RankedJob) -> None:
    typer.echo(f"  score:     {ranked.score}")
    typer.echo(f"  rationale: {ranked.rationale}")


@ingest_app.command("paste")
def ingest_paste(
    url: str = typer.Option(..., "--url", help="The job posting URL."),
    file: Optional[Path] = typer.Option(
        None, "--file", exists=True, readable=True, dir_okay=False,
        help="Read the JD from a file instead of stdin.",
    ),
    rank: bool = typer.Option(
        False, "--rank", help="Rank the job right after storing it."
    ),
):
    """Ingest one manually pasted job description (from --file or stdin)."""
    _require_api_key()
    if file is not None:
        jd_text = file.read_text()
    else:
        if sys.stdin.isatty():
            typer.echo(
                "Paste the job description below, then press Ctrl-D on an empty line:",
                err=True,
            )
        jd_text = sys.stdin.read()

    conn = _connect()
    try:
        result = ingest_pipeline.ingest_pasted_job(conn, url, jd_text)
    except (ValueError, llm.LLMError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1)

    posting = result.posting
    if result.duplicate:
        typer.echo(
            f"Duplicate — already stored as job {result.job_id} "
            f"({posting.company_name} — {posting.title}). Nothing inserted."
        )
        raise typer.Exit(0)

    typer.echo(f"Stored job {result.job_id}:")
    typer.echo(f"  company:     {posting.company_name}")
    typer.echo(f"  title:       {posting.title}")
    typer.echo(f"  location:    {posting.location or '-'}")
    typer.echo(f"  remote_type: {posting.remote_type}")
    typer.echo(f"  posted_at:   {posting.posted_at or '-'}")

    if rank:
        try:
            ranked = rank_pipeline.rank_job(conn, result.job_id)
        except llm.LLMError as exc:
            typer.echo(
                f"stored, but ranking failed ({exc}) — run "
                f"`python -m cli.main rank {result.job_id}` to retry.",
                err=True,
            )
            raise typer.Exit(1)
        typer.echo("Ranked:")
        _print_ranked(ranked)


@ingest_app.command("gmail")
def ingest_gmail(
    days: int = typer.Option(7, "--days", help="Look back this many days of alert emails."),
    rank: bool = typer.Option(False, "--rank", help="Rank each new job right after storing."),
):
    """Pull LinkedIn job-alert emails from your Gmail inbox (read-only IMAP)."""
    _require_api_key()
    if not config.gmail_configured():
        typer.echo(
            f"error: Gmail is not configured — export {config.GMAIL_ADDRESS_ENV_VAR} "
            f"and {config.GMAIL_APP_PASSWORD_ENV_VAR} first (see CLAUDE.md).",
            err=True,
        )
        raise typer.Exit(1)

    conn = _connect()
    try:
        result = gmail_alerts.ingest_alerts(conn, days=days)
    except (ValueError, llm.LLMError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1)

    typer.echo(
        f"Scanned {result.emails_scanned} alert email(s): "
        f"{len(result.new_job_ids)} new job(s), {result.duplicates} duplicate(s)."
    )
    for job_id in result.new_job_ids:
        job = repo.get_job(conn, job_id)
        typer.echo(f"  job {job_id}: {job['company_name']} — {job['title']}")

    if rank and result.new_job_ids:
        typer.echo("Ranking new jobs (snippet-based — paste full JD for accuracy):")
        for job_id in result.new_job_ids:
            try:
                ranked = rank_pipeline.rank_job(conn, job_id)
                typer.echo(f"  job {job_id}: score {ranked.score}")
            except llm.LLMError as exc:
                typer.echo(f"  job {job_id}: ranking failed ({exc})", err=True)


@app.command()
def rank(
    job_id: Optional[int] = typer.Argument(
        None, help="Job to rank; omit to rank every 'discovered' job."
    ),
):
    """LLM-rank stored jobs against the profile (score 0-100 + rationale)."""
    _require_api_key()
    conn = _connect()
    try:
        if job_id is not None:
            ranked_jobs = [rank_pipeline.rank_job(conn, job_id)]
        else:
            ranked_jobs = rank_pipeline.rank_discovered(conn)
    except (ValueError, llm.LLMError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1)

    if not ranked_jobs:
        typer.echo("Nothing to rank — no jobs in status 'discovered'.")
        return
    for ranked in ranked_jobs:
        typer.echo(f"Job {ranked.job_id}:")
        _print_ranked(ranked)


@app.command("list")
def list_jobs(
    min_score: Optional[int] = typer.Option(
        None, "--min-score", help="Only jobs with relevance_score >= N."
    ),
    status: Optional[str] = typer.Option(
        None, "--status", help="Only jobs in this status."
    ),
):
    """List stored jobs (highest score first)."""
    rows = repo.list_jobs(_connect(), min_score=min_score, status=status)
    if not rows:
        typer.echo("No jobs match.")
        return
    fmt = "{:>4}  {:>5}  {:<24}  {:<34}  {:<20}  {:<12}"
    typer.echo(fmt.format("id", "score", "company", "title", "location", "status"))
    for row in rows:
        typer.echo(
            fmt.format(
                row["id"],
                row["relevance_score"] if row["relevance_score"] is not None else "-",
                (row["company_name"] or "")[:24],
                (row["title"] or "")[:34],
                (row["location"] or "-")[:20],
                row["status"],
            )
        )


@app.command()
def status(
    job_id: int = typer.Argument(..., help="Job id (see `list`)."),
    new_status: str = typer.Argument(
        ..., help="One of: " + ", ".join(repo.STATUS_LIFECYCLE)
    ),
):
    """Record a status transition (e.g. `status 3 applied`). Always manual."""
    conn = _connect()
    try:
        repo.set_status(conn, job_id, new_status)
    except ValueError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1)
    job = repo.get_job(conn, job_id)
    typer.echo(
        f"Job {job_id} ({job['company_name']} — {job['title']}) → {new_status}"
    )


@app.command()
def deadline(
    job_id: int = typer.Argument(..., help="Job id (see `list`)."),
    value: str = typer.Argument(..., help="YYYY-MM-DD, or 'clear' to remove it."),
):
    """Set or clear a job's application deadline."""
    conn = _connect()
    new_deadline = None if value.lower() == "clear" else value
    try:
        repo.set_deadline(conn, job_id, new_deadline)
    except ValueError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1)
    job = repo.get_job(conn, job_id)
    typer.echo(
        f"Job {job_id} ({job['company_name']} — {job['title']}) "
        f"deadline → {job['application_deadline'] or '-'}"
    )


@app.command("status-report")
def status_report():
    """Show the funnel: how many jobs sit in each lifecycle stage."""
    counts = repo.status_counts(_connect())
    total = sum(counts.values())
    if total == 0:
        typer.echo("No jobs stored yet.")
        return
    for stage in repo.STATUS_LIFECYCLE:
        n = counts.get(stage, 0)
        bar = "#" * n
        typer.echo(f"{stage:<16} {n:>4}  {bar}")
    typer.echo(f"{'total':<16} {total:>4}")


@app.command()
def tailor(job_id: int = typer.Argument(..., help="Job id (see `list`).")):
    """Generate CV bullet suggestions + a cover letter draft for a job."""
    _require_api_key()
    conn = _connect()
    try:
        result = tailor_pipeline.tailor_job(conn, job_id)
    except (ValueError, llm.LLMError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1)

    typer.echo(f"Job {result.job_id} — materials generated (status: materials_ready)")
    typer.echo(f"  CV bullets:    {result.cv_path}")
    typer.echo(f"  Cover letter:  {result.cover_letter_path}")
    if result.warnings:
        typer.echo("")
        typer.echo("Warnings (review before using):")
        for w in result.warnings:
            typer.echo(f"  - {w}")


@app.command()
def answer(
    job_id: int = typer.Argument(..., help="Job id (see `list`)."),
    question: str = typer.Argument(..., help="The application question to answer."),
):
    """Answer an application question, preferring canned answers over generation."""
    _require_api_key()
    conn = _connect()
    try:
        record = answer_pipeline.answer_question(conn, job_id, question)
    except (ValueError, llm.LLMError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1)

    if record.source == "needs_input":
        typer.echo(f"needs your input: {record.note}")
    else:
        typer.echo(f"[{record.source}] {record.answer}")


@app.command()
def show(job_id: int = typer.Argument(..., help="Job id (see `list`).")):
    """Show a job's full record, including the ranking rationale."""
    job = repo.get_job(_connect(), job_id)
    if job is None:
        typer.echo(f"error: no job with id {job_id}", err=True)
        raise typer.Exit(1)

    typer.echo(f"Job {job['id']}: {job['company_name']} — {job['title']}")
    typer.echo(f"  status:        {job['status']} (since {job['status_updated_at']})")
    typer.echo(f"  deadline:      {job['application_deadline'] or '-'}")
    typer.echo(f"  location:      {job['location'] or '-'}")
    typer.echo(f"  remote_type:   {job['remote_type']}")
    typer.echo(f"  source:        {job['source']}")
    typer.echo(f"  url:           {job['source_url']}")
    typer.echo(f"  posted_at:     {job['posted_at'] or '-'}")
    typer.echo(f"  discovered_at: {job['discovered_at']}")
    typer.echo(f"  score:         {job['relevance_score'] if job['relevance_score'] is not None else 'not ranked yet'}")
    if job["relevance_rationale"]:
        typer.echo(f"  rationale:     {job['relevance_rationale']}")
    typer.echo("")
    typer.echo("Description (verbatim):")
    text = job["description_text"]
    excerpt = text[:1500]
    typer.echo(excerpt)
    if len(text) > len(excerpt):
        typer.echo(f"[... {len(text) - len(excerpt)} more characters — stored in full]")


@opportunities_app.command("scan")
def opportunities_scan(
    focus: Optional[str] = typer.Option(
        None, "--focus", help="Steer the scan (e.g. 'quick commerce AI startups')."
    ),
):
    """Search-grounded scan for startups, AI developments, and learning gaps."""
    _require_api_key()
    conn = _connect()
    try:
        result = opportunities_pipeline.scan(conn, focus=focus)
    except llm.LLMError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1)

    typer.echo(result.overview)
    typer.echo(
        f"{len(result.new_ids)} new item(s), {result.duplicates} already seen. "
        f"Digest: {result.digest_path}"
    )


@opportunities_app.command("list")
def opportunities_list(
    status: Optional[str] = typer.Option(None, "--status", help="Filter by status."),
):
    """List stored opportunities (newest first)."""
    rows = repo.list_opportunities(_connect(), status=status)
    if not rows:
        typer.echo("No opportunities match.")
        return
    for row in rows:
        typer.echo(f"[{row['id']}] ({row['kind']}, {row['status']}) {row['title']}")
        typer.echo(f"    {row['summary']}")
        if row["source_url"]:
            typer.echo(f"    source: {row['source_url']}")


@opportunities_app.command("status")
def opportunities_status(
    opportunity_id: int = typer.Argument(..., help="Opportunity id (see `opportunities list`)."),
    new_status: str = typer.Argument(..., help="One of: " + ", ".join(repo.OPPORTUNITY_STATUSES)),
):
    """Mark an opportunity as new, saved, or dismissed."""
    conn = _connect()
    try:
        repo.set_opportunity_status(conn, opportunity_id, new_status)
    except ValueError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1)
    typer.echo(f"Opportunity {opportunity_id} -> {new_status}")


if __name__ == "__main__":
    app()
