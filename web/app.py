"""Local single-user web UI for the job search assistant.

A thin JSON layer over the exact same pipeline functions the CLI uses —
no logic lives here. Run with:

    python -m web.app          # http://localhost:8000

The UI never submits applications anywhere; status transitions are made by
the user clicking, mirroring the CLI's human-driven lifecycle rule.
"""

from contextlib import closing
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

import config
import llm
from db import database, repo
from pipeline import ingest as ingest_pipeline
from pipeline import rank as rank_pipeline

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Job Search Assistant")


class IngestRequest(BaseModel):
    url: str
    jd_text: str
    rank: bool = True


class StatusRequest(BaseModel):
    status: str


def _require_api_key() -> None:
    if not config.api_key_present():
        raise HTTPException(
            status_code=503,
            detail=f"{config.API_KEY_ENV_VAR} is not set — export it in the "
            "environment running the server, then retry.",
        )


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/jobs")
def api_list_jobs(min_score: int | None = None, status: str | None = None):
    with closing(database.connect()) as conn:
        return [dict(row) for row in
                repo.list_jobs(conn, min_score=min_score, status=status)]


@app.get("/api/jobs/{job_id}")
def api_get_job(job_id: int):
    with closing(database.connect()) as conn:
        job = repo.get_job(conn, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"no job with id {job_id}")
    return dict(job)


@app.post("/api/jobs")
def api_add_job(req: IngestRequest):
    """Ingest a pasted JD. Stores first, ranks after — a ranking failure never
    loses the paste; it comes back as a warning instead of an error."""
    _require_api_key()
    with closing(database.connect()) as conn:
        try:
            result = ingest_pipeline.ingest_pasted_job(conn, req.url, req.jd_text)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except llm.LLMError as exc:
            raise HTTPException(status_code=502, detail=str(exc))

        payload = {
            "job_id": result.job_id,
            "duplicate": result.duplicate,
            "warning": None,
        }
        if req.rank and not result.duplicate:
            try:
                rank_pipeline.rank_job(conn, result.job_id)
            except llm.LLMError as exc:
                payload["warning"] = (
                    f"stored, but ranking failed ({exc}) — use 'Rank now' to retry"
                )
        payload["job"] = dict(repo.get_job(conn, result.job_id))
    return payload


@app.post("/api/jobs/{job_id}/rank")
def api_rank_job(job_id: int):
    _require_api_key()
    with closing(database.connect()) as conn:
        try:
            rank_pipeline.rank_job(conn, job_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except llm.LLMError as exc:
            raise HTTPException(status_code=502, detail=str(exc))
        return dict(repo.get_job(conn, job_id))


@app.post("/api/jobs/{job_id}/status")
def api_set_status(job_id: int, req: StatusRequest):
    with closing(database.connect()) as conn:
        try:
            repo.set_status(conn, job_id, req.status)
        except ValueError as exc:
            code = 404 if "no job" in str(exc) else 400
            raise HTTPException(status_code=code, detail=str(exc))
        return dict(repo.get_job(conn, job_id))


@app.get("/api/report")
def api_report():
    with closing(database.connect()) as conn:
        counts = repo.status_counts(conn)
    return {
        "lifecycle": list(repo.STATUS_LIFECYCLE),
        "counts": counts,
        "total": sum(counts.values()),
    }


def main() -> None:
    uvicorn.run("web.app:app", host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
