# resume-coach-data-pipeline

A production-grade synthetic-data pipeline that **generates** resume ↔ job-description
pairs at controlled quality levels, **validates** them with Pydantic, **labels** each
pair with six rule-based failure metrics, **self-corrects** invalid records via an LLM
feedback loop, **visualizes** the failure patterns, and **serves** the analysis through
a FastAPI REST API.

> Bootcamp mini-project (AI Accelerator Bootcamp). Python · OpenRouter · Instructor +
> Pydantic · pandas · matplotlib/seaborn · FastAPI.

## Success targets

| Metric | Target |
|--------|--------|
| Data volume | ≥ 50 jobs, ≥ 250 pairs, all 5 fit levels + 5 templates |
| Schema validation | > 90 % valid |
| Correction success | > 50 % within ≤ 3 attempts |
| API latency | < 2 s (no judge) · < 10 s (with judge) |

## Setup

```bash
# 1. Create + activate a virtual environment
python -m venv .venv
.venv\Scripts\activate          # Windows PowerShell
# source .venv/bin/activate     # macOS/Linux

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure your API key
copy .env.example .env          # Windows  (cp on macOS/Linux)
#   then edit .env and paste your real OPENROUTER_API_KEY
```

## Running the pipeline

```bash
python -m src.step1_generate --jobs 50 --resumes-per-job 6   # generate (API)
python -m src.step2_validate                                 # Pydantic gate
python -m src.step3_correct                                  # correction loop (API)
python -m src.step4_label                                    # 6 failure metrics
python -m src.step5_judge --enabled                          # LLM judge (optional, API)
python -m src.step6_analyze                                  # metrics + summary
python -m src.step7_visualize                                # charts

uvicorn api.main:app --reload                                # API — docs at /docs
```

## Architecture & context

See [`CLAUDE.md`](./CLAUDE.md) for full project context and
[`AGENT.md`](./AGENT.md) for the mentoring/working style used to build it.
Decision history lives in [`docs/iteration_log.md`](./docs/iteration_log.md).

_Status: under construction — Phase 0 (scaffolding) complete._
