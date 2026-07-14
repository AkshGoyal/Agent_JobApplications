"""Central configuration — the ONE place for settings.

API keys come from environment variables only (never committed).
Model names and paths live here so they can be changed in one place.
"""

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent

# --- LLM settings -----------------------------------------------------------
# The google-genai SDK reads GEMINI_API_KEY from the environment itself;
# we never store the key in code or in the database.
API_KEY_ENV_VAR = "GEMINI_API_KEY"

# Global default model. gemini-3.5-flash is the current GA flash-tier model —
# fast, strong at structured JSON output. Override via JOBSEARCH_MODEL.
MODEL = os.environ.get("JOBSEARCH_MODEL", "gemini-3.5-flash")

# Per-task model overrides — each falls back to MODEL. To cut costs, try
# gemini-3.1-flash-lite ($0.25/M in, $1.50/M out vs 3.5-flash's $1.50/$9.00 —
# ~6x cheaper) for extract/rank/answer, e.g.:
#   export JOBSEARCH_MODEL_EXTRACT=gemini-3.1-flash-lite
# (Do NOT use gemini-2.5-flash-lite: retired for new API keys, shuts down
# Oct 2026.) Keep tailor on the stronger model if prose quality matters.
MODEL_EXTRACT = os.environ.get("JOBSEARCH_MODEL_EXTRACT", MODEL)
MODEL_RANK = os.environ.get("JOBSEARCH_MODEL_RANK", MODEL)
MODEL_TAILOR = os.environ.get("JOBSEARCH_MODEL_TAILOR", MODEL)
MODEL_ANSWER = os.environ.get("JOBSEARCH_MODEL_ANSWER", MODEL)

# Output-token caps. Gemini flash models spend output tokens on internal
# "thinking" too, so generation tasks need far more headroom than extraction:
# a 2048 cap can truncate (finish_reason=MAX_TOKENS) a long CV-bullets or
# cover-letter response. 3.5-flash supports ~64k output tokens.
MAX_TOKENS = 2048
MAX_TOKENS_TAILOR = int(os.environ.get("JOBSEARCH_MAX_TOKENS_TAILOR", "16384"))

# --- Paths ------------------------------------------------------------------
DB_PATH = Path(os.environ.get("JOBSEARCH_DB", REPO_ROOT / "jobsearch.db"))
PROFILE_DIR = REPO_ROOT / "profile"
PROMPTS_DIR = REPO_ROOT / "prompts"
MIGRATIONS_DIR = REPO_ROOT / "db" / "migrations"
OUTPUT_DIR = REPO_ROOT / "output"  # Phase 2: generated materials (gitignored)


def api_key_present() -> bool:
    """True if a Gemini API key is available in the environment."""
    return bool(os.environ.get(API_KEY_ENV_VAR))
