# CLAUDE.md — Project Context for Claude Code

> This file is loaded automatically into Claude Code's context every session.
> It is the project's "single source of truth" so the assistant always knows what
> we're building, how it's structured, and the rules it must follow.

---

## 1. What this project is

**resume-coach-data-pipeline** is a production-grade synthetic-data pipeline that
**generates** realistic resume ↔ job-description pairs at controlled quality levels,
**validates** them against strict Pydantic schemas, **labels** every pair with six
rule-based failure metrics, **self-corrects** invalid records via an LLM feedback
loop, **visualizes** the failure patterns, and **serves** the analysis in real time
through a FastAPI REST service.

It is a bootcamp mini-project and a **portfolio piece** evaluated by instructors and
potential employers. Code clarity, documentation, and reproducibility matter as much
as correctness.

**Unlike Project 1 (DIY Q&A), the "judge" here is mostly DETERMINISTIC Python** —
set math (Jaccard), integer math (seniority levels), and pattern matching
(hallucination / awkward language). The LLM's jobs are *generation*, *correction*,
and an *optional* nuanced judge. That shifts the correctness risk from prompt-tuning
to our own labeling logic, which we verify with a 10-pair manual spot-check.

## 2. Success metrics (the bar we must clear)

| # | Metric | Target |
|---|--------|--------|
| 1 | Data volume | ≥ 50 jobs, 5–10 resumes/job, **≥ 250 pairs**, all 5 fit levels + 5 templates |
| 2 | Schema validation rate | **> 90 %** valid, with errors categorized |
| 3 | Failure labeling | all 6 metrics per pair; **≥ 80 %** manual agreement on 10-pair spot-check |
| 4 | Correction success | **> 50 %** of invalid records fixed within ≤ 3 attempts |
| 5 | API latency | **< 2 s** without judge, **< 10 s** with judge; valid JSON + error handling |

## 3. Tech stack

- **Python 3.10+**
- **OpenRouter** as the LLM provider (OpenAI-compatible endpoint; model-swappable)
- **Instructor + Pydantic** for schema-safe structured output
- **pandas / numpy** for aggregation
- **matplotlib / seaborn** for charts
- **FastAPI + uvicorn** for the REST service
- **python-dotenv** for config, **tenacity** for retries
- **Braintrust / Logfire** (optional) for eval logging + tracing

Config lives in `.env` (git-ignored). Models/temperatures/keys are read from env vars
— see `.env.example`. Tunable thresholds/weights live in `src/config.py`.

## 4. Architecture — runtime data flow

```
generate ─► validate ─┬─► (valid) ───────────────► label ─► analyze ─► visualize
                      └─► (invalid) ─► correct ─► re-validate ─┘
                                                                  ▲
                                     FastAPI service reads label + analyze logic
```

| Module | Role | Output |
|--------|------|--------|
| `src/step1_generate.py` | jobs (niche flag) → fit-controlled resumes → pairs | `data/generated/*.jsonl` |
| `src/step2_validate.py` | Pydantic gate; split valid/invalid; categorize errors | `data/validated/*` |
| `src/step3_correct.py` | feed Pydantic errors back to LLM; ≤3 retries | corrected records + stats |
| `src/step4_label.py` | 6 rule-based failure metrics per pair | `data/labels/failure_labels_*.jsonl` |
| `src/step5_judge.py` | optional LLM-as-judge for subtle issues | judge verdicts |
| `src/step6_analyze.py` | aggregate rates, correlations, `pipeline_summary.json` | `data/reports/*` |
| `src/step7_visualize.py` | the 6 required charts | `visualizations/*.png` |
| `api/main.py` | REST service on top of label + analyze | live JSON responses |

## 5. Data schemas (Pydantic — see `src/schemas.py`)

**Resume:** Contact (name, email, phone, location, +opt linkedin/portfolio) ·
Education (degree, institution, graduation_date, +opt gpa, coursework) ·
Experience[] (company, title, start_date, end_date?, responsibilities, achievements) ·
Skills[] (name, proficiency_level ∈ {Beginner,Intermediate,Advanced,Expert}, +opt years) ·
Metadata (trace_id, generated_at, prompt_template, fit_level, writing_style).

**JobDescription:** Company (name, industry, size, location) ·
Requirements (required_skills[], preferred_skills[], education, experience_years,
experience_level) · Metadata (trace_id, generated_at, is_niche_role).

**ResumePair:** links a resume + job by trace_id, carries the intended fit_level.

**Validation rules:** valid email format · phone ≥ 10 chars · ISO-format dates ·
GPA 0.0–4.0 · experience_years 0–30 · end_date after start_date (if present).

## 6. The 5 fit levels (controlled at generation, verified by Jaccard)

| Fit level | Target skill overlap |
|-----------|----------------------|
| Excellent | 80 %+ |
| Good | 60–80 % |
| Partial | 40–60 % |
| Poor | 20–40 % |
| Mismatch | < 20 % |

Each fit level must be ≥ 15 % of all pairs.

## 7. The 5 writing-style templates (Challenge 1 — diversity)

Formal/corporate · Casual/startup · Technical/detail-heavy · Achievement-focused
(metrics-driven) · Career-changer (transferable skills).

## 8. The 6 failure metrics (rule-based, computed in `step4_label.py`)

| Code | Metric | Flag rule |
|------|--------|-----------|
| F1 | Skills overlap | Jaccard = \|A∩B\| / \|A∪B\| on normalized skills |
| F2 | Experience mismatch | years gap, or < 50 % of required → flag |
| F3 | Seniority mismatch | level diff > 1 (Entry0/Mid1/Senior2/Lead3/Exec4) → flag |
| F4 | Missing core skills | any of job's top-3 required skills absent → flag |
| F5 | Hallucinated skills | e.g. entry-level (<2 yr) claiming "expert" in 10+ skills, 20+ skills mostly "expert", impossible timelines → flag |
| F6 | Awkward language | buzzword density > 5 in a summary, 3+ repeats, AI patterns → flag |

**Skill normalization (Challenge 3, `src/normalize.py`)** is applied before F1/F4:
lowercase → strip version numbers → strip suffixes (`.js`, `developer`, `engineer`).
Without it, Jaccard is artificially low.

## 9. Correction loop (`step3_correct.py`)

Extract error context (field path, type, invalid value, expected format) → build a
correction prompt that includes the specific Pydantic error messages + the original
data → re-validate → up to **3 attempts** then mark permanently failed. Track success
rate, avg attempts, common failure reasons. **Target > 50 %.**

## 10. Repository layout

```
.
├── CLAUDE.md            # this file — project context
├── AGENT.md             # the "AI Senior Engineer" mentor charter + decision log
├── README.md            # human-facing run instructions
├── .env.example         # config template (real .env is git-ignored)
├── requirements.txt
├── src/                 # config, schemas, normalize, one module per pipeline step
├── api/                 # FastAPI service
├── prompts/             # generator (5 styles) + corrector + judge templates (versioned)
├── data/{generated,validated,labels,reports}/
├── visualizations/      # chart PNGs
├── logs/                # per-step logs + raw-response audit trail
└── docs/iteration_log.md
```

## 11. Hard rules (do not violate)

1. **No hardcoded resume/job content.** All content is LLM-generated at runtime.
2. **Never commit secrets.** Keys live only in `.env`.
3. **Prompts are not hardcoded in logic** — they live in `prompts/` (templates with
   variable injection), so variants are swappable and versioned.
4. **Judge/corrector temperature < generator temperature** (near 0 for determinism).
5. **Every threshold/weight change is data-driven** and logged in `docs/iteration_log.md`
   (date → component → change → before/after metric → delta → keep/revert). ≥ 3 entries.
6. **Handle malformed LLM responses gracefully** — retry, log, never crash the run.
7. **Rate-limit**: small delay between API calls; batch with progress tracking.
8. **Every record carries a `trace_id` + timestamp** — essential for linking + debugging.
9. **Timestamped output filenames** (`resumes_{ts}.jsonl`, etc.) so runs don't clobber.
10. **Skill normalization is shared** between generator checks and the labeler — one source.

## 12. Common commands (finalized as modules land)

```bash
pip install -r requirements.txt

# Pipeline (steps 1/3/5 hit the OpenRouter API; 2/4/6/7 are local compute)
python -m src.step1_generate --jobs 50 --resumes-per-job 6
python -m src.step2_validate
python -m src.step3_correct
python -m src.step4_label
python -m src.step5_judge --enabled          # optional
python -m src.step6_analyze
python -m src.step7_visualize

# API
uvicorn api.main:app --reload                # docs at http://127.0.0.1:8000/docs
```

## 13. Working style

See **AGENT.md** — the owner (Edwin, an AI Engineering student) wants decisions, code,
and architecture **explained as we go**, senior-engineer style, to learn and to be able
to defend every choice in an interview.
