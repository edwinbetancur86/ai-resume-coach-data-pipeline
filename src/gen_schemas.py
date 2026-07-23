"""Lenient GENERATION schemas — the loose half of the two-layer design (decision #10).

These are the shapes we hand to Instructor when *asking* the LLM for content. They
mirror the field NAMES of the strict domain models in `schemas.py` so a generated
record slots straight into the strict validator later — but they deliberately DROP the
business-rule constraints:

    strict (schemas.py)                 lenient (here)
    ─────────────────────               ─────────────────────
    experience_years: int, 0..30   →    experience_years: int   (no bounds → 45 slips through)
    name/education: min_length=1   →    plain str               (empty string slips through)
    metadata: JobMetadata          →    (omitted entirely)      (our code stamps it, not the LLM)

WHY loose: if Instructor enforced the strict model, it would re-prompt until ~100 % of
records were valid — leaving the validation gate (step2) and correction loop (step3)
with nothing to act on. The gap between "structurally reliable" and "domain-valid" is
what manufactures the invalid records the deliverable needs.

WHY still slightly constrained: `required_skills` stays non-empty because a job with
zero required skills is meaningless to the whole downstream Jaccard/overlap analysis —
that is a structural necessity, not a business rule we want to test.

WHY no metadata block: `trace_id`, `generated_at`, `is_niche_role` are provenance WE
own (Q2 ownership boundary). Omitting them here makes it structurally impossible for the
model to invent a linking key or self-report a flag we assign.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class GenCompanyInfo(BaseModel):
    name: str
    industry: str
    size: str
    location: str


class GenJobRequirements(BaseModel):
    required_skills: list[str] = Field(min_length=1)  # ≥1 is structural, not a rule under test
    preferred_skills: list[str] = Field(default_factory=list)
    education: str
    experience_years: int      # no 0..30 bound → out-of-range values reach the strict gate
    experience_level: str


class GenJobDescription(BaseModel):
    """Loose job shape: title + company + requirements. Metadata is attached by our
    pipeline code after generation, never produced by the model."""

    title: str
    company: GenCompanyInfo
    requirements: GenJobRequirements
