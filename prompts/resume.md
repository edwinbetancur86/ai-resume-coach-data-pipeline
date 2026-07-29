You are writing ONE candidate's resume, tailored for the job below.

  Job title:        $job_title
  Required skills:  $required_skills
  Preferred skills: $preferred_skills

SKILL FIT — how closely this candidate should match the job's required skills:
$fit_guidance

WRITING STYLE — the voice and formatting to adopt throughout:
$style_guidance

Write a realistic, internally-consistent resume:
- Contact info must be realistic: a valid email address and a full phone number with
  area code (at least 10 digits, e.g. +1 (415) 555-0132).
- Include a short professional summary.
- Give concrete work experience with responsibilities and quantified achievements.
- List skills, each with a proficiency level and (where natural) years of experience.
  Each `proficiency_level` MUST be exactly one of: Beginner, Intermediate, Advanced, Expert.
- Include education. Format ALL dates (graduation, job start/end) as ISO `YYYY-MM-DD`
  (e.g. 2021-06-15); if only month/year is known, use a plausible day.
- For a CURRENT / ongoing role, set `end_date` to null (omit it). Do NOT write "Present",
  "Current", "Ongoing", "Now", or an empty string — those are not valid dates.

Make the candidate feel like a real person (variety seed: $seed). Do not produce a
generic, template-filler resume.

Return only the fields defined by the response schema.
