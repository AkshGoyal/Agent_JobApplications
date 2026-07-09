You are extracting structured fields from a job posting that was manually
copied from a job board (usually LinkedIn) by the user.

Job posting URL: {{url}}
Today's date: {{today}}

Job description text, pasted verbatim:
<job_description>
{{jd_text}}
</job_description>

Extract these fields from the text:

- company_name: the hiring company's name as written in the posting.
- title: the job title as written.
- location: city/region as written (e.g. "Bengaluru, Karnataka, India");
  null if no location is stated.
- remote_type: one of "onsite", "hybrid", "remote", or "unknown" if the
  posting does not say.
- posted_at: the posting date as an ISO date (YYYY-MM-DD). If the posting
  states a relative time (e.g. "2 weeks ago"), compute it from today's date.
  Null if no date information is present.

Rules:
- Use only information present in the pasted text (the URL may help confirm
  the company name, but never invent details not supported by the text).
- Do not summarize, rewrite, or embellish anything — extract exactly what is
  written.
