"""Contract tests for pipeline.opportunities.scan — mocked client, no live
API and no real web search."""

import config
from db import repo
from pipeline import opportunities
from tests.conftest import FakeLLMClient, make_response

RESULT = opportunities.OpportunityScanResult(
    overview="Found two AI startups and one RAG-eval learning gap.",
    items=[
        opportunities.OpportunityItem(
            kind="startup",
            title="Acme AI Labs raises Series A",
            summary="Acme AI Labs raised $10M to build agentic RAG tooling for pharma.",
            why_relevant="Matches your AI/ML + pharma + startup targets.",
            source_url="https://example.com/acme-series-a",
            suggested_action="Check their careers page.",
        ),
        opportunities.OpportunityItem(
            kind="learning",
            title="RAG evaluation frameworks",
            summary="RAGAS and similar frameworks are now standard for evaluating retrieval quality.",
            why_relevant="You've built RAG systems but haven't used a formal eval framework yet.",
            source_url=None,
            suggested_action="Spend an hour on the RAGAS docs.",
        ),
    ],
)


def test_scan_calls_llm_with_web_search_and_opportunities_model(conn, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "OUTPUT_DIR", tmp_path / "output")
    client = FakeLLMClient(make_response(RESULT))

    opportunities.scan(conn, client=client)

    assert client.calls[-1]["model"] == config.MODEL_OPPORTUNITIES
    assert client.calls[-1]["config"].max_output_tokens == config.MAX_TOKENS_OPPORTUNITIES
    assert client.calls[-1]["config"].tools is not None


def test_scan_stores_items_and_writes_digest(conn, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "OUTPUT_DIR", tmp_path / "output")
    client = FakeLLMClient(make_response(RESULT))

    result = opportunities.scan(conn, client=client)

    assert len(result.new_ids) == 2
    assert result.duplicates == 0
    rows = repo.list_opportunities(conn)
    assert {r["kind"] for r in rows} == {"startup", "learning"}

    assert result.digest_path.exists()
    digest = result.digest_path.read_text()
    assert "Acme AI Labs raises Series A" in digest
    assert "RAG evaluation frameworks" in digest


def test_rescan_dedupes_against_prior_items(conn, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "OUTPUT_DIR", tmp_path / "output")
    opportunities.scan(conn, client=FakeLLMClient(make_response(RESULT)))

    rerun = opportunities.scan(conn, client=FakeLLMClient(make_response(RESULT)))
    assert rerun.new_ids == []
    assert rerun.duplicates == 2
    assert len(repo.list_opportunities(conn)) == 2


def test_scan_passes_focus_into_prompt(conn, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "OUTPUT_DIR", tmp_path / "output")
    client = FakeLLMClient(make_response(RESULT))
    opportunities.scan(conn, focus="quick commerce AI", client=client)
    assert "quick commerce AI" in client.last_prompt
