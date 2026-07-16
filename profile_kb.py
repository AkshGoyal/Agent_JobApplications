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


def load_cv_structure() -> dict:
    """The canonical CV's exact sections/entries/bullets (section name ->
    list of {id, entry, context, bullets}). This is the ONLY source `tailor`
    may draw entries from — facts.yaml has more history than the CV shows
    (old-CV-only roles, supplementary detail); this file is deliberately the
    narrower, exact-CV-match source of truth.
    """
    with open(config.PROFILE_DIR / "cv_canonical_structure.yaml") as f:
        return yaml.safe_load(f)["sections"]


def cv_section_names() -> tuple[str, ...]:
    """The 5 canonical section names, in CV order."""
    return tuple(load_cv_structure().keys())


def cv_entry_ids() -> tuple[str, ...]:
    """Every entry id across all sections — used to constrain the tailor
    LLM's structured output to real entries via a Literal[...] type."""
    return tuple(
        entry["id"]
        for entries in load_cv_structure().values()
        for entry in entries
    )


def render_cv_structure_for_prompt() -> str:
    """Readable section -> entry -> bullets block for the tailor_cv prompt."""
    lines = []
    for section, entries in load_cv_structure().items():
        lines.append(f"## {section}")
        for entry in entries:
            lines.append(f"### [{entry['id']}] {entry['entry']}")
            if entry.get("context"):
                lines.append(f"_{entry['context']}_")
            for bullet in entry["bullets"]:
                lines.append(f"− {bullet}")
        lines.append("")
    return "\n".join(lines)


def tailoring_context() -> str:
    """Profile context for tailor_cv / tailor_cover_letter.

    Broader than ranking_context(): adds the full narratives text (role
    detail, framing) so wording can be specific — but still excludes
    identity/contact (unchanged reasoning: never let the LLM fabricate or
    reproduce personal fields; those are injected deterministically by code
    where needed, e.g. the cover letter's signature block).
    """
    facts = load_facts()
    section_keys = ("education", "experience", "projects", "leadership",
                    "achievements", "skills", "targets")
    sections = {k: facts[k] for k in section_keys if k in facts}
    parts = [
        "Profile facts (YAML):\n"
        + yaml.dump(sections, sort_keys=False, allow_unicode=True),
        "Narratives (context for framing/wording only — every claim must "
        "still be grounded in the facts above; do not introduce new "
        "unverifiable claims):\n" + load_narratives(),
    ]
    return "\n\n".join(parts)


def canned_context() -> str:
    """Renders canned_answers.yaml for the `answer` prompt. Blank fields are
    marked explicitly so the prompt itself reinforces the policy: flag
    instead of guessing.
    """
    data = load_canned_answers()

    def render_section(section: dict) -> str:
        lines = []
        for key, value in section.items():
            if value in (None, "", []):
                lines.append(f"{key}: (not provided — flag as needs_input, never guess)")
            else:
                lines.append(f"{key}: {value}")
        return "\n".join(lines)

    parts = [
        "Logistics:\n" + render_section(data.get("logistics", {})),
        "Standard questions:\n" + render_section(data.get("standard_questions", {})),
        "Policies (must always follow):\n"
        + "\n".join(f"- {p}" for p in data.get("policies", [])),
    ]
    return "\n\n".join(parts)


def opportunities_context() -> str:
    """Compact profile context for the Opportunities scan: targets, skills,
    and the career arc — enough to judge relevance of startups/AI news/
    learning gaps without exposing identity/contact fields."""
    facts = load_facts()
    section_keys = ("targets", "skills", "experience", "projects")
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
