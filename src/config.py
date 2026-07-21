"""Central configuration — the single control panel for the whole pipeline.

WHY this file exists: the spec requires that every threshold/weight change be
data-driven and logged (iteration log). If those numbers were scattered across
modules, a change would be a scavenger hunt and easy to get wrong. Keeping them
here means one edit, one place, and a clean diff to cite in docs/iteration_log.md.

Secrets/models/temperatures come from the environment (.env, git-ignored).
Everything else — bands, thresholds, buzzword lists, paths — is plain constants.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env once, at import time, so every module that imports config sees it.
load_dotenv()

# ─────────────────────────────────────────────────────────────────────────
# Paths — resolved relative to the repo root (this file is src/config.py).
# ─────────────────────────────────────────────────────────────────────────
ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
GENERATED_DIR = DATA_DIR / "generated"
VALIDATED_DIR = DATA_DIR / "validated"
LABELS_DIR = DATA_DIR / "labels"
REPORTS_DIR = DATA_DIR / "reports"
VISUALS_DIR = ROOT_DIR / "visualizations"
LOGS_DIR = ROOT_DIR / "logs"
PROMPTS_DIR = ROOT_DIR / "prompts"


def _env(key: str, default: str) -> str:
    """Read an env var, falling back to a safe default (keeps dev friction low)."""
    return os.getenv(key, default)


# ─────────────────────────────────────────────────────────────────────────
# LLM provider — OpenRouter via the OpenAI-compatible client.
# ─────────────────────────────────────────────────────────────────────────
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = _env("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

GENERATOR_MODEL = _env("GENERATOR_MODEL", "openai/gpt-4o-mini")
JUDGE_MODEL = _env("JUDGE_MODEL", "openai/gpt-4o-mini")
CORRECTOR_MODEL = _env("CORRECTOR_MODEL", "openai/gpt-4o-mini")

# Generator gets variety; judge/corrector run near-deterministic (hard rule 4).
GENERATOR_TEMPERATURE = float(_env("GENERATOR_TEMPERATURE", "0.8"))
JUDGE_TEMPERATURE = float(_env("JUDGE_TEMPERATURE", "0.0"))
CORRECTOR_TEMPERATURE = float(_env("CORRECTOR_TEMPERATURE", "0.2"))

REQUEST_TIMEOUT_SECONDS = int(_env("REQUEST_TIMEOUT_SECONDS", "60"))
API_CALL_DELAY_SECONDS = float(_env("API_CALL_DELAY_SECONDS", "0.3"))  # rate-limit courtesy

# Optional observability (only active if keys present).
BRAINTRUST_API_KEY = os.getenv("BRAINTRUST_API_KEY", "")
LOGFIRE_TOKEN = os.getenv("LOGFIRE_TOKEN", "")

# ─────────────────────────────────────────────────────────────────────────
# Generation volume (spec: ≥50 jobs, 5–10 resumes/job, ≥250 pairs).
# ─────────────────────────────────────────────────────────────────────────
DEFAULT_NUM_JOBS = 50
DEFAULT_RESUMES_PER_JOB = 6

# The 5 writing-style templates (Challenge 1 — diversity).
WRITING_STYLES = [
    "formal_corporate",
    "casual_startup",
    "technical_detailed",
    "achievement_focused",
    "career_changer",
]

# ─────────────────────────────────────────────────────────────────────────
# Fit levels — (label, inclusive-low, exclusive-high) on Jaccard skill overlap.
# Used both to STEER generation and to VERIFY it after labeling.
# ─────────────────────────────────────────────────────────────────────────
FIT_LEVELS = [
    ("excellent", 0.80, 1.01),   # 80 %+
    ("good", 0.60, 0.80),        # 60–80 %
    ("partial", 0.40, 0.60),     # 40–60 %
    ("poor", 0.20, 0.40),        # 20–40 %
    ("mismatch", 0.00, 0.20),    # <20 %
]
MIN_FIT_LEVEL_SHARE = 0.15  # each fit level must be ≥15 % of all pairs

# ─────────────────────────────────────────────────────────────────────────
# Seniority ladder (spec mapping). Mismatch flag when |resume - job| > 1.
# ─────────────────────────────────────────────────────────────────────────
SENIORITY_LEVELS = {
    "entry": 0, "junior": 0,
    "mid": 1, "intermediate": 1,
    "senior": 2,
    "lead": 3, "principal": 3, "staff": 3,
    "executive": 4, "director": 4, "vp": 4,
}
SENIORITY_MISMATCH_GAP = 1  # > this many levels apart = flag

# ─────────────────────────────────────────────────────────────────────────
# Failure-metric thresholds (F2–F6). All tunable + iteration-logged.
# ─────────────────────────────────────────────────────────────────────────
EXPERIENCE_MIN_RATIO = 0.50        # F2: <50 % of required years = mismatch
MISSING_CORE_TOP_N = 3             # F4: job's top-3 required skills are "core"

# F5 — hallucination heuristics
HALLUC_ENTRY_YEARS_MAX = 2         # "entry-level" = < 2 years total experience
HALLUC_ENTRY_EXPERT_MAX = 10       # entry-level claiming expert in >10 skills = flag
HALLUC_TOTAL_SKILLS_MAX = 20       # 20+ skills listed …
HALLUC_EXPERT_RATIO_MAX = 0.60     # … most (>60 %) marked expert = flag

# F6 — awkward-language heuristics
AWKWARD_BUZZWORD_MAX = 5           # >5 buzzwords in one summary/description = flag
AWKWARD_REPEAT_MIN = 3             # same word 3+ times in close proximity = flag
BUZZWORDS = [
    "synergy", "synergize", "think outside the box", "thinking outside the box",
    "move the needle", "low-hanging fruit", "circle back", "deep dive",
    "leverage", "paradigm shift", "value-add", "core competency", "bandwidth",
    "boil the ocean", "best of breed", "game changer", "disrupt", "ninja",
    "rockstar", "guru", "results-driven", "detail-oriented", "team player",
    "go-getter", "self-starter", "hard worker", "proven track record",
]

PROFICIENCY_LEVELS = ["Beginner", "Intermediate", "Advanced", "Expert"]

# ─────────────────────────────────────────────────────────────────────────
# Correction loop (spec: ≤3 attempts, >50 % success).
# ─────────────────────────────────────────────────────────────────────────
MAX_CORRECTION_ATTEMPTS = 3

# ─────────────────────────────────────────────────────────────────────────
# Validation-rule constants (mirrored by Pydantic validators in schemas.py).
# ─────────────────────────────────────────────────────────────────────────
PHONE_MIN_LENGTH = 10
GPA_MIN, GPA_MAX = 0.0, 4.0
EXPERIENCE_YEARS_MIN, EXPERIENCE_YEARS_MAX = 0, 30


def ensure_dirs() -> None:
    """Create all output directories if missing (idempotent). Called by steps."""
    for d in (GENERATED_DIR, VALIDATED_DIR, LABELS_DIR, REPORTS_DIR, VISUALS_DIR, LOGS_DIR):
        d.mkdir(parents=True, exist_ok=True)


def assert_api_key() -> None:
    """Fail fast with a friendly message if the key is missing (before any API call)."""
    if not OPENROUTER_API_KEY:
        raise RuntimeError(
            "OPENROUTER_API_KEY is not set. Copy .env.example to .env and paste your key."
        )
