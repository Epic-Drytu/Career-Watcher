"""Mail integration boundary: drafts are private and can be delivered by a future provider."""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class EmailDraft:
    job_key: str
    recipient: str
    subject: str
    body: str
    resume_path: Path


class MailSender(Protocol):
    """Implement send() in a Gmail, Outlook, or SMTP connector."""

    def send(self, draft: EmailDraft) -> None: ...


def build_draft(job_key: str, company: str, title: str, url: str, recipient: str, resume_path: Path) -> EmailDraft:
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", recipient.strip()):
        raise ValueError("Enter a valid recipient email address")
    if not resume_path.is_file():
        raise ValueError("Upload your resume before preparing an email")
    subject = f"Interest in {title} at {company}"
    body = (f"Hello,\n\nI’m interested in the {title} opportunity at {company}. "
            "I’ve attached my resume for your consideration.\n\n"
            f"Job details: {url}\n\nThank you")
    return EmailDraft(job_key, recipient.strip(), subject, body, resume_path)


def enqueue(conn: sqlite3.Connection, draft: EmailDraft, created_at: str) -> bool:
    cur = conn.execute("""INSERT OR IGNORE INTO email_drafts
        (job_key,recipient,subject,body,resume_path,status,created_at)
        VALUES (?,?,?,?,?,'draft',?)""",
        (draft.job_key, draft.recipient, draft.subject, draft.body, str(draft.resume_path), created_at))
    return cur.rowcount == 1


def dispatch_pending(conn: sqlite3.Connection, sender: MailSender) -> int:
    """Send already prepared drafts through a configured provider; no provider is enabled by default."""
    rows = conn.execute("SELECT draft_id,job_key,recipient,subject,body,resume_path FROM email_drafts WHERE status='draft' ORDER BY draft_id").fetchall()
    sent = 0
    for draft_id, job_key, recipient, subject, body, resume_path in rows:
        sender.send(EmailDraft(job_key, recipient, subject, body, Path(resume_path)))
        conn.execute("UPDATE email_drafts SET status='sent',sent_at=CURRENT_TIMESTAMP WHERE draft_id=?", (draft_id,))
        conn.commit()
        sent += 1
    return sent
