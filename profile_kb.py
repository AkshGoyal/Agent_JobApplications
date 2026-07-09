"""Profile knowledge base loader.

The files in profile/ are the ONLY source of truth about the user. Generation
and ranking must draw exclusively from what these loaders return — never from
model priors about the user.
"""

import yaml

import config


def load_facts() -> dict:
    """Structured facts: education, experience, projects, skills, targets, ..."""
    with open(config.PROFILE_DIR / "facts.yaml") as f:
        return yaml.safe_load(f)


def load_narratives() -> str:
    """Longer-form story material for cover letters and long-form answers."""
    return (config.PROFILE_DIR / "narratives.md").read_text()


def load_canned_answers() -> dict:
    """Approved answers to recurring application questions (Phase 2 uses this)."""
    with open(config.PROFILE_DIR / "canned_answers.yaml") as f:
        return yaml.safe_load(f)


def career_arc() -> str:
    """The one-paragraph career arc section from narratives.md ('' if absent)."""
    lines = load_narratives().splitlines()
    collected: list[str] = []
    in_section = False
    for line in lines:
        if line.startswith("## "):
            if in_section:
                break
            in_section = line.lower().startswith("## career arc")
            continue
        if in_section:
            collected.append(line)
    return "\n".join(collected).strip()


def ranking_context() -> str:
    """Compact profile context for the ranking prompt.

    Includes the career-arc paragraph plus the fact sections relevant to
    relevance scoring (targets drive the ranking, per facts.yaml). Identity
    and contact details are deliberately excluded — ranking doesn't need them.
    """
    facts = load_facts()
    section_keys = ("targets", "skills", "experience", "projects", "education",
                    "leadership", "achievements")
    sections = {k: facts[k] for k in section_keys if k in facts}
    parts = []
    arc = career_arc()
    if arc:
        parts.append(f"Career arc:\n{arc}")
    parts.append(
        "Profile facts (YAML):\n"
        + yaml.dump(sections, sort_keys=False, allow_unicode=True)
    )
    return "\n\n".join(parts)
