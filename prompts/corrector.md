A generated resume failed strict schema validation. Fix ONLY the fields named in the
errors below and return the COMPLETE corrected resume. Preserve every other field exactly
as-is — do not rewrite, summarize, add, or delete unrelated content.

VALIDATION ERRORS TO FIX:
$errors

FORMAT RULES the corrected values must satisfy:
- All dates must be ISO `YYYY-MM-DD` (e.g. 2021-06-15). For an ongoing role, set
  `end_date` to null — never "Present", "Current", or an empty string.
- `end_date` must be AFTER `start_date`.
- `email` must be a valid address (contains "@" and a domain).
- `phone` must be a full number with area code, at least 10 characters.
- Each `proficiency_level` must be exactly one of: Beginner, Intermediate, Advanced, Expert.
- `gpa` must be between 0.0 and 4.0.

Keep the same experience, education, and skills entries (same count, same order) — only
repair the specific invalid values.

RESUME TO FIX (JSON):
$record

Return the corrected resume.
