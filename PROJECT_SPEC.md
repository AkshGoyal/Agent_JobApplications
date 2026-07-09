# Job Search Assistant — Project Spec

## What this is

A personal, human-in-the-loop job search assistant. It discovers relevant job
openings based on my profile and targets, ranks them, and generates tailored
application materials (CV bullets, cover letters, answers to application form
questions). **I apply manually.** The system never submits anything on my
behalf.

This is Phase A of a larger system. Outreach workflows (HR cold email, alumni
referrals) are designed for but deliberately deferred — the architecture must
leave room for them without building them now.

## Explicit non-goals (do not build, scaffold, or suggest these)

- No automated submission of applications, anywhere.
- No LinkedIn automation of any kind (no scraping, no messaging, no login).
- No email sending. (A future phase adds a human-approved outbox; not now.)
- No web UI in early phases. CLI first.
- No multi-agent framework (CrewAI, LangGraph, AutoGen, etc.). This is a
  deterministic pipeline with LLM calls at specific steps, not an agent swarm.

## Guiding principles

1. **Deterministic pipeline, LLM at the joints.** Code handles fetching,
   parsing, dedup, storage, state transitions. The LLM is called only where
   judgment is needed: relevance scoring, tailoring, drafting, Q&A.
2. **Human approves everything outbound.** In this phase that simply means:
   all outputs are drafts I read and use manually.
3. **Everything is inspectable.** SQLite database, YAML/Markdown files, plain
   CLI. I should be able to open any artifact and understand it.
4. **One vertical slice before generalizing.** Prove the pipeline on one job
   source end-to-end before adding sources.
5. **Grounded generation only.** Every generated CV bullet, cover letter, or
   form answer must be traceable to facts in my profile knowledge base. Never
   invent experience, metrics, or skills. If the profile lacks the needed
   fact, say so and ask me instead of fabricating.

## Tech stack (fixed — do not propose alternatives unless something is broken)

- Python 3.11+, managed with a virtualenv and `requirements.txt`
- SQLite via the standard library (`sqlite3`) or SQLAlchemy Core if justified
- `httpx` + `beautifulsoup4` / `feedparser` for fetching and parsing sources
- Anthropic API (`anthropic` SDK) for all LLM calls; model name and settings
  in a single config module so they can be changed in one place
- `click` or `typer` for the CLI
- `pytest` for tests
- Profile knowledge base: YAML + Markdown files in `profile/` (human-editable,
  git-tracked)

## Architecture

```
sources/          # one module per job source (fetch + parse → RawPosting)
pipeline/         # normalize → dedup → store → rank (LLM) → status updates
generation/       # tailor CV bullets, cover letter, form-question answers (LLM)
profile/          # my knowledge base (YAML facts + Markdown narratives)
db/               # schema, migrations, repository functions
cli/              # commands: ingest, rank, list, show, tailor, answer, status
config.py         # API keys via env vars, model settings, paths
```

### Data model (core tables — extend as needed, don't rename)

**company**: id, name, website, notes, is_target (bool), created_at

**job**: id, company_id, title, location, remote_type, source, source_url,
description_text, posted_at, discovered_at, dedup_hash,
relevance_score (0–100), relevance_rationale, status, status_updated_at

Job status lifecycle:
`discovered → ranked → shortlisted → materials_ready → applied → in_process → interview → offer / rejected / dropped`

Status changes to `applied` and beyond are made by me via the CLI
(`cli status <job_id> applied`), never automatically.

**generated_asset**: id, job_id, kind (cv_bullets | cover_letter | form_answer),
prompt_context_hash, content, created_at, my_edits (nullable)

**person** and **outreach** tables: define the schema now (so future phases
slot in), but build no logic around them.

### Profile knowledge base (`profile/`)

- `facts.yaml` — structured: education, roles with dates, skills, projects
  with metrics, certifications, locations, work authorization, salary range,
  target roles/industries/geographies
- `narratives.md` — longer-form: career story, strengths, key project
  write-ups the LLM can draw on for cover letters
- `canned_answers.yaml` — my approved answers to recurring application
  questions (notice period, relocation, sponsorship, etc.)

The generation module must load ONLY from these files as its source of truth
about me.

## Phases

**Phase 1 — vertical slice (build this first, nothing else):**
1. Repo scaffold, config, DB schema + migrations, profile KB templates I fill in
2. ONE job source module: <FILL IN: e.g. a specific job board RSS/API or one
   company careers page>
3. Ingest → normalize → dedup → store
4. LLM relevance ranking against my profile (score + 2–3 line rationale)
5. CLI: `ingest`, `list --min-score 70`, `show <job_id>`
6. Tests for parsing, dedup, and the ranking prompt's I/O contract

**Phase 2 — generation:**
- `tailor <job_id>` → CV bullet suggestions + cover letter draft as Markdown
  files under `output/<company>-<job_id>/`
- `answer <job_id> "question text"` → drafted form answer grounded in profile
- Log all generated assets to `generated_asset`

**Phase 3 — tracking:**
- Manual status transitions via CLI; `status-report` command showing the
  funnel (discovered / applied / interviewing / etc.)
- (Later, separate design discussion: Gmail read-only ingestion to detect
  confirmations/rejections. Do not build yet.)

**Phase 4+ (deferred, schema-only for now):** HR contact finder, outreach
drafting, approval queue/outbox, alumni triage.

## Working agreements for Claude Code

- Always start a new feature in Plan mode; show me the plan before writing code.
- Small commits with clear messages, one logical change each.
- Every LLM call goes through one wrapper function (logging, retries, model
  config in one place). Prompts live as readable template files/constants,
  not scattered f-strings.
- Write tests alongside code, not after. Parsing and dedup logic especially.
- When a design decision isn't covered by this spec, ask me — don't assume.
- Never add scope from the non-goals list, even as "optional" stubs.
- Secrets only via environment variables; never committed.
