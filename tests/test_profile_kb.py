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
