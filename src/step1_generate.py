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
import time
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


def _append_jsonl(path, record: dict) -> None:
    """Append one record and close — crash-safe: a mid-run failure keeps prior progress."""
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


# ── Balanced assignment ──────────────────────────────────────────────────
# Fit level and writing style are assigned by cycling through all 25 (fit×style)
# combos. Over each block of 25 resumes every combo appears exactly once, so each of
# the 5 fit levels lands ~20 % of pairs (spec floor ≥15 %), every style is used evenly,
# and fit is DECORRELATED from style (not "excellent is always formal"). No RNG →
# reproducible runs.
def _fit_style_for(index: int) -> tuple[str, str]:
    combo = index % 25
    fit_level = config.FIT_LEVELS[combo % 5][0]        # (label, low, high) -> label
    writing_style = config.WRITING_STYLES[combo // 5]
    return fit_level, writing_style


def _is_niche(job_index: int, niche_ratio: float) -> bool:
    """Deterministic ~niche_ratio split so runs are reproducible (no RNG)."""
    return (job_index % 10) < round(niche_ratio * 10)


def _pct(part: int, whole: int) -> float:
    return 100.0 * part / whole if whole else 0.0


def run(*, num_jobs: int, resumes_per_job: int, niche_ratio: float) -> None:
    """Full generation run: jobs → targeted resumes → pair links, written incrementally.

    Rule #6: a single failed generation is logged and skipped, never crashes the run.
    Rule #9: outputs are timestamped. The rate-limit delay lives in llm_client.
    """
    sys.stdout.reconfigure(encoding="utf-8")  # cp1252 consoles crash on LLM em-dashes/emoji
    config.ensure_dirs()
    config.assert_api_key()  # fail fast before any work if the key is missing

    ts = _timestamp()
    jobs_path = config.GENERATED_DIR / f"jobs_{ts}.jsonl"
    resumes_path = config.GENERATED_DIR / f"resumes_{ts}.jsonl"
    pairs_path = config.GENERATED_DIR / f"pairs_{ts}.jsonl"

    target = num_jobs * resumes_per_job
    print(f"Generating {num_jobs} jobs x {resumes_per_job} resumes = {target} pairs "
          f"via {config.GENERATOR_MODEL} (temp={config.GENERATOR_TEMPERATURE})")
    print(f"Output -> data/generated/*_{ts}.jsonl\n")

    fit_counts = {lvl[0]: 0 for lvl in config.FIT_LEVELS}
    style_counts = {s: 0 for s in config.WRITING_STYLES}
    n_jobs = n_resumes = n_pairs = n_niche = 0
    failures: list[dict] = []

    resume_index = 0
    start = time.monotonic()

    for j in range(num_jobs):
        is_niche = _is_niche(j, niche_ratio)
        try:
            job = generate_one_job(is_niche=is_niche)
        except Exception as exc:  # transport/schema failure survived retries → skip job
            failures.append({"kind": "job", "job_index": j, "error": repr(exc)})
            print(f"[job {j + 1}/{num_jobs}] FAILED: {exc!r}")
            continue

        _append_jsonl(jobs_path, job)
        n_jobs += 1
        n_niche += int(is_niche)
        job_tid = job["metadata"]["trace_id"]
        tag = "niche" if is_niche else "standard"
        print(f"[job {j + 1}/{num_jobs}] {job['title'][:48]} ({tag}) -> {resumes_per_job} resumes")

        for _ in range(resumes_per_job):
            fit, style = _fit_style_for(resume_index)
            resume_index += 1
            try:
                resume = generate_resume_for_job(job, fit_level=fit, style=style)
            except Exception as exc:
                failures.append({"kind": "resume", "job_trace_id": job_tid,
                                 "fit": fit, "style": style, "error": repr(exc)})
                continue

            _append_jsonl(resumes_path, resume)
            n_resumes += 1
            fit_counts[fit] += 1
            style_counts[style] += 1

            _append_jsonl(pairs_path, {
                "pair_id": f"pair-{uuid.uuid4().hex[:12]}",
                "job_trace_id": job_tid,
                "resume_trace_id": resume["metadata"]["trace_id"],
                "fit_level": fit,          # intended label; verified by Jaccard in step4
                "generated_at": _now_iso(),
            })
            n_pairs += 1

    elapsed = time.monotonic() - start

    # ── Summary — lets us check spec floors BEFORE validation ────────────
    print("\n" + "=" * 60)
    print(f"DONE in {elapsed:.0f}s  |  {n_jobs} jobs, {n_resumes} resumes, "
          f"{n_pairs} pairs, {n_niche} niche jobs, {len(failures)} failures")

    print("\nFit-level distribution (spec floor: each >= 15% of pairs):")
    for lvl in config.FIT_LEVELS:
        name = lvl[0]
        pct = _pct(fit_counts[name], n_pairs)
        print(f"  {name:10s} {fit_counts[name]:4d}  {pct:5.1f}%  [{'ok' if pct >= 15.0 else 'LOW'}]")

    print("\nWriting-style distribution:")
    for s in config.WRITING_STYLES:
        print(f"  {s:20s} {style_counts[s]:4d}  {_pct(style_counts[s], n_resumes):5.1f}%")

    if failures:
        print(f"\n{len(failures)} failure(s) logged (run continued; details in logs/raw_responses.jsonl).")

    print(f"\nWrote -> {jobs_path.relative_to(config.ROOT_DIR)}")
    print(f"Wrote -> {resumes_path.relative_to(config.ROOT_DIR)}")
    print(f"Wrote -> {pairs_path.relative_to(config.ROOT_DIR)}")


def main() -> None:
    import argparse

    p = argparse.ArgumentParser(description="Step 1 — generate jobs, resumes, and pair links.")
    p.add_argument("--jobs", type=int, default=config.DEFAULT_NUM_JOBS,
                   help=f"number of jobs (default {config.DEFAULT_NUM_JOBS})")
    p.add_argument("--resumes-per-job", type=int, default=config.DEFAULT_RESUMES_PER_JOB,
                   help=f"resumes per job (default {config.DEFAULT_RESUMES_PER_JOB})")
    p.add_argument("--niche-ratio", type=float, default=config.NICHE_JOB_RATIO,
                   help=f"fraction of jobs flagged niche (default {config.NICHE_JOB_RATIO})")
    args = p.parse_args()
    run(num_jobs=args.jobs, resumes_per_job=args.resumes_per_job, niche_ratio=args.niche_ratio)


if __name__ == "__main__":
    main()
