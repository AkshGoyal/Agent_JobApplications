# CLAUDE.md — Job Search Assistant

Personal, human-in-the-loop job search assistant. It captures job postings,
ranks them against my profile, and (in later phases) drafts tailored
application materials. **I apply manually — the system never submits anything
on my behalf.** Full details: `PROJECT_SPEC.md` (the source of truth; read it
before making design decisions).

## Hard non-goals — never build, scaffold, or suggest

- No automated submission of applications, anywhere.
- No LinkedIn automation of any kind (no scraping, no messaging, no login).
  Phase 1's only source is *manual paste*: I copy a JD from LinkedIn myself.
- No email sending.
- No hosted/multi-user deployment. (The original "no web UI" rule was lifted
  2026-07-11: a *local, single-user* web UI in `web/` wraps the same pipeline
  functions as the CLI.)
- No multi-agent frameworks (CrewAI, LangGraph, AutoGen, etc.). This is a
  deterministic pipeline with LLM calls at specific steps.

## Guiding principles

1. **Deterministic pipeline, LLM at the joints.** Code handles parsing,
   dedup, storage, state transitions. The LLM is called only where judgment
   is needed: field extraction from pasted JDs, relevance scoring, and
   (Phase 2) tailoring/drafting.
2. **Human approves everything outbound.** All outputs are drafts I read and
   use manually.
3. **Everything is inspectable.** SQLite, YAML/Markdown, plain CLI.
4. **Grounded generation only.** Every generated CV bullet, cover letter, or
   form answer must be traceable to facts in `profile/`. Never invent
   experience, metrics, or skills. If the profile lacks a needed fact, ask me
   instead of fabricating.

## Architecture

```
config.py         # env-var API key, model name, DB path — the ONE place for settings
llm.py            # the ONE wrapper for all LLM calls (templates, parsing, logging)
profile_kb.py     # loads profile/ files — the ONLY source of truth about me
prompts/          # readable prompt template files (never scattered f-strings)
db/               # migrations, connection, repository functions
sources/          # one module per job source (Phase 1: manual_paste)
pipeline/         # normalize → dedup → ingest → rank
cli/              # Typer app: ingest paste, rank, list, show, status, status-report
web/              # FastAPI app + single static page — same pipeline, in the browser
profile/          # my knowledge base: facts.yaml, narratives.md, canned_answers.yaml, cv_canonical.pdf
output/           # generated materials (gitignored; Phase 2)
tests/            # pytest; LLM client is always mocked — no live API calls in tests
```

Job status lifecycle:
`discovered → ranked → shortlisted → materials_ready → applied → in_process → interview → offer / rejected / dropped`.
Transitions to `applied` and beyond are made by me via the CLI, never
automatically.

## Phase 1 CLI (current scope)

```bash
python -m cli.main ingest paste --url <URL> [--file jd.txt] [--rank]
python -m cli.main rank [JOB_ID]
python -m cli.main list [--min-score 70] [--status discovered]
python -m cli.main show <JOB_ID>
python -m cli.main status <JOB_ID> <STAGE>   # e.g. status 3 applied — always manual
python -m cli.main status-report             # funnel counts per lifecycle stage
```

## Web UI

```bash
python -m web.app        # http://localhost:8000 (Codespaces auto-forwards port 8000)
```

One static page over the same pipeline: paste a JD (add & rank), browse and
filter the ranked table, open a job's detail/rationale, change its status,
and see the funnel. The web layer (`web/app.py`) contains no business logic —
it must stay a thin JSON wrapper over `pipeline/` and `db/repo.py`.

`ingest paste` reads the JD from `--file` or stdin (paste, then Ctrl-D). It
always **stores first, ranks after** — a failed LLM call must never lose a
pasted JD. Duplicates (same company+title+location hash or same source URL)
are reported, not re-inserted.

## Phase 2 contract (recorded now, do not build yet)

`tailor <job_id>` must output CV content matching the style of
`profile/cv_canonical.pdf`:

- The same five sections only: Education / Professional Experience /
  Projects / Leadership & Organizational Roles / Extracurriculars & Accolades.
- The same bullet style: em-dash bullets, concise (1–2 lines), key terms
  bolded, metric-led where possible.
- It suggests improved bullets for existing entries; it **never invents new
  sections** and every bullet must trace to `profile/` facts.

`answer <job_id> "question"` must prefer `profile/canned_answers.yaml`
verbatim/adapted over fresh generation, and must follow the `policies` list
in that file (never misstate CGPA, never claim absent skills, flag instead of
guessing when a canned answer is blank).

## Working agreements

- Start new features in Plan mode; show the plan before writing code.
- Small commits, one logical change each.
- Every LLM call goes through `llm.py`; model settings only in `config.py`.
- Prompts live in `prompts/` as readable template files.
- Write tests alongside code — parsing and dedup logic especially. Tests
  never hit the live API; mock the Gemini client (`FakeLLMClient`).
- When a design decision isn't covered by the spec, ask — don't assume.
- Secrets only via environment variables (`GEMINI_API_KEY`); never
  committed. Never commit the SQLite DB or `output/` (see `.gitignore`).

## Dev setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export GEMINI_API_KEY=...   # from Google AI Studio; never commit this
pytest                     # offline, mocked LLM — no key needed
```

Smoke test (needs a real API key):

```bash
python -m cli.main ingest paste --url https://www.linkedin.com/jobs/view/123 \
  --file tests/fixtures/sample_jd.txt --rank
python -m cli.main list --min-score 0
python -m cli.main show 1
```

## Running on GitHub

- **CI (`.github/workflows/ci.yml`)** runs `pytest` on every push/PR. Mocked —
  no key, no Gemini calls, no cost.
- **Live run (`.github/workflows/live-run.yml`)** is a manual "Run workflow"
  button that exercises the real Gemini flow on the sample JD. Add the key
  under **Settings → Secrets and variables → Actions** as `GEMINI_API_KEY`.
  Spends quota only when triggered; the DB is ephemeral per run.
- **Codespaces (`.devcontainer/`)** gives an interactive browser terminal for
  real use (paste JDs, read rankings). Add the key under **Settings → Secrets
  and variables → Codespaces** as `GEMINI_API_KEY`; it's injected as an env var.

The key is never committed — only stored in GitHub secrets.
