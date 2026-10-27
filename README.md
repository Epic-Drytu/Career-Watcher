# Career Watcher

**A private job-search monitor for roles that fit your resume.** Choose job titles, add supported company career boards or search Adzuna's indexed listings across selected countries, and receive alerts for new matches in Telegram.

Career Watcher runs locally. Resume text and credentials stay on the user's machine; listing descriptions are matched locally against resume keywords. It does not publish collected listings or send applications.

## What it does

- Starts by asking which job roles the user is targeting.
- Monitors direct Greenhouse and Lever job boards and Adzuna's supported country indexes.
- Filters by role and optional location, and labels matches with a weighted resume-keyword-overlap score.
- Tracks seen listings in a local SQLite database and sends newly surfaced matches to Telegram.
- Prepares local recruiter email drafts for review. Email sending is not connected or enabled.
- Supports optional, opt-in presence reports to a separately hosted owner dashboard. Presence sharing is off by default.

## Quick start

### Docker

Install Docker Desktop or Docker Engine, then run this from the project root:

```sh
./setup-and-run.sh
```

The script offers to install Docker when needed, builds the image, and prompts before launching the app. Open the private `127.0.0.1` link printed in the terminal. Press Ctrl+C to stop. The named Docker volume `career-watcher-data` preserves settings, resume, and match history between launches.

### Without Docker

Python 3.10 or newer is required.

```sh
python3 -m jobwatcher.app ui
```

On macOS, `start.command` can be double-clicked. On Windows, run `start.bat`; on Linux, run `./start.sh`.

## First-time setup

1. Enter target titles such as `SRE intern`, `Site Reliability Engineer`, or `Platform Engineer`.
2. Upload a PDF or DOCX resume. The file is kept locally; PDF text extraction uses `pdftotext` when available.
3. Choose locations and search sources. For broad indexed search, add Adzuna API credentials and select countries. For direct monitoring, add supported Greenhouse or Lever career-board URLs.
4. Create a Telegram bot, enter its token and chat ID, and use **Send test alert**.
5. Save the setup and run **Check for new jobs**. The first successful check alerts on matching listings it finds; later checks alert on newly surfaced listing IDs.

Review [source terms and data handling](docs/terms-and-data.md) before enabling a source. Adzuna searches a finite index of recent ads in selected supported countries; no service guarantees every opening worldwide. Company boards outside the supported public Greenhouse and Lever feeds are not scraped.

## How matching works

The percentage is a weighted overlap between terms extracted from the job description and the user's resume. It is a sorting aid, not an AI judgment, hiring probability, or guarantee of suitability. Resume parsing and scoring happen locally; resume text is not sent to job sources.

## Scheduling

The Docker launcher checks every six hours after setup is complete. Other options include the included GitHub Actions workflow and Linux `systemd` timer. The GitHub Actions workflow skips public repositories so cached listings are not exposed to repository readers; configure its secrets only in an appropriate private repository.

## Privacy and security

- The local web interface binds to `127.0.0.1` and requires a per-launch access key.
- Settings, credentials, resumes, and SQLite state are stored locally with restricted file permissions on supported systems.
- Presence sharing is optional and off by default. When enabled, it sends a user-chosen label, a random installation ID, and presence timestamps to the configured owner service. It does not send resumes, job searches, listings, or API credentials.
- See [SECURITY.md](SECURITY.md) for the protection details and limits.

## Project layout

```text
jobwatcher/       Search, matching, database, email-draft, and local web UI code
config/           Safe example job-search configuration
docs/             Source terms and email integration notes
systemd/          Linux service and timer examples
tests/            Unit tests
Dockerfile        Container image definition
setup-and-run.sh  Docker install/build/launch helper
```

The optional owner dashboard is an independent companion service. It is not required for job monitoring and needs its own always-on host and domain before it can receive check-ins.

## Development

Run the unit tests with:

```sh
python3 -m unittest discover -s tests -v
```

For a command-line check using a local config, copy `config/companies.example.json` to `config/companies.json`, fill in the target roles and sources, then run:

```sh
python3 -m jobwatcher.app run --config config/companies.json
python3 -m jobwatcher.app report
```

Never commit personal configuration, credentials, resumes, or local database files.
