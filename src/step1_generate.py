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
from .gen_schemas import GenJobDescription, GenResume
from .llm_client import generate_structured

# Minimal, generic system directive. The SUBSTANTIVE, swappable prompt is the versioned
# template file (Hard Rule #3); this only sets role posture.
_JOB_SYSTEM = "You write realistic, internally-consistent hiring content. Be concrete and specific."
_RESUME_SYSTEM = "You write realistic, internally-consistent resumes in the requested voice. Be concrete and specific."

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


def generate_resume_for_job(
    job: dict,
    *,
    fit_level: str,
    style: str,
    seed: str | None = None,
) -> dict:
    """Generate one resume TARGETED at a given job, steered by fit level + writing style.

    `fit_level` and `style` are the INTENDED labels — we stamp them into metadata (our
    ownership boundary). The ACTUAL skill overlap is measured later by the labeler (step4)
    via Jaccard; here we only steer generation toward the intended band.
    """
    trace_id = f"res-{uuid.uuid4().hex[:12]}"
    req = job["requirements"]

    user_prompt = load(
        "resume",
        job_title=job["title"],
        required_skills=", ".join(req["required_skills"]),
        preferred_skills=", ".join(req.get("preferred_skills", [])) or "(none listed)",
        fit_guidance=load(f"fit/{fit_level}"),        # steering fragment (prompts/fit/)
        style_guidance=load(f"styles/{style}"),        # voice fragment (prompts/styles/)
        seed=seed or trace_id,
    )

    gen: GenResume = generate_structured(
        GenResume,
        system=_RESUME_SYSTEM,
        user=user_prompt,
        log_step="generate_resume",
        trace_id=trace_id,
    )

    record = gen.model_dump()
    record["metadata"] = {          # intended labels + provenance, owned by our code
        "trace_id": trace_id,
        "generated_at": _now_iso(),
        "prompt_template": "resume_v1",
        "fit_level": fit_level,     # what we ASKED for; verified later, not trusted
        "writing_style": style,
    }
    return record


def _write_jsonl(records: list[dict], path) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")


def _demo_strict_gate(record: dict, model_cls, label: str) -> None:
    """Teaching peek-ahead at step2: run the loose record through the STRICT schema so we
    can SEE whether the two-layer gap produced a valid or an invalid record this time."""
    try:
        model_cls.model_validate(record)
        print(f"  strict-gate preview [{label}]: VALID ✓")
    except Exception as exc:  # pydantic.ValidationError, but keep it generic for the demo
        errs = getattr(exc, "errors", lambda: [])()
        print(f"  strict-gate preview [{label}]: INVALID ({len(errs)} error(s)) "
              f"— raw material for step3")
        for e in errs[:4]:  # show a few field paths so the two-layer gap is concrete
            loc = ".".join(str(p) for p in e.get("loc", ()))
            print(f"      - {loc}: {e.get('msg', '')}")


def main() -> None:
    # Windows consoles default to cp1252 and crash on em-dashes/emoji the LLM emits.
    sys.stdout.reconfigure(encoding="utf-8")

    from .schemas import JobDescription, Resume  # local: step1 doesn't depend on the gate

    config.ensure_dirs()
    ts = _timestamp()
    print(f"Generating via {config.GENERATOR_MODEL} (temp={config.GENERATOR_TEMPERATURE})...")

    # ── 1 job ────────────────────────────────────────────────────────────
    job = generate_one_job(is_niche=False)
    job_path = config.GENERATED_DIR / f"jobs_{ts}.jsonl"
    _write_jsonl([job], job_path)

    print(f"\nJOB  {job['title']}  @ {job['company']['name']} ({job['company']['industry']})")
    print(f"  exp: {job['requirements']['experience_years']}y / {job['requirements']['experience_level']}"
          f"   req_skills: {', '.join(job['requirements']['required_skills'][:6])}")
    _demo_strict_gate(job, JobDescription, "job")

    # ── 1 resume targeted at that job (Phase 2b proof) ───────────────────
    fit, style = "partial", "technical_detailed"
    resume = generate_resume_for_job(job, fit_level=fit, style=style)
    resume_path = config.GENERATED_DIR / f"resumes_{ts}.jsonl"
    _write_jsonl([resume], resume_path)

    print(f"\nRESUME  {resume['contact']['name']}  (fit={fit}, style={style})")
    print(f"  email: {resume['contact']['email']}   phone: {resume['contact']['phone']}")
    skills_preview = ", ".join(f"{s['name']}={s['proficiency_level']}" for s in resume["skills"][:5])
    print(f"  skills: {skills_preview}")
    if resume["education"]:
        print(f"  grad_date (raw): {resume['education'][0]['graduation_date']}  "
              f"gpa: {resume['education'][0].get('gpa')}")
    _demo_strict_gate(resume, Resume, "resume")

    print(f"\nWrote -> {job_path.relative_to(config.ROOT_DIR)}")
    print(f"Wrote -> {resume_path.relative_to(config.ROOT_DIR)}")


if __name__ == "__main__":
    main()
