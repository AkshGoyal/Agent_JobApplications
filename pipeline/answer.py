"""Phase 2 generation: answer_question(job, question).

Prefers profile/canned_answers.yaml over fresh generation, per the spec.
Defense in depth: the model is instructed to flag a blank canned field as
needs_input rather than guess, but we never *trust* that instruction alone —
code re-checks the actual value in canned_answers.yaml and overrides to
needs_input if the model claimed a field that is in fact blank.
"""

import hashlib
import sqlite3
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel

import config
import llm
import profile_kb
from db import repo


class AnswerResult(BaseModel):
    """Structured-output contract for the answer_question prompt."""

    source: Literal["canned", "generated", "needs_input"]
    canned_field: str | None = None
    answer: str | None = None
    note: str | None = None


@dataclass
class AnswerRecord:
    job_id: int
    source: str
    answer: str | None
    note: str | None


def _lookup_canned_field(canned: dict, field_path: str | None):
    """Resolve a dotted path like 'logistics.notice_period' against the
    loaded canned_answers.yaml. Returns None if the path doesn't resolve."""
    if not field_path:
        return None
    node = canned
    for part in field_path.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def _context_hash(job_id: int, question: str) -> str:
    return hashlib.sha256(f"{job_id}|{question}".encode()).hexdigest()


def answer_question(
    conn: sqlite3.Connection, job_id: int, question: str, *, client=None
) -> AnswerRecord:
    job = repo.get_job(conn, job_id)
    if job is None:
        raise ValueError(f"no job with id {job_id}")
    if not question.strip():
        raise ValueError("question is empty")

    result = llm.call(
        "answer_question",
        AnswerResult,
        client=client,
        model=config.MODEL_ANSWER,
        canned_context=profile_kb.canned_context(),
        profile_context=profile_kb.tailoring_context(),
        company=job["company_name"],
        title=job["title"],
        question=question,
    )

    source, answer, note = result.source, result.answer, result.note

    if source == "canned":
        canned = profile_kb.load_canned_answers()
        value = _lookup_canned_field(canned, result.canned_field)
        if value in (None, "", []):
            # The model claimed a canned field is usable — verify, don't trust.
            source = "needs_input"
            answer = None
            note = (
                f"model pointed at canned field '{result.canned_field}' but "
                "it is blank in canned_answers.yaml — fill it in there, or "
                "answer this one manually."
            )

    content = answer if answer is not None else (note or "needs input")
    repo.insert_generated_asset(
        conn, job_id, "form_answer", _context_hash(job_id, question), content
    )

    return AnswerRecord(job_id=job_id, source=source, answer=answer, note=note)
