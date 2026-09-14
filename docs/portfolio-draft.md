# Portfolio draft — Agent_JobApplications

Draft material for review. Everything below is derived from the repo's code,
commit history, README, and config — anything I couldn't verify from those
sources is marked **[INFERRED]**, and open questions are listed at the end.

---

## 1. GitHub repo description & topics

**Description** (118 chars):
> A human-in-the-loop AI job search assistant: ranks postings and drafts tailored CVs/cover letters. You apply manually.

**Topics:**
`python` `fastapi` `sqlite` `llm` `gemini-api` `cli` `chrome-extension` `job-search`

---

## 2. Case study

### Problem

Applying to jobs involves the same manual work over and over: reading a
posting, deciding whether it's worth your time, and rewriting your CV and
cover letter to fit it. `PROJECT_SPEC.md` frames this directly as a personal
tool — "I discover relevant job openings based on my profile and targets,
rank them, and generate tailored application materials... I apply
manually." It's built for one user (the repo owner) managing their own job
search, not as a multi-tenant product.

### What I built

**In plain terms:** A tool that takes a job posting — pasted in, captured
with a one-click Chrome extension, or picked up automatically from LinkedIn
job-alert emails — and uses an LLM to pull out the structured details
(company, title, location) and score how well it matches your background.
For postings you're interested in, it can draft CV bullet suggestions, a
cover letter, and answers to application-form questions, all grounded
strictly in a profile you maintain (`profile/facts.yaml`,
`narratives.md`, `canned_answers.yaml`, your CV). A human reviews and sends
everything manually — the tool never submits an application or sends an
email itself. There's also a separate "Opportunities" feature: a
web-search-grounded scan for relevant startups and AI developments, unrelated
to the job-tracking pipeline, which runs weekly via a scheduled GitHub
Action and posts its digest as a GitHub Issue.

**Architecture:**
```
sources/   → one module per job source (manual paste, Gmail alert IMAP ingestion,
             Chrome extension capture) — each produces a raw posting
pipeline/  → normalize → dedup → store → rank (LLM) → tailor/answer (LLM)
profile/   → the user's own knowledge base — the ONLY source of truth the LLM may draw from
llm.py     → single wrapper for every LLM call (prompts, parsing, retries, logging)
db/        → SQLite schema, migrations, repository functions
cli/       → Typer commands (ingest, rank, list, show, tailor, answer, status, opportunities)
web/       → FastAPI app + static page, calling the same pipeline functions as the CLI
extension/ → Chrome extension that posts the current page to the web app's ingest endpoint
config.py  → env-var API key, model names, paths
```
Data flows one way: a source produces a raw posting → the pipeline
normalizes, dedupes, and stores it in SQLite → the LLM ranks it against the
profile → on request, the LLM drafts materials, grounded only in `profile/`.
The CLI and web UI are two interfaces over the same pipeline functions.

### Hard parts and decisions

These are drawn from the commit history and code, not from the README:

- **LLM provider migration, contained by design (`bd8ee40`).** The app
  switched from Anthropic to Google Gemini. Because every LLM call goes
  through one wrapper (`llm.py`), the change touched only `llm.py`,
  `config.py`, `requirements.txt`, and the test double — the pipelines, CLI,
  and prompt templates were untouched. A same-day follow-up (`bbd5684`)
  hot-fixed a 404 after `gemini-2.5-flash` was retired for new API keys,
  caught because the scheduled `live-run` GitHub Action calls the real API
  (tests mock the LLM client, so this class of failure can only show up
  there).
- **Retries weren't free (`04fd800`).** Unlike the Anthropic SDK, the
  `google-genai` SDK makes exactly one attempt per call and raises
  immediately on a 429 or a transient 503 ("high demand, try again later").
  The fix was configuring `HttpRetryOptions` explicitly on client
  construction, with a unit test that asserts the option is set (no live
  network call) so the behavior can't silently regress again.
- **Grounding enforced at the schema level, not just by prompting, in two
  places.** In `pipeline/answer.py`, when the model claims a pre-approved
  "canned" answer applies to a question, the code doesn't trust that claim —
  it independently re-looks-up the field in `canned_answers.yaml` and
  overrides to `needs_input` if the field is actually blank, with a test
  specifically covering the case where the model hallucinates an answer for
  a blank field. In `pipeline/tailor.py`, CV bullet suggestions are
  constrained to `Literal[...]` types for `entry_id`/`section`, built
  dynamically from `cv_canonical_structure.yaml` at call time — so a
  fabricated CV entry is schema-invalid before it could ever be returned,
  rather than merely checked after the fact.
- **Explicit boundary enforcement on the Gmail source (`a025a45`).** The
  Gmail-alert ingestion opens the mailbox strictly read-only over IMAP,
  never sends/marks/moves/deletes anything, never fetches linkedin.com
  itself, and stores job URLs from the emails as inert text labels rather
  than following them — several of the project's stated non-goals (no
  LinkedIn scraping, no email sending) enforced directly in code.
- **A late refactor unified three ingestion paths (`43f99e5`).** The
  normalize → dedup → store logic was pulled out of the manual-paste-specific
  function into a shared `store_posting()`, so manual paste, the Chrome
  extension, and Gmail ingestion all go through one storage path instead of
  three separately-maintained ones.
- Smaller in-flight fixes are visible too — e.g. `2132425` fixed invalid YAML
  in `canned_answers.yaml` that had been committed.

The offline test suite (101 test functions across 18 files) mocks the LLM
client throughout, so it runs in CI on every push with no API key and no
live model calls (`.github/workflows/ci.yml`).

### Outcome

_TODO — to be filled in._

### What I'd do next

Based on `PROJECT_SPEC.md`'s explicitly deferred backlog (Phase 4+,
"schema-only for now"): an HR contact finder, outreach-email drafting behind
a human-approved outbox, and alumni-referral triage. The spec also notes a
planned but unbuilt feature: detecting application confirmations/rejections
in email as *suggested* status changes only, never automatic ones.
Separately, the profile files (`facts.yaml`, `canned_answers.yaml`) still
contain unfilled `# TODO` placeholders in the working tree — output quality
for tailoring/answering depends on that profile being complete, which is
worth noting as a practical next step independent of new features.

---

## 3. Questions for Aksh

1. Every generation commit in this history is authored `Claude
   <noreply@anthropic.com>`, and `CLAUDE.md` lays out working agreements for
   Claude Code (plan mode first, your review before code, etc.). How do you
   want your role described to a hiring manager — spec author & reviewer
   directing an AI coding assistant, hands-on implementer, or something
   between? This changes how "What I built" should be framed, and I didn't
   want to guess.
2. Is this still an active part of your job search, or was it a
   point-in-time build? That affects how "Outcome" should be framed once you
   fill it in.
3. Is there any real usage you can share (roughly how many postings
   ingested, materials generated, applications sent)? Nothing like that is
   in the repo itself — `output/` and the SQLite DB are gitignored — so I
   have no basis to estimate it.
4. Should the "Opportunities" weekly market-intelligence digest be
   highlighted as a distinct feature in the case study, or treated as a
   minor add-on to the main job-tracking pipeline?
