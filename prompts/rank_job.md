You are scoring how relevant a job posting is for a specific candidate.

<candidate_profile>
{{profile_context}}
</candidate_profile>

<job>
Company: {{company}}
Title: {{title}}
Location: {{location}}
Remote type: {{remote_type}}

Description:
{{jd_text}}
</job>

Produce:

- score: an integer 0–100 for how relevant this job is to the candidate.
- rationale: 2–3 short lines explaining the score, referencing the specific
  profile facts and job requirements that drove it.

Scoring guidance:
- Weigh the candidate's stated targets heavily: target roles, industries,
  geographies, seniority, and company types. A job matching several targets
  should score high; a job outside them should score low.
- Any stated dealbreaker present in the job → score below 20.
- Then weigh skill/experience fit: how much of the job's requirements are
  covered by the candidate's listed skills, experience, and projects.
- Seniority mismatch (job requires far more experience than the candidate
  has) should substantially lower the score.

Grounding rules:
- Judge fit ONLY from the profile facts provided above. Never assume the
  candidate has skills, experience, or preferences that are not listed.
- The rationale must be specific ("production RAG experience matches the
  retrieval-systems requirement"), not generic ("good fit").
