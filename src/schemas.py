"""Strict domain models — the data contract the whole pipeline is built on.

These are the *validation* schemas: every business rule from the spec lives here as
a Pydantic constraint or validator. The validation gate (step2) parses generated
records against these models; anything that violates a rule lands in the invalid
bucket (with a precise error path) and is handed to the correction loop.

DESIGN NOTE — two-layer schemas:
    Generation (step1) targets a *lenient* schema (loose string types) so the LLM
    reliably returns structure but can still violate business rules. These STRICT
    models are what turn those violations into caught, categorized errors. That gap
    is what gives the correction-loop deliverable something to fix. See CLAUDE.md §1.

Everything is bottom-up: enums → leaf models (Contact, Education, Experience, Skill)
→ metadata → the three top-level documents (Resume, JobDescription, ResumePair).
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from . import config


# ─────────────────────────────────────────────────────────────────────────
# Enums — closed value sets. Using enums means the LLM writing "Grandmaster"
# for a proficiency level is a *validation error*, not silent bad data.
# ─────────────────────────────────────────────────────────────────────────
class ProficiencyLevel(str, Enum):
    beginner = "Beginner"
    intermediate = "Intermediate"
    advanced = "Advanced"
    expert = "Expert"


class FitLevel(str, Enum):
    excellent = "excellent"
    good = "good"
    partial = "partial"
    poor = "poor"
    mismatch = "mismatch"


class WritingStyle(str, Enum):
    formal_corporate = "formal_corporate"
    casual_startup = "casual_startup"
    technical_detailed = "technical_detailed"
    achievement_focused = "achievement_focused"
    career_changer = "career_changer"


# Shared config: strip whitespace on all string fields; ignore unknown extras
# (extra keys aren't one of the spec's 4 error categories, so we don't punish them).
_MODEL_CONFIG = ConfigDict(str_strip_whitespace=True, extra="ignore")


# ─────────────────────────────────────────────────────────────────────────
# Leaf models
# ─────────────────────────────────────────────────────────────────────────
class ContactInfo(BaseModel):
    model_config = _MODEL_CONFIG

    name: str = Field(min_length=1)
    email: EmailStr                      # RFC-valid email or it's a format violation
    phone: str
    location: str = Field(min_length=1)
    linkedin: Optional[str] = None       # optional per spec
    portfolio: Optional[str] = None

    @field_validator("phone")
    @classmethod
    def phone_min_length(cls, v: str) -> str:
        """Spec rule: phone must be ≥10 characters (format violation otherwise)."""
        if len(v.strip()) < config.PHONE_MIN_LENGTH:
            raise ValueError(f"phone must be at least {config.PHONE_MIN_LENGTH} characters")
        return v


class Education(BaseModel):
    model_config = _MODEL_CONFIG

    degree: str = Field(min_length=1)
    institution: str = Field(min_length=1)
    graduation_date: date                # `date` type only accepts ISO (YYYY-MM-DD)
    # GPA bounds enforced by Field; None is allowed (optional field).
    gpa: Optional[float] = Field(default=None, ge=config.GPA_MIN, le=config.GPA_MAX)
    coursework: list[str] = Field(default_factory=list)


class Experience(BaseModel):
    model_config = _MODEL_CONFIG

    company: str = Field(min_length=1)
    title: str = Field(min_length=1)
    start_date: date
    end_date: Optional[date] = None      # None = current role
    responsibilities: list[str] = Field(default_factory=list)
    achievements: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def end_after_start(self) -> "Experience":
        """Logical-consistency rule: end_date (if present) must be after start_date."""
        if self.end_date is not None and self.end_date <= self.start_date:
            raise ValueError("end_date must be after start_date")
        return self


class Skill(BaseModel):
    model_config = _MODEL_CONFIG

    name: str = Field(min_length=1)
    proficiency_level: ProficiencyLevel
    years: Optional[float] = Field(default=None, ge=0, le=50)


# ─────────────────────────────────────────────────────────────────────────
# Metadata — set by OUR pipeline code, never invented by the LLM. Keeping it a
# separate nested object makes clear which fields the model owns vs. which we own.
# ─────────────────────────────────────────────────────────────────────────
class ResumeMetadata(BaseModel):
    model_config = _MODEL_CONFIG

    trace_id: str = Field(min_length=1)
    generated_at: datetime
    prompt_template: str                 # template id/version used (e.g. "resume_v1")
    fit_level: FitLevel                  # the *intended* fit vs. its paired job
    writing_style: WritingStyle


class JobMetadata(BaseModel):
    model_config = _MODEL_CONFIG

    trace_id: str = Field(min_length=1)
    generated_at: datetime
    is_niche_role: bool                  # flag for the niche-vs-standard analysis


# ─────────────────────────────────────────────────────────────────────────
# Job-side composite pieces
# ─────────────────────────────────────────────────────────────────────────
class CompanyInfo(BaseModel):
    model_config = _MODEL_CONFIG

    name: str = Field(min_length=1)
    industry: str = Field(min_length=1)
    size: str = Field(min_length=1)      # free-form ("startup", "500+ employees")
    location: str = Field(min_length=1)


class JobRequirements(BaseModel):
    model_config = _MODEL_CONFIG

    required_skills: list[str] = Field(min_length=1)   # at least one required skill
    preferred_skills: list[str] = Field(default_factory=list)
    education: str = Field(min_length=1)               # e.g. "BS in Computer Science"
    experience_years: int = Field(ge=config.EXPERIENCE_YEARS_MIN, le=config.EXPERIENCE_YEARS_MAX)
    experience_level: str = Field(min_length=1)        # "Entry"/"Senior"/… (mapped in labeler)


# ─────────────────────────────────────────────────────────────────────────
# Top-level documents
# ─────────────────────────────────────────────────────────────────────────
class Resume(BaseModel):
    model_config = _MODEL_CONFIG

    contact: ContactInfo
    summary: Optional[str] = None        # free-text; scanned for buzzwords (F6)
    education: list[Education] = Field(default_factory=list)
    experience: list[Experience] = Field(default_factory=list)
    skills: list[Skill] = Field(min_length=1)          # a resume must list ≥1 skill
    metadata: ResumeMetadata


class JobDescription(BaseModel):
    model_config = _MODEL_CONFIG

    title: str = Field(min_length=1)     # the role title (e.g. "Senior Backend Engineer")
    company: CompanyInfo
    requirements: JobRequirements
    metadata: JobMetadata


class ResumePair(BaseModel):
    """Links one resume to one job. Self-contained (embeds both) so the labeler and
    the API can operate on a single record without cross-file lookups."""

    model_config = _MODEL_CONFIG

    pair_id: str = Field(min_length=1)
    fit_level: FitLevel                  # intended fit (mirrors resume.metadata.fit_level)
    resume: Resume
    job: JobDescription
    generated_at: datetime
