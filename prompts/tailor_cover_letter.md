You are drafting a cover letter for a specific job application. This is a
draft the candidate will read, edit, and personalize before sending — write
it in their voice, grounded only in the facts given below.

<candidate_profile>
{{profile_context}}
</candidate_profile>

<job>
Company: {{company}}
Title: {{title}}

Description:
{{jd_text}}
</job>

Produce:
- subject: a short line, e.g. "Application for {{title}} — {{company}}".
- body: the letter body (3–4 short paragraphs). Do NOT include a salutation
  line ("Dear Hiring Manager") or a sign-off/signature — those are added
  separately. Open by connecting the candidate's background to this specific
  role and company; use 1–2 concrete, specific examples from the profile
  (not generic claims); close with genuine interest in the role.
- facts_used: a short list of the specific profile facts/claims the letter
  relies on (e.g. "Aspect Ratio RAG system", "GEO optimization 41% citation
  lift") — this is a self-audit trail the candidate will use to double-check
  nothing was invented.

Hard rules:
- Every claim, project, metric, or skill mentioned must come from
  `<candidate_profile>` above. Never invent experience, a metric, or a skill
  not present there.
- Do not state or imply a CGPA, dates, or title different from what's given.
- Keep it specific to this job and company — avoid generic filler that could
  apply to any application.
