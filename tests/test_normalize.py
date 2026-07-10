from dataclasses import replace

from pipeline import normalize
from sources.manual_paste import RawPosting


def _posting(**overrides) -> RawPosting:
    base = RawPosting(
        source="manual_paste",
        source_url="https://example.com/job/1",
        description_text="  raw   text\nstays  verbatim  ",
        company_name="Acme AI",
        title="AI Engineer",
        location="Bengaluru",
        remote_type="hybrid",
        posted_at="2026-06-25",
    )
    return replace(base, **overrides)


def test_clean_text_collapses_whitespace():
    assert normalize.clean_text("  Acme \n AI  Labs ") == "Acme AI Labs"


def test_clean_text_empty_becomes_none():
    assert normalize.clean_text("   ") is None
    assert normalize.clean_text(None) is None


def test_remote_type_mapping():
    assert normalize.normalize_remote_type("Remote") == "remote"
    assert normalize.normalize_remote_type("  HYBRID ") == "hybrid"
    assert normalize.normalize_remote_type("On-site") == "onsite"
    assert normalize.normalize_remote_type("work from home") == "remote"
    assert normalize.normalize_remote_type("4 days in office per month") == "unknown"
    assert normalize.normalize_remote_type(None) == "unknown"
    assert normalize.normalize_remote_type("") == "unknown"


def test_normalize_cleans_fields_but_not_description():
    raw = _posting(company_name=" Acme  AI ", title=" AI  Engineer ", location="  ")
    cleaned = normalize.normalize(raw)
    assert cleaned.company_name == "Acme AI"
    assert cleaned.title == "AI Engineer"
    assert cleaned.location is None
    # The pasted JD must stay byte-for-byte verbatim.
    assert cleaned.description_text == raw.description_text
