# Security and privacy

## What the app protects

- The web server binds only to `127.0.0.1`; it is not exposed on the local network.
- Each launch creates a random access key held in process memory. The key is passed in the browser URL fragment, which browsers do not send to the server in HTTP requests. Every data-changing or data-reading API request must include it. The terminal prints the private link; do not share it.
- The local page sets a restrictive Content Security Policy and disables framing, caching, and referrers. API requests must target loopback, any supplied Origin must be loopback, and the per-launch key is required.
- The `data/` directory is mode `700` on POSIX systems. Settings, SQLite state, and uploaded resumes are mode `600`. The app refuses symbolic links for its private data directory, database, settings, and resume paths.
- Telegram and Adzuna credentials are not returned by the settings API. Telegram HTTP errors are sanitized so bot tokens in request URLs are not copied into the UI or run status.
- The app does not collect recruiter email addresses. The user enters each recipient and queues a draft. No email provider is connected and no email is automatically sent.
- Resume parsing and keyword-overlap scoring run locally. Resume text is not sent to Adzuna or company job boards. The stored database contains the score and matched terms for each listing.
- Listings, drafts, credentials, and resumes are not published by the app. The project ignores its local `data/` directory.
- Presence sharing with a separate owner dashboard is off by default and requires an explicit opt-in. When enabled, it sends the user's chosen display label, a random per-installation ID, and service/dashboard/check timestamps over HTTPS. It does not send resumes, job searches, listings, or API credentials. The collector does not store source IP addresses in its database; hosting providers or reverse proxies may keep their own connection logs. The project token authorizes presence ingestion only, not access to the owner dashboard.

## Limits

This is a local personal tool, not a security boundary against malware or another person with access to the same device account. The per-launch access key protects browser endpoints from other web pages and casual local requests, but a process running as your user can inspect files or browser state. Settings and resumes are protected with operating-system file permissions, not application-level encryption. Use your device's disk encryption, keep the operating system and Python updated, and do not share the private browser link.

Without opt-in presence sharing, usage remains local to this installation. Presence labels are user-chosen and are not verified identities. Deploy the companion owner collector separately if remote presence tracking is needed.

Job-board providers receive requests containing search terms, selected countries, and your network address. Telegram receives the job matches sent to your configured chat. A future email provider will receive queued resume attachments and recipient addresses when you connect and enable it. Review provider privacy and retention terms before connecting one.

When adding a mail provider, store OAuth or SMTP credentials in the operating system keychain where possible, require an explicit send enable switch, add daily rate limits and duplicate-send protection, and retain a reviewable send log. Do not send to automatically harvested addresses.
