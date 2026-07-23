"""Step 1 — Generation.

PHASE 2a SLICE (walking skeleton): generate exactly ONE job end-to-end to prove the
pipe — prompt template → LLM client → lenient gen schema → OUR metadata stamp → JSONL.
Resume generation, the 5 style templates, and the full 50-job batch come in 2b/2c.

Data flow for one job:
    prompts/job_description.md  ──►  llm_client.generate_structured(GenJobDescription)
                                          │  (loose: model can violate domain rules)
                                          ▼
                            record = gen.model_dump()  +  metadata WE stamp
                                          │  (trace_id, timestamp, is_niche_role)
                                          ▼
                     data/generated/jobs_<timestamp>.jsonl   (Rule #9: timestamped)
"""

from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime, timezone

from prompts import load

from . import config
from .gen_schemas import GenJobDescription
from .llm_client import generate_structured

# Minimal, generic system directive. The SUBSTANTIVE, swappable prompt is the versioned
# template file (Hard Rule #3); this only sets role posture.
_JOB_SYSTEM = "You write realistic, internally-consistent hiring content. Be concrete and specific."

_NICHE_CLAUSE = (
    "This must be a NICHE / specialized role — an unusual domain, rare tech stack, or "
    "hard-to-fill niche (not a generic web-dev or data-analyst posting)."
)
_STANDARD_CLAUSE = (
    "This should be a common, standard industry role that many companies hire for."
)


def _now_iso() -> str:
    # Timezone-aware UTC (project note: never the deprecated datetime.utcnow()).
    return datetime.now(timezone.utc).isoformat()


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def generate_one_job(*, is_niche: bool = False, seed: str | None = None) -> dict:
    """Generate one job via the LLM and attach pipeline-owned metadata.

    Returns a plain dict shaped like the strict `JobDescription` (title/company/
    requirements/metadata) — ready to be written and, later, validated by step2.
    """
    trace_id = f"job-{uuid.uuid4().hex[:12]}"  # provenance key WE mint (Rule #8, Q2)
    niche_clause = _NICHE_CLAUSE if is_niche else _STANDARD_CLAUSE

    user_prompt = load("job_description", niche_clause=niche_clause, seed=seed or trace_id)

    gen: GenJobDescription = generate_structured(
        GenJobDescription,
        system=_JOB_SYSTEM,
        user=user_prompt,
        log_step="generate_job",
        trace_id=trace_id,
    )

    record = gen.model_dump()
    record["metadata"] = {          # our code owns this block, not the LLM
        "trace_id": trace_id,
        "generated_at": _now_iso(),
        "is_niche_role": is_niche,
    }
    return record


def _write_jsonl(records: list[dict], path) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")


def _demo_strict_gate(record: dict) -> None:
    """Teaching peek-ahead at step2: run the loose record through the STRICT schema so we
    can SEE whether the two-layer gap produced a valid or an invalid record this time."""
    from .schemas import JobDescription  # local import: step1 doesn't depend on the gate

    try:
        JobDescription.model_validate(record)
        print("  strict-gate preview: VALID against JobDescription ✓")
    except Exception as exc:  # pydantic.ValidationError, but keep it generic for the demo
        n = len(getattr(exc, "errors", lambda: [])())
        print(f"  strict-gate preview: INVALID ({n} error(s)) — this is the raw material step3 corrects")


def main() -> None:
    # Windows consoles default to cp1252 and crash on em-dashes/emoji the LLM emits.
    sys.stdout.reconfigure(encoding="utf-8")

    config.ensure_dirs()
    print(f"Generating 1 job via {config.GENERATOR_MODEL} (temp={config.GENERATOR_TEMPERATURE})...")

    record = generate_one_job(is_niche=False)

    out_path = config.GENERATED_DIR / f"jobs_{_timestamp()}.jsonl"
    _write_jsonl([record], out_path)

    print(f"\n  title:      {record['title']}")
    print(f"  company:    {record['company']['name']} ({record['company']['industry']})")
    print(f"  exp_years:  {record['requirements']['experience_years']}  "
          f"level: {record['requirements']['experience_level']}")
    print(f"  req_skills: {', '.join(record['requirements']['required_skills'][:6])}")
    print(f"  trace_id:   {record['metadata']['trace_id']}")
    _demo_strict_gate(record)
    print(f"\nWrote -> {out_path.relative_to(config.ROOT_DIR)}")


if __name__ == "__main__":
    main()
