"""Repo-layer tests for the opportunity table: insert/dedupe/list/status."""

import pytest

from db import repo


def _item(conn, title="Acme raises Series A", dedup_hash="hash-1"):
    return repo.insert_opportunity(
        conn,
        kind="startup",
        title=title,
        summary="Acme raised a $10M Series A to build agentic RAG tooling.",
        why_relevant="Matches your AI/ML + startup targets.",
        source_url="https://example.com/acme-raises",
        suggested_action="Check their careers page for early roles.",
        dedup_hash=dedup_hash,
    )


def test_insert_and_list(conn):
    oid = _item(conn)
    assert oid is not None
    rows = repo.list_opportunities(conn)
    assert len(rows) == 1
    assert rows[0]["id"] == oid
    assert rows[0]["status"] == "new"


def test_insert_dedupes_silently(conn):
    first = _item(conn, dedup_hash="dup-hash")
    second = _item(conn, title="Acme raises Series A (again)", dedup_hash="dup-hash")
    assert first is not None
    assert second is None
    assert len(repo.list_opportunities(conn)) == 1


def test_list_filters_by_status(conn):
    a = _item(conn, dedup_hash="a")
    _item(conn, title="Beta launches", dedup_hash="b")
    repo.set_opportunity_status(conn, a, "saved")
    assert len(repo.list_opportunities(conn, status="saved")) == 1
    assert len(repo.list_opportunities(conn, status="new")) == 1


def test_set_status_rejects_unknown_status(conn):
    oid = _item(conn)
    with pytest.raises(ValueError, match="unknown opportunity status"):
        repo.set_opportunity_status(conn, oid, "archived")


def test_set_status_rejects_unknown_id(conn):
    with pytest.raises(ValueError, match="no opportunity with id"):
        repo.set_opportunity_status(conn, 999, "saved")
