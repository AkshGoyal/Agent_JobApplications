You are extracting job postings from a LinkedIn job-alert email.

Below is the text content of one email from LinkedIn's job alerts. It
typically lists several recommended jobs, each with a title, company,
location, and sometimes a short description snippet and a link.

Extract every distinct job posting you can find. For each job:

- `company_name`: the company offering the job. Required — skip entries
  where you cannot identify the company.
- `title`: the job title. Required — skip entries without one.
- `location`: the location as stated (city/region/"Remote"), or null.
- `job_url`: the LinkedIn URL for that specific job if one is present in the
  text, or null. Copy it exactly — do not construct or guess URLs.
- `snippet`: whatever descriptive text the email gives for this job
  (requirements, blurb, salary line). Empty string if there is none.

Rules:
- Only extract jobs actually present in the email. Never invent entries.
- Ignore navigation text, unsubscribe links, footers, and LinkedIn's own
  promotional content.
- If the email contains no job postings at all, return an empty list.

Email date: {{email_date}}
Email subject: {{email_subject}}

Email text:

{{email_text}}
