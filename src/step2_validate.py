"""Step 2 — Validation gate. LOCAL compute, no API calls (fast + free).

Reads the latest generated jobs/resumes/pairs, parses every record against the STRICT
domain schemas (`schemas.py`), and splits them:

    valid   → data/validated/valid_*.jsonl     (clean, ready for step4 labeling)
    invalid → data/validated/invalid_*.jsonl   (record + extracted errors, ready for
                                                 the step3 correction loop)

Every error is sorted into a documented 4-bucket taxonomy (metric #2: "errors
categorized"). Because generation stamped `metadata.injected_defect` as ground truth,
we can AUTO-VERIFY the categorizer: each injected defect has a known expected category,
so we report categorization agreement instead of eyeballing it.

Error categories (the 4 buckets):
    invalid_format       value can't be parsed into the expected type   (ISO date, email)
    out_of_range         numeric value outside allowed bounds           (GPA, exp years)
    invalid_value        value not in the allowed set                   (proficiency enum)
    constraint_violation field/cross-field rule fails                   (phone len, end<start,
                                                                          missing, too short)
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timezone

from pydantic import ValidationError

from . import config
from .schemas import JobDescription, Resume

# ── Error categorization ─────────────────────────────────────────────────
# Maps a Pydantic v2 error (type + field path) to one of the 4 buckets. `value_error`
# is ambiguous (EmailStr, the phone validator, and the end>start validator all raise it),
# so we disambiguate by the field it fired on.
_OUT_OF_RANGE = {"greater_than", "greater_than_equal", "less_than", "less_than_equal", "multiple_of"}
_FORMAT_TYPES = {"date_parsing", "date_from_datetime_parsing", "datetime_parsing",
                 "datetime_from_date_parsing", "int_parsing", "float_parsing"}
_CONSTRAINT_TYPES = {"missing", "string_too_short", "string_too_long",
                     "string_pattern_mismatch", "too_short", "too_long"}


def categorize(err: dict) -> str:
    t = err.get("type", "")
    loc = ".".join(str(p) for p in err.get("loc", ()))
    if t in _FORMAT_TYPES:
        return "invalid_format"
    if t == "enum":
        return "invalid_value"
    if t in _OUT_OF_RANGE:
        return "out_of_range"
    if t in _CONSTRAINT_TYPES:
        return "constraint_violation"
    if t == "value_error":
        return "invalid_format" if "email" in loc else "constraint_violation"
    return "other"  # safety net — logged so we notice an unmapped type


# Ground-truth: which category each injected defect SHOULD land in.
_EXPECTED_CATEGORY = {
    "present_end_date": "invalid_format",
    "non_iso_date": "invalid_format",
    "gpa_out_of_range": "out_of_range",
    "invalid_email": "invalid_format",
    "bad_proficiency": "invalid_value",
    "short_phone": "constraint_violation",
    "end_before_start": "constraint_violation",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_jsonl(records, path) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")


def _latest_timestamp() -> str:
    files = sorted(config.GENERATED_DIR.glob("jobs_*.jsonl"))
    if not files:
        raise FileNotFoundError("No generated jobs_*.jsonl found — run step1 first.")
    return files[-1].stem[len("jobs_"):]


def validate_records(records: list[dict], model) -> tuple[list[dict], list[dict]]:
    """Split records into (valid, invalid). Invalid entries carry extracted+categorized
    errors and the injected-defect ground truth, shaped for the correction loop."""
    valid, invalid = [], []
    for r in records:
        try:
            model.model_validate(r)
            valid.append(r)
        except ValidationError as exc:
            errors = [{
                "loc": ".".join(str(p) for p in e["loc"]),
                "type": e["type"],
                "category": categorize(e),
                "msg": e["msg"],
            } for e in exc.errors()]
            meta = r.get("metadata", {})
            invalid.append({
                "trace_id": meta.get("trace_id"),
                "injected_defect": meta.get("injected_defect"),  # ground truth (may be None)
                "errors": errors,
                "record": r,
            })
    return valid, invalid


def run(*, timestamp: str | None = None) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    config.ensure_dirs()
    ts = timestamp or _latest_timestamp()
    print(f"Validating generation run: {ts}\n")

    jobs = _read_jsonl(config.GENERATED_DIR / f"jobs_{ts}.jsonl")
    resumes = _read_jsonl(config.GENERATED_DIR / f"resumes_{ts}.jsonl")
    pairs = _read_jsonl(config.GENERATED_DIR / f"pairs_{ts}.jsonl")

    valid_jobs, invalid_jobs = validate_records(jobs, JobDescription)
    valid_resumes, invalid_resumes = validate_records(resumes, Resume)

    # A pair is usable for labeling only if BOTH sides are valid.
    valid_job_ids = {j["metadata"]["trace_id"] for j in valid_jobs}
    valid_res_ids = {r["metadata"]["trace_id"] for r in valid_resumes}
    valid_pairs, invalid_pairs = [], []
    for p in pairs:
        (valid_pairs if (p["job_trace_id"] in valid_job_ids and p["resume_trace_id"] in valid_res_ids)
         else invalid_pairs).append(p)

    # ── Write outputs (timestamped, linked to the source run — Rule #9) ──
    out = config.VALIDATED_DIR
    _write_jsonl(valid_jobs, out / f"valid_jobs_{ts}.jsonl")
    _write_jsonl(invalid_jobs, out / f"invalid_jobs_{ts}.jsonl")
    _write_jsonl(valid_resumes, out / f"valid_resumes_{ts}.jsonl")
    _write_jsonl(invalid_resumes, out / f"invalid_resumes_{ts}.jsonl")
    _write_jsonl(valid_pairs, out / f"valid_pairs_{ts}.jsonl")
    _write_jsonl(invalid_pairs, out / f"invalid_pairs_{ts}.jsonl")

    # ── Error-category breakdown (across all invalid resumes + jobs) ─────
    cat_counts = Counter()
    for inv in invalid_resumes + invalid_jobs:
        for e in inv["errors"]:
            cat_counts[e["category"]] += 1

    # ── Ground-truth verification of the categorizer ─────────────────────
    checked = matched = 0
    for inv in invalid_resumes:
        defect = inv["injected_defect"]
        if not defect:
            continue
        expected = _EXPECTED_CATEGORY.get(defect["type"])
        got = {e["category"] for e in inv["errors"]}
        checked += 1
        if expected in got:
            matched += 1
    agreement = (matched / checked) if checked else 0.0

    def rate(v, n):
        return v / n if n else 0.0

    report = {
        "validated_at": _now_iso(),
        "source_timestamp": ts,
        "jobs": {"total": len(jobs), "valid": len(valid_jobs), "invalid": len(invalid_jobs),
                 "valid_rate": round(rate(len(valid_jobs), len(jobs)), 4)},
        "resumes": {"total": len(resumes), "valid": len(valid_resumes), "invalid": len(invalid_resumes),
                    "valid_rate": round(rate(len(valid_resumes), len(resumes)), 4)},
        "pairs": {"total": len(pairs), "valid": len(valid_pairs), "invalid": len(invalid_pairs),
                  "valid_rate": round(rate(len(valid_pairs), len(pairs)), 4)},
        "error_categories": dict(cat_counts.most_common()),
        "categorizer_ground_truth": {"checked": checked, "matched": matched,
                                     "agreement": round(agreement, 4)},
    }
    (out / f"validation_report_{ts}.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    # ── Console summary ──────────────────────────────────────────────────
    print(f"JOBS    {len(valid_jobs):3d}/{len(jobs):3d} valid ({100*rate(len(valid_jobs),len(jobs)):.1f}%)")
    print(f"RESUMES {len(valid_resumes):3d}/{len(resumes):3d} valid "
          f"({100*rate(len(valid_resumes),len(resumes)):.1f}%)  -> {len(invalid_resumes)} to correct")
    print(f"PAIRS   {len(valid_pairs):3d}/{len(pairs):3d} usable for labeling")
    print("\nError categories (across invalid records):")
    for cat, c in cat_counts.most_common():
        print(f"  {cat:22s} {c:3d}")
    if cat_counts.get("other"):
        print("  WARNING: 'other' means an unmapped Pydantic error type — extend categorize().")
    print(f"\nCategorizer vs. injected ground truth: {matched}/{checked} = "
          f"{100*agreement:.1f}% agreement")
    print(f"\nWrote validated/*_{ts}.jsonl + validation_report_{ts}.json")


def main() -> None:
    import argparse

    p = argparse.ArgumentParser(description="Step 2 — strict validation gate (local, no API).")
    p.add_argument("--timestamp", default=None,
                   help="generation run timestamp to validate (default: latest)")
    args = p.parse_args()
    run(timestamp=args.timestamp)


if __name__ == "__main__":
    main()
