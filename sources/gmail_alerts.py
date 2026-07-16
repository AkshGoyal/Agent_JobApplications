"""Gmail job-alert source — reads LinkedIn's job-alert emails from the
user's own inbox, read-only, over IMAP.

Boundary notes (see PROJECT_SPEC.md non-goals):
- This NEVER sends email. The mailbox is opened read-only; nothing is
  marked, moved, or deleted.
- This is not LinkedIn automation: we never log into or fetch linkedin.com.
  We parse emails LinkedIn already delivered to the user, and the job URLs
  found in them are stored as labels only — never fetched.
- Credentials are a Google app password from env vars (config.py); they are
  never stored anywhere.

The LLM's only role is extracting structured job cards from the email text
(same judgment-point pattern as manual paste extraction). Everything else —
IMAP fetch, HTML stripping, dedup, storage — is deterministic code.
"""

import email
import email.policy
import imaplib
import sqlite3
from dataclasses import dataclass, field
from datetime import date, timedelta
from html.parser import HTMLParser

from pydantic import BaseModel

import config
import llm
from pipeline import ingest
from sources.manual_paste import RawPosting

SOURCE_NAME = "gmail_alert"


class AlertJob(BaseModel):
    """One job card extracted from an alert email."""

    company_name: str
    title: str
    location: str | None = None
    job_url: str | None = None  # stored as a label only — never fetched
    snippet: str = ""


class AlertJobsResult(BaseModel):
    """Structured-output contract for the extract_alert_jobs prompt."""

    jobs: list[AlertJob]


@dataclass
class AlertEmail:
    subject: str
    date: str
    text: str


@dataclass
class GmailIngestResult:
    emails_scanned: int
    new_job_ids: list[int] = field(default_factory=list)
    duplicates: int = 0


class _TextExtractor(HTMLParser):
    """Minimal HTML → text: visible text plus href targets (the job links
    live in <a href> attributes, not in the anchor text)."""

    _SKIP = {"script", "style", "head", "title"}

    def __init__(self):
        super().__init__()
        self._chunks: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP:
            self._skip_depth += 1
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self._chunks.append(f" {href} ")

    def handle_endtag(self, tag):
        if tag in self._SKIP and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data):
        if not self._skip_depth and data.strip():
            self._chunks.append(data.strip())

    def text(self) -> str:
        return "\n".join(self._chunks)


def _html_to_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    return parser.text()


def _message_text(msg: email.message.EmailMessage) -> str:
    """Prefer the HTML part (it carries the job links); fall back to plain."""
    html_part = msg.get_body(preferencelist=("html",))
    if html_part is not None:
        return _html_to_text(html_part.get_content())
    plain_part = msg.get_body(preferencelist=("plain",))
    if plain_part is not None:
        return plain_part.get_content()
    return ""


def _connect_imap() -> imaplib.IMAP4_SSL:
    import os

    if not config.gmail_configured():
        raise ValueError(
            f"Gmail is not configured — set {config.GMAIL_ADDRESS_ENV_VAR} and "
            f"{config.GMAIL_APP_PASSWORD_ENV_VAR} (a Google app password; see "
            "CLAUDE.md for setup)."
        )
    imap = imaplib.IMAP4_SSL(config.IMAP_HOST)
    imap.login(
        os.environ[config.GMAIL_ADDRESS_ENV_VAR],
        os.environ[config.GMAIL_APP_PASSWORD_ENV_VAR],
    )
    return imap


def fetch_alert_emails(*, days: int = 7, imap=None) -> list[AlertEmail]:
    """Fetch LinkedIn job-alert emails from the last ``days`` days, read-only.

    ``imap`` is injectable so tests can pass a fake — tests must never open a
    live IMAP connection.
    """
    owns_connection = imap is None
    if imap is None:
        imap = _connect_imap()
    try:
        imap.select("INBOX", readonly=True)  # read-only: nothing is ever marked/moved
        since = (date.today() - timedelta(days=days)).strftime("%d-%b-%Y")
        _status, data = imap.search(None, "FROM", config.ALERT_SENDER, "SINCE", since)
        uids = data[0].split() if data and data[0] else []

        emails: list[AlertEmail] = []
        for uid in uids:
            _status, msg_data = imap.fetch(uid, "(RFC822)")
            raw_bytes = msg_data[0][1]
            msg = email.message_from_bytes(raw_bytes, policy=email.policy.default)
            emails.append(
                AlertEmail(
                    subject=str(msg.get("Subject", "")),
                    date=str(msg.get("Date", "")),
                    text=_message_text(msg),
                )
            )
        return emails
    finally:
        if owns_connection:
            imap.logout()


def extract_alert_jobs(alert: AlertEmail, *, client=None) -> AlertJobsResult:
    """LLM-extract the job cards from one alert email's text."""
    return llm.call(
        "extract_alert_jobs",
        AlertJobsResult,
        client=client,
        model=config.MODEL_EXTRACT,
        email_date=alert.date,
        email_subject=alert.subject,
        email_text=alert.text,
    )


def _to_raw_posting(job: AlertJob, alert: AlertEmail) -> RawPosting:
    import hashlib

    # Alert emails carry a snippet at best, never the full JD — say so in the
    # stored text so a low-information ranking is explainable.
    description = (job.snippet or f"{job.title} at {job.company_name}").strip()
    description += (
        "\n\n[from a LinkedIn job-alert email — snippet only; open the job "
        "and paste the full description to get an accurate ranking]"
    )
    # Jobs without a link still need a unique, stable source_url label for
    # dedup; derive one from the job's identity, clearly marked non-fetchable.
    source_url = job.job_url or (
        "gmail-alert://"
        + hashlib.sha256(
            f"{job.company_name}|{job.title}|{job.location or ''}".lower().encode()
        ).hexdigest()[:16]
    )
    return RawPosting(
        source=SOURCE_NAME,
        source_url=source_url,
        description_text=description,
        company_name=job.company_name,
        title=job.title,
        location=job.location,
        remote_type="unknown",
        posted_at=None,
    )


def ingest_alerts(
    conn: sqlite3.Connection, *, days: int = 7, client=None, imap=None
) -> GmailIngestResult:
    """Fetch alert emails, extract job cards, and store new ones.

    Storage reuses the exact same normalize → dedup → store path as manual
    paste (pipeline.ingest.store_posting), so re-running is always safe —
    previously seen jobs come back as duplicates, never re-inserted.
    """
    alerts = fetch_alert_emails(days=days, imap=imap)
    result = GmailIngestResult(emails_scanned=len(alerts))
    for alert in alerts:
        extracted = extract_alert_jobs(alert, client=client)
        for job in extracted.jobs:
            stored = ingest.store_posting(conn, _to_raw_posting(job, alert))
            if stored.duplicate:
                result.duplicates += 1
            else:
                result.new_job_ids.append(stored.job_id)
    return result
