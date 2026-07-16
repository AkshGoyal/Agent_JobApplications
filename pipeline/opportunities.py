"""Opportunities / market-intelligence scan.

A search-grounded LLM call surveys the web for things the job pipeline
otherwise wouldn't surface on its own: newly-funded/launching AI startups,
notable AI developments, concrete learning gaps, and entrepreneurship
angles — all filtered through the user's own profile targets. This is
judgment (relevance, recency, grounding a claim in a real search result),
so it's an LLM step; everything else (dedup, storage, digest rendering) is
deterministic code, same split as the rest of the pipeline.

Not a job source: opportunity rows never touch the job table or its
lifecycle. Read-only web search via the model's own tool use — no scraping
code here, no LinkedIn involvement at all.
"""

import hashlib
import sqlite3
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

import config
import llm
import profile_kb
from db import repo


class OpportunityItem(BaseModel):
    """Structured-output contract for one item in the opportunity_scan prompt."""

    kind: Literal["startup", "ai_development", "learning", "entrepreneurship"]
    title: str
    summary: str
    why_relevant: str
    source_url: str | None = None
    suggested_action: str | None = None


class OpportunityScanResult(BaseModel):
    overview: str
    items: list[OpportunityItem]


@dataclass
class ScanResult:
    overview: str
    new_ids: list[int] = field(default_factory=list)
    duplicates: int = 0
    digest_path: Path | None = None


def _dedup_hash(item: OpportunityItem) -> str:
    return hashlib.sha256(f"{item.kind}|{item.title.strip().lower()}".encode()).hexdigest()


def _render_digest(overview: str, items: list[OpportunityItem]) -> str:
    lines = [f"# Opportunities scan — {date.today().isoformat()}", "", overview, ""]
    by_kind: dict[str, list[OpportunityItem]] = {}
    for item in items:
        by_kind.setdefault(item.kind, []).append(item)
    for kind, kind_items in by_kind.items():
        lines.append(f"## {kind.replace('_', ' ').title()}")
        for item in kind_items:
            lines.append(f"### {item.title}")
            lines.append(item.summary)
            lines.append(f"_Why relevant: {item.why_relevant}_")
            if item.source_url:
                lines.append(f"Source: {item.source_url}")
            if item.suggested_action:
                lines.append(f"Suggested action: {item.suggested_action}")
            lines.append("")
    return "\n".join(lines)


def scan(conn: sqlite3.Connection, *, focus: str | None = None, client=None) -> ScanResult:
    """Run one search-grounded opportunities scan, dedupe against prior scans,
    store new items, and write a digest Markdown file."""
    focus_line = f"Focus this scan on: {focus}" if focus else ""
    result = llm.call(
        "opportunity_scan",
        OpportunityScanResult,
        client=client,
        model=config.MODEL_OPPORTUNITIES,
        max_tokens=config.MAX_TOKENS_OPPORTUNITIES,
        tools="web_search",
        profile_context=profile_kb.opportunities_context(),
        focus_line=focus_line,
        today=date.today().isoformat(),
    )

    scan_result = ScanResult(overview=result.overview)
    for item in result.items:
        new_id = repo.insert_opportunity(
            conn,
            kind=item.kind,
            title=item.title,
            summary=item.summary,
            why_relevant=item.why_relevant,
            source_url=item.source_url,
            suggested_action=item.suggested_action,
            dedup_hash=_dedup_hash(item),
        )
        if new_id is None:
            scan_result.duplicates += 1
        else:
            scan_result.new_ids.append(new_id)

    out_dir = config.OUTPUT_DIR / "opportunities"
    out_dir.mkdir(parents=True, exist_ok=True)
    digest_path = out_dir / f"{date.today().isoformat()}.md"
    digest_path.write_text(_render_digest(result.overview, result.items))
    scan_result.digest_path = digest_path

    return scan_result
