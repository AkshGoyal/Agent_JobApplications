# Job Search Assistant

A personal tool that reads job postings, scores how well they fit your
profile, and drafts tailored CV bullets, cover letters, and application-form
answers — you review and apply manually; it never submits anything on your
behalf.

## The problem it solves

Job hunting means re-reading the same job description five times, guessing
whether it's worth your time, then rewriting your CV and cover letter for
every application. This tool automates the repetitive parts — extracting
structured data from a posting, scoring relevance against your background,
and drafting tailored materials grounded in your actual CV — while keeping a
human in the loop for every decision that matters (what to apply to, what to
send, when a status changes).

## Tech stack

- **Python 3.11** — core pipeline and CLI (Typer)
- **SQLite** — job/application tracking, plain-file database
- **FastAPI + a static HTML/JS page** — local single-user web UI
- **Google Gemini API** (`google-genai`) — extraction, relevance ranking,
  tailoring, and market-intelligence search, all through one wrapper module
- **Chrome extension** (vanilla JS) — one-click capture of the job posting
  you're currently viewing
- **pytest** — tests, with the LLM client always mocked (no live API calls)
- **GitHub Actions** — CI, plus a scheduled opportunity-scan digest

## How to run it locally

```bash
# 1. Clone and install dependencies
git clone https://github.com/AkshGoyal/Agent_JobApplications.git
cd Agent_JobApplications
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
# edit .env and set GEMINI_API_KEY (get one at aistudio.google.com/apikey)
export $(grep -v '^#' .env | xargs)   # or use a tool like direnv/python-dotenv

# 3. Fill in your profile (required before ranking/tailoring will work)
#    edit profile/facts.yaml, profile/narratives.md, profile/canned_answers.yaml

# 4. Use the CLI
python -m cli.main ingest paste --url <job-url> --file jd.txt --rank
python -m cli.main list --min-score 70
python -m cli.main tailor <job_id>

# — or run the web UI instead —
python -m web.app   # http://localhost:8000
```

Run `python -m pytest` to run the test suite.

## Architecture

A deterministic pipeline with an LLM called only at the steps that need
judgment (extraction, ranking, drafting). Everything else — parsing,
deduplication, storage, state transitions — is plain code.

```
sources/   → one module per job source (manual paste, Gmail alert ingestion,
             Chrome extension capture) — each produces a raw posting
pipeline/  → normalize → dedup → store → rank (LLM) → tailor/answer (LLM)
profile/   → your knowledge base (facts.yaml, narratives.md, canned_answers.yaml,
             cv_canonical.pdf) — the ONLY source of truth the LLM may draw from
llm.py     → single wrapper for every LLM call (prompts, parsing, logging)
db/        → SQLite schema, migrations, repository functions
cli/       → Typer commands (ingest, rank, list, show, tailor, answer, status, opportunities)
web/       → FastAPI app + static page, same pipeline functions as the CLI
extension/ → Chrome extension that posts the current page to the web app's
             ingest endpoint
config.py  → env-var API key, model names, paths — the one place for settings
```

Data flows one way: a **source** produces a raw posting → the **pipeline**
normalizes, dedupes, and stores it in **SQLite** → the LLM (via `llm.py`)
ranks it against your **profile** → on request, the LLM drafts tailored
materials, grounded only in `profile/`, written to `output/` (or shown in the
web UI). The **CLI** and **web UI** are two interfaces over the identical
pipeline functions — neither has logic the other lacks. Status changes
(`applied`, `interview`, etc.) are always made by you, never automatically.

## Screenshots

<!-- TODO: add screenshots of the web UI (pipeline board) and CLI output -->
