# Email sender integration point

The app prepares private resume email drafts but does not send email yet. Each draft is tied to one open role and one recipient address entered by the user. The user uploads a PDF or DOCX resume locally; only the local path is attached to the queued draft. The draft subject/body and attachment path live in the local SQLite database.

`jobwatcher.mail.MailSender` is the provider interface. A future Gmail, Microsoft Graph/Outlook, or SMTP connector implements `send(draft: EmailDraft)`. After the user configures that provider, the connector can call `dispatch_pending(conn, sender)` to deliver queued drafts. The mailer should enforce a daily send cap and duplicate-send protection using `job_key`/recipient; it must never discover or scrape recipient addresses itself. Use addresses deliberately supplied by the user, and review the generated message before enabling unattended delivery.

This keeps provider credentials and outbound sending separate from job-feed polling. No mail provider is connected or invoked by this project today.
