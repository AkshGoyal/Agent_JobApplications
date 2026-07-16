"""Gmail alert ingestion — FakeIMAP + mocked LLM, fully offline.

Tests must never open a live IMAP connection or hit the live API.
"""

from email.message import EmailMessage

import pytest

import config
from db import repo
from sources import gmail_alerts
from sources.gmail_alerts import AlertJob, AlertJobsResult
from tests.conftest import FakeLLMClient, make_response

ALERT_HTML = """
<html><head><style>body{font:14px}</style></head><body>
<h2>Your job alert for AI Engineer</h2>
<table>
  <tr><td>
    <a href="https://www.linkedin.com/comm/jobs/view/4001">AI Engineer</a>
    <p>Acme AI Labs · Bengaluru, Karnataka, India</p>
    <p>Build production RAG systems with hybrid retrieval.</p>
  </td></tr>
  <tr><td>
    <a href="https://www.linkedin.com/comm/jobs/view/4002">GenAI Product Manager</a>
    <p>Beta Robotics · Remote</p>
  </td></tr>
</table>
<p><a href="https://www.linkedin.com/unsubscribe">Unsubscribe</a></p>
</body></html>
"""

EXTRACTED = AlertJobsResult(
    jobs=[
        AlertJob(
            company_name="Acme AI Labs",
            title="AI Engineer",
            location="Bengaluru, Karnataka, India",
            job_url="https://www.linkedin.com/comm/jobs/view/4001",
            snippet="Build production RAG systems with hybrid retrieval.",
        ),
        AlertJob(
            company_name="Beta Robotics",
            title="GenAI Product Manager",
            location="Remote",
            job_url=None,
            snippet="",
        ),
    ]
)


def _alert_message(html: str = ALERT_HTML) -> bytes:
    msg = EmailMessage()
    msg["From"] = f"LinkedIn Job Alerts <{config.ALERT_SENDER}>"
    msg["To"] = "user@example.com"
    msg["Subject"] = "8 new jobs for AI Engineer"
    msg["Date"] = "Mon, 14 Jul 2026 08:00:00 +0000"
    msg.set_content("Plain-text fallback")
    msg.add_alternative(html, subtype="html")
    return msg.as_bytes()


class FakeIMAP:
    """Mimics the slice of imaplib.IMAP4_SSL that fetch_alert_emails uses.
    Records every call so tests can assert the mailbox was opened read-only."""

    def __init__(self, messages: list[bytes]):
        self._messages = messages
        self.calls = []

    def select(self, mailbox, readonly=False):
        self.calls.append(("select", mailbox, readonly))
        return "OK", [b""]

    def search(self, charset, *criteria):
        self.calls.append(("search", charset, criteria))
        uids = b" ".join(str(i + 1).encode() for i in range(len(self._messages)))
        return "OK", [uids]

    def fetch(self, uid, parts):
        self.calls.append(("fetch", uid, parts))
        idx = int(uid.decode()) - 1
        return "OK", [(b"", self._messages[idx])]

    def logout(self):
        self.calls.append(("logout",))


def test_fetch_parses_html_and_opens_readonly():
    imap = FakeIMAP([_alert_message()])
    emails = gmail_alerts.fetch_alert_emails(imap=imap)

    assert ("select", "INBOX", True) in imap.calls  # read-only, always
    # injected connection is not logged out by us
    assert ("logout",) not in imap.calls

    assert len(emails) == 1
    assert emails[0].subject == "8 new jobs for AI Engineer"
    # HTML stripped to text, job links preserved, style content dropped
    assert "Acme AI Labs" in emails[0].text
    assert "https://www.linkedin.com/comm/jobs/view/4001" in emails[0].text
    assert "font:14px" not in emails[0].text


def test_search_filters_by_alert_sender():
    imap = FakeIMAP([])
    gmail_alerts.fetch_alert_emails(imap=imap)
    search_call = [c for c in imap.calls if c[0] == "search"][0]
    assert config.ALERT_SENDER in search_call[2]


def test_ingest_alerts_stores_jobs_with_gmail_source(conn):
    imap = FakeIMAP([_alert_message()])
    client = FakeLLMClient(make_response(EXTRACTED))

    result = gmail_alerts.ingest_alerts(conn, imap=imap, client=client)

    assert result.emails_scanned == 1
    assert len(result.new_job_ids) == 2
    assert result.duplicates == 0

    first = repo.get_job(conn, result.new_job_ids[0])
    assert first["source"] == "gmail_alert"
    assert first["company_name"] == "Acme AI Labs"
    assert first["source_url"] == "https://www.linkedin.com/comm/jobs/view/4001"
    assert "snippet only" in first["description_text"]  # honesty marker

    # A job without a link still gets a stable non-fetchable label.
    second = repo.get_job(conn, result.new_job_ids[1])
    assert second["source_url"].startswith("gmail-alert://")
    assert second["description_text"].startswith("GenAI Product Manager at Beta Robotics")


def test_ingest_alerts_rerun_reports_duplicates_not_reinserts(conn):
    imap = FakeIMAP([_alert_message()])
    client = FakeLLMClient(make_response(EXTRACTED))
    first = gmail_alerts.ingest_alerts(conn, imap=imap, client=client)

    rerun = gmail_alerts.ingest_alerts(
        conn, imap=FakeIMAP([_alert_message()]), client=FakeLLMClient(make_response(EXTRACTED))
    )
    assert rerun.new_job_ids == []
    assert rerun.duplicates == 2
    assert len(repo.list_jobs(conn)) == len(first.new_job_ids)


def test_ingest_alerts_empty_inbox(conn):
    result = gmail_alerts.ingest_alerts(
        conn, imap=FakeIMAP([]), client=FakeLLMClient(make_response(None))
    )
    assert result.emails_scanned == 0
    assert result.new_job_ids == [] and result.duplicates == 0


def test_extraction_uses_extract_model_and_email_content():
    client = FakeLLMClient(make_response(EXTRACTED))
    alert = gmail_alerts.AlertEmail(subject="S", date="D", text="email body text")
    gmail_alerts.extract_alert_jobs(alert, client=client)
    assert client.calls[-1]["model"] == config.MODEL_EXTRACT
    assert "email body text" in client.last_prompt


def test_fetch_without_credentials_raises_clear_error(monkeypatch):
    monkeypatch.delenv(config.GMAIL_ADDRESS_ENV_VAR, raising=False)
    monkeypatch.delenv(config.GMAIL_APP_PASSWORD_ENV_VAR, raising=False)
    with pytest.raises(ValueError, match="Gmail is not configured"):
        gmail_alerts.fetch_alert_emails()
