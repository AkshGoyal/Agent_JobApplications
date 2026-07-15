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
   tailoring/drafting (CV bullets, cover letters, application answers).
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
cli/              # Typer app: ingest paste, rank, list, show, status, status-report, tailor, answer, deadline
web/              # FastAPI app + single static page — same pipeline, in the browser
profile/          # my knowledge base: facts.yaml, narratives.md, canned_answers.yaml, cv_canonical.pdf,
                  #   cv_canonical_structure.yaml (ground-truth CV entries for tailor)
output/           # generated materials (gitignored)
tests/            # pytest; LLM client is always mocked — no live API calls in tests
```

Job status lifecycle:
`discovered → ranked → shortlisted → materials_ready → applied → in_process → interview → offer / rejected / dropped`.
Transitions to `applied` and beyond are made by me via the CLI, never
automatically.

## CLI (current scope)

```bash
python -m cli.main ingest paste --url <URL> [--file jd.txt] [--rank]
python -m cli.main rank [JOB_ID]
python -m cli.main list [--min-score 70] [--status discovered]
python -m cli.main show <JOB_ID>
python -m cli.main status <JOB_ID> <STAGE>   # e.g. status 3 applied — always manual
python -m cli.main status-report             # funnel counts per lifecycle stage
python -m cli.main tailor <JOB_ID>           # CV bullet suggestions + cover letter draft
python -m cli.main answer <JOB_ID> "question text"
python -m cli.main deadline <JOB_ID> <YYYY-MM-DD|clear>
```

## Web UI

Run **from the repo root** (`python -m` resolves packages from the current
directory — running it from anywhere else fails with
`ModuleNotFoundError: No module named 'web'`):

```bash
cd /workspaces/Agent_JobApplications   # Codespaces repo root; adjust locally
python -m web.app                      # http://localhost:8000 (Codespaces auto-forwards port 8000)
# equivalent alternative:
python -m uvicorn web.app:app --host 0.0.0.0 --port 8000
```

One static page over the same pipeline: paste a JD (add & rank), browse and
filter the ranked table, open a job's detail/rationale, change its status,
generate/view materials, ask application questions, and see the funnel. The
**Tracker** section groups jobs by lifecycle status (collapsible per stage);
each row expands to a deadline badge (amber ≤3 days out, red overdue) plus
inline status/deadline controls and copy/download buttons for any generated
CV bullets and cover letter. The web layer (`web/app.py`) contains no
business logic — it must stay a thin JSON wrapper over `pipeline/` and
`db/repo.py`.

`ingest paste` reads the JD from `--file` or stdin (paste, then Ctrl-D). It
always **stores first, ranks after** — a failed LLM call must never lose a
pasted JD. Duplicates (same company+title+location hash or same source URL)
are reported, not re-inserted.

## Phase 2 generation: `tailor` + `answer`

`tailor <job_id>` outputs CV bullet suggestions and a cover letter draft to
`output/<company>-<job_id>/` and logs both as `generated_asset` rows; the job
advances to `materials_ready`. Grounding is enforced at the schema level, not
just prompt wording: `profile/cv_canonical_structure.yaml` is the sole
ground-truth source of CV entries (hand-transcribed from `cv_canonical.pdf`),
and the LLM's response schema constrains `entry_id`/`section` to
`Literal[...]` values built from that file — inventing an entry or a section
outside the canonical five (Education / Professional Experience / Projects /
Leadership & Organizational Roles / Extracurriculars & Accolades) is
schema-invalid, not merely discouraged. It suggests improved bullets for
existing entries only; a soft drift check flags (never blocks) suggestions
whose `original_bullet` doesn't closely match a known bullet. The cover
letter's signature is appended deterministically by code, never LLM-written.

`answer <job_id> "question"` prefers `profile/canned_answers.yaml`
verbatim/adapted over fresh generation, and follows the `policies` list in
that file (never misstate CGPA, never claim absent skills, flag instead of
guessing when a canned answer is blank). Defense in depth: even if the model
claims a canned field applies, code independently re-verifies the field
isn't blank before trusting it — never trusts the model's self-report.
Always logged to `generated_asset`, including `needs_input` results, for an
audit trail.

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

### Model/env-var configuration (all optional; defaults in `config.py`)

| Env var | Default | Controls |
|---|---|---|
| `JOBSEARCH_MODEL` | `gemini-3.5-flash` | global fallback model |
| `JOBSEARCH_MODEL_EXTRACT` | global | JD field extraction (`ingest paste`) |
| `JOBSEARCH_MODEL_RANK` | global | relevance scoring (`rank`) |
| `JOBSEARCH_MODEL_TAILOR` | global | CV bullets + cover letter (`tailor`) |
| `JOBSEARCH_MODEL_ANSWER` | global | application Q&A (`answer`) |
| `JOBSEARCH_MAX_TOKENS_TAILOR` | `16384` | output-token cap for both tailor calls |
| `JOBSEARCH_DB` | `jobsearch.db` | SQLite path |

To cut costs, `gemini-3.1-flash-lite` (~6x cheaper) is a good fit for
extract/rank/answer — but do **not** use `gemini-2.5-flash-lite`
(retired for new API keys; shuts down Oct 2026).

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
