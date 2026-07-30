"""Step 3 — Correction loop. API-hitting (corrector model, near-deterministic).

For every invalid resume from step2, feed its SPECIFIC Pydantic errors + the record back
to the LLM, ask it to repair only those fields, re-validate against the strict schema, and
retry up to MAX_CORRECTION_ATTEMPTS. Then it's either fixed or permanently failed.

    invalid envelope ─► correction prompt (errors + record) ─► LLM (GenResume)
           ▲                                                        │
           └────────── re-validate; still invalid? feed new errors ─┘  (≤3 attempts)

Design notes:
  * The loop is OURS (not Instructor's): the LLM returns a lenient GenResume so we always
    get parseable structure, then WE gate it against the strict schema and drive retries.
  * NO ground-truth leakage: metadata (incl. `injected_defect`) is stripped before the
    corrector sees the record — it works only from the errors, then we re-attach metadata.
  * Corrector runs at temperature < generator (Hard Rule #4) for deterministic fixes.
  * Fix-quality: re-validation proves "now valid"; we ALSO check list lengths didn't shrink
    to catch a corrector that deletes the offending entry instead of repairing it.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timezone

from pydantic import ValidationError

from prompts import load

from . import config
from .gen_schemas import GenResume
from .llm_client import generate_structured
from .schemas import Resume
from .step2_validate import categorize  # single source of truth for the taxonomy

_CORRECTOR_SYSTEM = (
    "You repair malformed resume JSON. Change only what the errors require and keep every "
    "other field identical. Return the complete resume."
)
_LIST_FIELDS = ("education", "experience", "skills")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_jsonl(records, path) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")


def _validate(record: dict) -> tuple[bool, list[dict]]:
    try:
        Resume.model_validate(record)
        return True, []
    except ValidationError as exc:
        errs = [{
            "loc": ".".join(str(p) for p in e["loc"]),
            "type": e["type"],
            "category": categorize(e),
            "msg": e["msg"],
        } for e in exc.errors()]
        return False, errs


def _fmt_errors(errors: list[dict]) -> str:
    return "\n".join(f"- {e['loc']}: {e['msg']} ({e['category']})" for e in errors)


def _lengths(record: dict) -> dict:
    return {k: len(record.get(k, []) or []) for k in _LIST_FIELDS}


def correct_one(envelope: dict) -> dict:
    """Run the ≤3-attempt correction loop for one invalid resume envelope."""
    original = envelope["record"]
    metadata = original.get("metadata", {})
    content = {k: v for k, v in original.items() if k != "metadata"}  # strip ground truth
    orig_lengths = _lengths(original)
    errors = envelope["errors"]

    for attempt in range(1, config.MAX_CORRECTION_ATTEMPTS + 1):
        prompt = load("corrector", errors=_fmt_errors(errors),
                      record=json.dumps(content, indent=2, ensure_ascii=False, default=str))
        try:
            fixed = generate_structured(
                GenResume, system=_CORRECTOR_SYSTEM, user=prompt,
                model=config.CORRECTOR_MODEL, temperature=config.CORRECTOR_TEMPERATURE,
                log_step="correct_resume", trace_id=metadata.get("trace_id"),
            )
        except Exception as exc:  # Rule #6: never crash the run
            return {"status": "error", "attempts": attempt, "trace_id": metadata.get("trace_id"),
                    "error": repr(exc)}

        content = fixed.model_dump()
        candidate = {**content, "metadata": metadata}  # re-attach provenance
        ok, errs = _validate(candidate)
        if ok:
            shrank = any(_lengths(candidate)[k] < orig_lengths[k] for k in _LIST_FIELDS)
            return {"status": "fixed", "attempts": attempt, "record": candidate,
                    "injected_defect": metadata.get("injected_defect"),
                    "structure_shrank": shrank}
        errors = errs  # feed the NEW errors into the next attempt

    return {"status": "failed", "attempts": config.MAX_CORRECTION_ATTEMPTS,
            "trace_id": metadata.get("trace_id"),
            "injected_defect": metadata.get("injected_defect"), "errors": errors}


def run(*, timestamp: str | None = None) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    config.ensure_dirs()

    inv_files = sorted(config.VALIDATED_DIR.glob("invalid_resumes_*.jsonl"))
    if not inv_files:
        raise FileNotFoundError("No invalid_resumes_*.jsonl — run step2 first.")
    ts = timestamp or inv_files[-1].stem[len("invalid_resumes_"):]

    invalids = _read_jsonl(config.VALIDATED_DIR / f"invalid_resumes_{ts}.jsonl")
    print(f"Correcting {len(invalids)} invalid resumes "
          f"(model={config.CORRECTOR_MODEL}, temp={config.CORRECTOR_TEMPERATURE}, "
          f"max {config.MAX_CORRECTION_ATTEMPTS} attempts)\n")

    fixed, failed = [], []
    attempts_hist = Counter()
    fixed_by_defect, failed_by_defect, shrank = Counter(), Counter(), 0
    n_error = 0

    for i, env in enumerate(invalids, 1):
        res = correct_one(env)
        defect = (env.get("injected_defect") or {}).get("type", "organic")
        if res["status"] == "fixed":
            fixed.append(res["record"])
            attempts_hist[res["attempts"]] += 1
            fixed_by_defect[defect] += 1
            shrank += int(res["structure_shrank"])
            mark = "✓" + (" (shrank!)" if res["structure_shrank"] else "")
        elif res["status"] == "failed":
            failed.append(res)
            failed_by_defect[defect] += 1
            mark = "✗ failed"
        else:
            n_error += 1
            mark = "! error"
        print(f"[{i:2d}/{len(invalids)}] {defect:18s} attempt {res['attempts']} -> {mark}")

    n_fixed, n_failed = len(fixed), len(failed)
    success_rate = n_fixed / len(invalids) if invalids else 0.0
    avg_attempts = (sum(a * c for a, c in attempts_hist.items()) / n_fixed) if n_fixed else 0.0

    # Final valid dataset = originally-valid resumes + freshly-corrected ones (for step4).
    valid_resumes = _read_jsonl(config.VALIDATED_DIR / f"valid_resumes_{ts}.jsonl")
    final_valid = valid_resumes + fixed
    post_rate = len(final_valid) / (len(valid_resumes) + len(invalids)) if invalids else 1.0

    out = config.VALIDATED_DIR
    _write_jsonl(fixed, out / f"corrected_resumes_{ts}.jsonl")
    _write_jsonl(failed, out / f"failed_resumes_{ts}.jsonl")
    _write_jsonl(final_valid, out / f"final_valid_resumes_{ts}.jsonl")

    report = {
        "corrected_at": _now_iso(),
        "source_timestamp": ts,
        "invalid_in": len(invalids),
        "fixed": n_fixed, "failed": n_failed, "errored": n_error,
        "success_rate": round(success_rate, 4),
        "avg_attempts_to_fix": round(avg_attempts, 2),
        "attempts_histogram": dict(sorted(attempts_hist.items())),
        "fixed_by_defect": dict(fixed_by_defect.most_common()),
        "failed_by_defect": dict(failed_by_defect.most_common()),
        "deletion_cheats": shrank,
        "valid_before": len(valid_resumes),
        "valid_after": len(final_valid),
        "post_correction_valid_rate": round(post_rate, 4),
    }
    (out / f"correction_report_{ts}.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    # ── Summary ──────────────────────────────────────────────────────────
    print("\n" + "=" * 56)
    print(f"FIXED {n_fixed}/{len(invalids)}  ({100*success_rate:.1f}% success"
          f"  |  target >50%  |  {'PASS' if success_rate > 0.50 else 'MISS'})")
    print(f"failed={n_failed}  errored={n_error}  avg attempts to fix={avg_attempts:.2f}")
    print(f"attempts histogram (fixed): {dict(sorted(attempts_hist.items()))}")
    if shrank:
        print(f"WARNING: {shrank} fix(es) shrank a list (possible deletion cheat) — inspect.")
    if failed_by_defect:
        print(f"unfixed by defect: {dict(failed_by_defect.most_common())}")
    print(f"\nValidation rate: {100*len(valid_resumes)/(len(valid_resumes)+len(invalids)):.1f}% raw "
          f"-> {100*post_rate:.1f}% post-correction  (metric #2 target >90%: "
          f"{'PASS' if post_rate > 0.90 else 'MISS'})")
    print(f"\nWrote corrected_/failed_/final_valid_resumes_{ts}.jsonl + correction_report_{ts}.json")


def main() -> None:
    import argparse

    p = argparse.ArgumentParser(description="Step 3 — LLM correction loop for invalid resumes.")
    p.add_argument("--timestamp", default=None, help="validated run timestamp (default: latest)")
    args = p.parse_args()
    run(timestamp=args.timestamp)


if __name__ == "__main__":
    main()
