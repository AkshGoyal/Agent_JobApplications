"""Shared builders for valid tailor/answer fixture responses.

Kept separate from conftest.py since these are specific to the tailor tests
and reference pipeline.tailor's dynamically-built models.
"""

from pipeline.tailor import CoverLetterResult, build_cv_models


def valid_cv_result():
    CVTailoringResult, CVSuggestion = build_cv_models()
    suggestion = CVSuggestion(
        entry_id="aspect_ratio_analyst",
        section="Professional Experience",
        original_bullet=(
            "Architected production **RAG system** using **OpenAI APIs, "
            "hybrid retrieval** combining **semantic vector search** with "
            "keyword-based **BM25** and **routing agents**."
        ),
        suggested_bullet=(
            "Architected production **RAG system** for pharma marketing "
            "research using **OpenAI APIs** and **hybrid retrieval**."
        ),
        rationale="Emphasizes RAG + hybrid retrieval, matching this JD's core ask.",
    )
    return CVTailoringResult(suggestions=[suggestion], notes=None)


def valid_cover_letter_result() -> CoverLetterResult:
    return CoverLetterResult(
        subject="Application for AI Engineer — Acme AI Labs",
        body=(
            "I am excited to apply for the AI Engineer role at Acme AI Labs. "
            "In my current role I architected a production RAG system combining "
            "hybrid retrieval with routing agents, directly relevant to your "
            "team's work."
        ),
        facts_used=["Aspect Ratio RAG system", "hybrid retrieval (BM25 + semantic search)"],
    )
