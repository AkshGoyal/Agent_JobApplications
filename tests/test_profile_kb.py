"""profile_kb loads the real profile/ files — these tests run against them."""

import profile_kb


def test_load_facts_has_core_sections():
    facts = profile_kb.load_facts()
    assert "targets" in facts
    assert "experience" in facts
    assert "skills" in facts


def test_ranking_context_includes_targets_and_arc():
    context = profile_kb.ranking_context()
    assert "targets:" in context           # YAML section present
    assert "Career arc:" in context        # narrative paragraph present
    # Contact details must not leak into the ranking prompt.
    facts = profile_kb.load_facts()
    email = facts.get("identity", {}).get("email")
    if email:
        assert email not in context


def test_cv_section_names_match_the_five_canonical_sections():
    assert profile_kb.cv_section_names() == (
        "Education",
        "Professional Experience",
        "Projects",
        "Leadership & Organizational Roles",
        "Extracurriculars & Accolades",
    )


def test_cv_entry_ids_are_unique_and_include_known_entries():
    ids = profile_kb.cv_entry_ids()
    assert len(ids) == len(set(ids))
    assert "aspect_ratio_analyst" in ids
    assert "geo_optimization" in ids


def test_render_cv_structure_for_prompt_includes_entries_and_bullets():
    text = profile_kb.render_cv_structure_for_prompt()
    assert "[aspect_ratio_analyst]" in text
    assert "RAG system" in text
    assert "## Professional Experience" in text


def test_tailoring_context_excludes_identity_but_includes_narratives():
    context = profile_kb.tailoring_context()
    assert "Narratives" in context
    assert "targets:" in context
    facts = profile_kb.load_facts()
    email = facts.get("identity", {}).get("email")
    if email:
        assert email not in context


def test_canned_context_flags_blank_fields():
    context = profile_kb.canned_context()
    assert "Policies" in context
    data = profile_kb.load_canned_answers()
    for key, value in data.get("standard_questions", {}).items():
        if value in (None, "", []):
            assert f"{key}: (not provided" in context
