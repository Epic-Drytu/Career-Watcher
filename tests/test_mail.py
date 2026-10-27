import base64
import sqlite3
import tempfile
import unittest
from pathlib import Path

from jobwatcher.app import init_db
from jobwatcher.mail import build_draft, dispatch_pending, enqueue
from jobwatcher.web import LocalApp


class MailDraftTests(unittest.TestCase):
    def test_build_and_dispatch_prepared_draft(self):
        class Sender:
            def __init__(self):
                self.sent = []

            def send(self, draft):
                self.sent.append(draft)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            resume = root / "resume.pdf"
            resume.write_bytes(b"private resume")
            db = init_db(root / "state.sqlite3")
            draft = build_draft("lever:Acme:1", "Acme", "SRE", "https://example.test/1", "recruiter@example.test", resume)
            self.assertTrue(enqueue(db, draft, "2026-10-27T00:00:00+00:00"))
            self.assertFalse(enqueue(db, draft, "2026-10-27T00:00:00+00:00"))
            sender = Sender()
            self.assertEqual(dispatch_pending(db, sender), 1)
            self.assertEqual(sender.sent[0].resume_path, resume)
            self.assertEqual(db.execute("SELECT status FROM email_drafts").fetchone()[0], "sent")
            db.close()

    def test_invalid_email_requires_manual_correction(self):
        with tempfile.TemporaryDirectory() as tmp:
            resume = Path(tmp) / "resume.pdf"
            resume.write_bytes(b"resume")
            with self.assertRaises(ValueError):
                build_draft("x", "Acme", "SRE", "https://example.test", "not-an-email", resume)

    def test_ui_can_queue_resume_email_for_a_saved_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = LocalApp(Path(tmp))
            conn = init_db(app.db_path)
            conn.execute("""INSERT INTO jobs(job_key,company,ats,job_id,title,location,url,description,first_seen,last_seen,is_open)
                VALUES ('lever:Acme:1','Acme','lever','1','SRE','Remote','https://example.test/1','', 'now','now',1)""")
            conn.commit()
            conn.close()
            app.store_resume("resume.pdf", base64.b64encode(b"resume").decode())
            self.assertTrue(app.queue_email("lever:Acme:1", "recruiter@example.test"))
            self.assertEqual(app.drafts()[0]["recipient"], "recruiter@example.test")


if __name__ == "__main__":
    unittest.main()
