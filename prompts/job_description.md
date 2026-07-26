You are an expert technical recruiter writing a single, realistic job posting.

Generate ONE job description for a real-world role. Make it specific and internally
consistent:

- SENIORITY: this must be a **$seniority_label**-level role (about $seniority_years years
  of experience). Set `experience_level` to "$seniority_label", make `experience_years`
  fall in that range, and ensure the title reflects that seniority.
- `required_skills` are the genuinely essential, must-have skills for the role.
- `preferred_skills` are nice-to-haves that would strengthen a candidate but are not
  disqualifying if missing.
- `education` should read like a real requirement line (e.g. "BS in Computer Science
  or equivalent experience").
- `size` is free-form company size (e.g. "Seed-stage startup", "500+ employees").

$niche_clause

Produce a role that is distinct and non-generic (variety seed: $seed). Do not repeat a
boilerplate template — vary the industry, stack, and company profile.

Return only the fields defined by the response schema.
