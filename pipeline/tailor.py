"""Phase 2 generation: tailor(job) -> CV bullet suggestions + cover letter.

Grounding is enforced at the schema level, not post-hoc: the CV suggestion's
`entry_id` and `section` fields are Literal[...] types built from
profile/cv_canonical_structure.yaml at call time, so an invented entry is
schema-invalid — impossible, not merely discouraged by prompt wording.

Like rank_job, this is atomic on failure: nothing is written to disk or the
DB unless both LLM calls succeed.
"""

import difflib
import hashlib
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

import config
import llm
import profile_kb
from db import repo

_BULLET_DRIFT_THRESHOLD = 0.5  # difflib ratio below this -> soft warning


class CoverLetterResult(BaseModel):
    """Structured-output contract for the tailor_cover_letter prompt."""

    subject: str
    body: str
    facts_used: list[str]


@dataclass
class TailorResult:
    job_id: int
    cv_path: Path
    cover_letter_path: Path
    warnings: list[str] = field(default_factory=list)


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "job"


def build_cv_models() -> tuple[type[BaseModel], type[BaseModel]]:
    """Build (CVTailoringResult, CVSuggestion) fresh per call, constrained to
    whatever cv_canonical_structure.yaml currently contains — editing that
    file takes effect immediately, no code change needed. Public (not
    underscore-prefixed) so tests can construct valid/invalid instances
    directly to demonstrate the schema-level grounding guarantee.
    """
    entry_ids = profile_kb.cv_entry_ids()
    section_names = profile_kb.cv_section_names()

    class CVSuggestion(BaseModel):
        entry_id: Literal[*entry_ids]
        section: Literal[*section_names]
        original_bullet: str
        suggested_bullet: str
        rationale: str

    class CVTailoringResult(BaseModel):
        suggestions: list[CVSuggestion]
        notes: str | None = None

    return CVTailoringResult, CVSuggestion


def _context_hash(job: sqlite3.Row) -> str:
    """Changes if the job's JD or any profile input file changes — inspectable,
    same pattern as job.dedup_hash. No cache/skip logic built on this yet."""
    h = hashlib.sha256()
    h.update(str(job["id"]).encode())
    h.update(job["description_text"].encode())
    for filename in ("cv_canonical_structure.yaml", "narratives.md", "facts.yaml"):
        h.update((config.PROFILE_DIR / filename).read_bytes())
    return h.hexdigest()


def _check_bullet_drift(cv_result, cv_structure: dict) -> list[str]:
    """Soft check: does each suggestion's original_bullet closely match a
    known bullet for that entry? Bullet wording is inherently fuzzy (the LLM
    may lightly normalize whitespace/punctuation when echoing it back), so
    this only ever warns — entry_id/section grounding is already enforced by
    the schema itself.
    """
    known_bullets = {
        entry["id"]: entry["bullets"]
        for entries in cv_structure.values()
        for entry in entries
    }
    warnings = []
    for s in cv_result.suggestions:
        bullets = known_bullets.get(s.entry_id, [])
        best_ratio = max(
            (difflib.SequenceMatcher(None, s.original_bullet, b).ratio() for b in bullets),
            default=0.0,
        )
        if best_ratio < _BULLET_DRIFT_THRESHOLD:
            warnings.append(
                f"[{s.entry_id}] the 'original_bullet' text doesn't closely "
                f"match any known bullet for this entry — double-check "
                f'before using: "{s.suggested_bullet}"'
            )
    return warnings


def _render_cv_markdown(job: sqlite3.Row, cv_structure: dict, cv_result) -> str:
    by_entry: dict[str, list] = {}
    for s in cv_result.suggestions:
        by_entry.setdefault(s.entry_id, []).append(s)

    lines = [f"# CV bullet suggestions — {job['company_name']} — {job['title']}", ""]
    any_suggestions = False
    for section, entries in cv_structure.items():
        section_pairs = [(entry, s) for entry in entries for s in by_entry.get(entry["id"], [])]
        if not section_pairs:
            continue
        any_suggestions = True
        lines.append(f"## {section}")
        for entry, s in section_pairs:
            lines.append(f"### {entry['entry']}")
            lines.append(f"- **original:** {s.original_bullet}")
            lines.append(f"- **suggested:** {s.suggested_bullet}")
            lines.append(f"  _{s.rationale}_")
            lines.append("")
    if not any_suggestions:
        lines.append(
            "_No changes suggested — the existing bullets already read "
            "well for this job._"
        )
        lines.append("")
    if cv_result.notes:
        lines += ["## Notes", cv_result.notes, ""]
    return "\n".join(lines)


def _render_cover_letter_markdown(cover_result: CoverLetterResult) -> str:
    # The signature is deterministic, never LLM-written — the prompt is
    # explicitly told not to include a salutation/sign-off.
    name = profile_kb.load_facts().get("identity", {}).get("name", "")
    lines = [
        f"# {cover_result.subject}",
        "",
        "Dear Hiring Manager,",
        "",
        cover_result.body,
        "",
        "Sincerely,",
        name,
    ]
    if cover_result.facts_used:
        lines += [
            "",
            "---",
            "_Facts this draft relies on (self-audit — verify before sending):_",
        ]
        lines += [f"- {fact}" for fact in cover_result.facts_used]
    return "\n".join(lines)


def tailor_job(conn: sqlite3.Connection, job_id: int, *, client=None) -> TailorResult:
    job = repo.get_job(conn, job_id)
    if job is None:
        raise ValueError(f"no job with id {job_id}")

    cv_structure = profile_kb.load_cv_structure()
    CVTailoringResult, _CVSuggestion = build_cv_models()

    cv_result = llm.call(
        "tailor_cv",
        CVTailoringResult,
        client=client,
        profile_context=profile_kb.tailoring_context(),
        cv_structure=profile_kb.render_cv_structure_for_prompt(),
        company=job["company_name"],
        title=job["title"],
        jd_text=job["description_text"],
    )
    warnings = _check_bullet_drift(cv_result, cv_structure)

    cover_result = llm.call(
        "tailor_cover_letter",
        CoverLetterResult,
        client=client,
        profile_context=profile_kb.tailoring_context(),
        company=job["company_name"],
        title=job["title"],
        jd_text=job["description_text"],
    )

    # Both calls succeeded — now (and only now) write anything.
    cv_markdown = _render_cv_markdown(job, cv_structure, cv_result)
    cover_markdown = _render_cover_letter_markdown(cover_result)

    out_dir = config.OUTPUT_DIR / f"{_slugify(job['company_name'])}-{job_id}"
    out_dir.mkdir(parents=True, exist_ok=True)
    cv_path = out_dir / "cv_bullets.md"
    cover_path = out_dir / "cover_letter.md"
    cv_path.write_text(cv_markdown)
    cover_path.write_text(cover_markdown)

    context_hash = _context_hash(job)
    repo.insert_generated_asset(conn, job_id, "cv_bullets", context_hash, cv_markdown)
    repo.insert_generated_asset(conn, job_id, "cover_letter", context_hash, cover_markdown)
    repo.set_status(conn, job_id, "materials_ready")

    return TailorResult(
        job_id=job_id, cv_path=cv_path, cover_letter_path=cover_path, warnings=warnings
    )
