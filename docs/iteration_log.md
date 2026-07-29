# Iteration Log

Every threshold or configuration change is recorded here with before/after metrics and
a keep/revert decision. Target: ≥ 3 substantive entries by the end of the project.

Format:

| Date | Component | Change | Before Metric | After Metric | Delta | Keep/Revert |
| ---- | --------- | ------ | ------------- | ------------ | ----- | ----------- |

---

| Date | Component | Change | Before | After | Delta | Decision |
| ---- | --------- | ------ | ------ | ----- | ----- | -------- |
| 2026-07-26 | step1 job generation | Added 5-tier seniority steering (cycled per job) after a 10-job pilot showed a monoculture | 10/10 jobs "Senior/5yr" (0 seniority spread → no F3 signal on job side) | Even 20% per tier: Entry/Mid/Senior/Lead/Director, years 1/3/6/10/15 | +4 seniority levels; job-side F3 signal 0→full | **Keep** |
| 2026-07-26 | step1 niche assignment | Re-keyed niche flag from `j%10<3` to per-seniority-cycle | Niche only ever landed on Entry/Mid/Senior (confounded with seniority) | Niche spread evenly across all 5 tiers; still ~30% overall | Decorrelates niche×seniority | **Keep** |
| 2026-07-29 | step1 resume prompt | Measure-first (3 pilots): instructed ISO dates, then null-not-"Present" end_date, then full phone/email + valid proficiency values | Raw resume valid rate **0.3%** (loose dates failed on every resume) | Raw valid **~100%** (fully instructed) | +99.7pp | **Keep** |
| 2026-07-29 | step1 resume generation | Added controlled defect injection: 15% of resumes get 1 known defect from a 7-type menu, ground truth in metadata | Fully-instructed gen is ~100% valid → **0 invalid records** for the correction loop (metric #4 impossible) | Raw valid **~85%**, ~45 varied+categorized invalid records | enables metrics #2 (categorized) + #4 (known ground truth) | **Keep** |
