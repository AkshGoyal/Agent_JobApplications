"""Central configuration — the ONE place for settings.

API keys come from environment variables only (never committed).
Model names and paths live here so they can be changed in one place.
"""

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent

# --- LLM settings -----------------------------------------------------------
# The anthropic SDK reads ANTHROPIC_API_KEY from the environment itself;
# we never store the key in code or in the database.
API_KEY_ENV_VAR = "ANTHROPIC_API_KEY"

# One model for all Phase 1 calls (extraction + ranking). Change here only.
MODEL = os.environ.get("JOBSEARCH_MODEL", "claude-opus-4-8")
MAX_TOKENS = 2048

# --- Paths ------------------------------------------------------------------
DB_PATH = Path(os.environ.get("JOBSEARCH_DB", REPO_ROOT / "jobsearch.db"))
PROFILE_DIR = REPO_ROOT / "profile"
PROMPTS_DIR = REPO_ROOT / "prompts"
MIGRATIONS_DIR = REPO_ROOT / "db" / "migrations"
OUTPUT_DIR = REPO_ROOT / "output"  # Phase 2: generated materials (gitignored)


def api_key_present() -> bool:
    """True if an Anthropic API key is available in the environment."""
    return bool(os.environ.get(API_KEY_ENV_VAR))
