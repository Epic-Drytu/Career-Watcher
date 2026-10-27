from __future__ import annotations

import argparse
import html
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable
import xml.etree.ElementTree as ET

USER_AGENT = "CareerWatcher/0.1 (+personal job-search notifier; contact: local user)"
GENERIC_ROLE_WORDS = {"engineer", "engineering", "developer", "development", "intern", "internship", "job", "role", "jobs"}
ROLE_ALIASES = {
    "sre": ["sre", "site reliability", "reliability engineer"],
    "site reliability": ["sre", "site reliability", "reliability engineer"],
    "devops": ["devops", "dev ops", "infrastructure engineer", "infrastructure engineering"],
    "backend": ["backend", "back-end", "server-side"],
    "platform": ["platform engineer", "platform engineering", "platform"],
    "intern": ["intern", "internship", "summer intern"],
}
ADZUNA_COUNTRIES = {
    "gb": "United Kingdom", "us": "United States", "at": "Austria", "au": "Australia",
    "be": "Belgium", "br": "Brazil", "ca": "Canada", "ch": "Switzerland", "de": "Germany",
    "es": "Spain", "fr": "France", "in": "India", "it": "Italy", "mx": "Mexico",
    "nl": "Netherlands", "nz": "New Zealand", "pl": "Poland", "sg": "Singapore", "za": "South Africa",
}


@dataclass(frozen=True)
class Job:
    company: str
    ats: str
    id: str
    title: str
    location: str
    url: str
    description: str = ""
    resume_match: int | None = None
    matched_terms: tuple[str, ...] = ()

    @property
    def key(self) -> str:
        return f"{self.ats}:{self.company}:{self.id}"


def load_config(path: Path) -> dict[str, Any]:
    config = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(config.get("companies"), list):
        raise ValueError("config must contain a companies array")
    for company in config["companies"]:
        if company.get("ats") not in {"greenhouse", "lever"}:
            raise ValueError(f"unsupported ATS for {company.get('name')}: {company.get('ats')}")
        if not company.get("board") or not company.get("name"):
            raise ValueError("each company requires name and board")
    config.setdefault("target_roles", [])
    config.setdefault("locations", [])
    config.setdefault("request_delay_seconds", 1.0)
    config.setdefault("timeout_seconds", 20)
    return config


def resolve_career_url(url: str) -> tuple[str, str]:
    """Resolve supported public company-board URLs into their API board IDs."""
    parsed = urllib.parse.urlparse(url.strip())
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Use a complete HTTPS careers-page URL")
    host = parsed.hostname.lower()
    parts = [urllib.parse.unquote(part) for part in parsed.path.split("/") if part]
    if host in {"boards.greenhouse.io", "job-boards.greenhouse.io"} and parts:
        return "greenhouse", parts[0]
    if host == "jobs.lever.co" and parts:
        return "lever", parts[0]
    if host == "jobs.nvidia.com":
        raise ValueError("NVIDIA's supplied careers page uses Eightfold and has no documented public listings feed in this app. Use Adzuna search for NVIDIA roles or add a supported Greenhouse/Lever board URL.")
    raise ValueError("This portal URL is not a supported public feed yet. Supported URLs are Greenhouse and Lever careers pages.")


def fetch_json(url: str, *, timeout: int = 20, retries: int = 3) -> Any:
    """Fetch JSON politely; retry transient errors and honor Retry-After."""
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            retryable = exc.code == 429 or 500 <= exc.code < 600
            if not retryable or attempt >= retries:
                raise RuntimeError(f"Job source returned HTTP {exc.code}") from exc
            retry_after = exc.headers.get("Retry-After")
            try:
                delay = min(60.0, max(1.0, float(retry_after))) if retry_after else min(30.0, 2**attempt)
            except ValueError:
                delay = min(30.0, 2**attempt)
            time.sleep(delay)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            if attempt >= retries:
                raise
            time.sleep(min(30.0, 2**attempt))


def fetch_company(company: dict[str, str], timeout: int = 20) -> list[Job]:
    ats, board = company["ats"], urllib.parse.quote(company["board"], safe="")
    if ats == "greenhouse":
        url = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"
        payload = fetch_json(url, timeout=timeout)
        jobs = payload.get("jobs", [])
        output = []
        for item in jobs:
            loc = (item.get("location") or {}).get("name", "")
            description = item.get("content", "") or ""
            output.append(Job(company["name"], ats, str(item["id"]), item.get("title", ""), loc,
                              item.get("absolute_url", ""), description))
        return output
    url = f"https://api.lever.co/v0/postings/{board}?mode=json"
    payload = fetch_json(url, timeout=timeout)
    output = []
    for item in payload:
        categories = item.get("categories") or {}
        loc = categories.get("location", "")
        description = "\n".join(filter(None, [item.get("description", ""), item.get("lists", ""), item.get("additional", "")]))
        output.append(Job(company["name"], ats, str(item.get("id", "")), item.get("text", ""), loc,
                          item.get("hostedUrl", ""), description))
    return output


def fetch_adzuna(country: str, role: str, app_id: str, app_key: str, timeout: int = 20) -> list[Job]:
    if country not in ADZUNA_COUNTRIES:
        raise ValueError(f"unsupported Adzuna country: {country}")
    params = urllib.parse.urlencode({"app_id": app_id, "app_key": app_key, "what": role,
                                    "results_per_page": 50, "sort_by": "date", "max_days_old": 30})
    url = f"https://api.adzuna.com/v1/api/jobs/{country}/search/1?{params}"
    payload = fetch_json(url, timeout=timeout)
    output = []
    for item in payload.get("results", []):
        location = (item.get("location") or {}).get("display_name", "")
        company = (item.get("company") or {}).get("display_name", "") or "Company not listed"
        output.append(Job(company, "adzuna", str(item.get("id", "")), item.get("title", ""), location,
                          item.get("redirect_url", ""), item.get("description", "")))
    return output


def role_matches(job: Job, target_roles: Iterable[str]) -> bool:
    """Match target roles against the full description, with title as a useful signal."""
    text = f"{job.title}\n{job.description}".casefold()
    for role in target_roles:
        phrase = role.casefold().strip()
        if not phrase:
            continue
        aliases = ROLE_ALIASES.get(phrase, [phrase])
        if any(alias in text for alias in aliases):
            return True
        tokens = [word for word in re.findall(r"[a-z0-9]+", phrase) if word not in GENERIC_ROLE_WORDS]
        if tokens:
            present = sum(token in text for token in tokens)
            needed = 1 if len(tokens) == 1 else (len(tokens) + 1) // 2
            if present >= needed:
                return True
    return False


def matches(job: Job, target_roles: Iterable[str], locations: Iterable[str]) -> bool:
    location = job.location.casefold()
    location_values = [loc.casefold() for loc in locations]
    location_match = not location_values or any(loc in location for loc in location_values)
    return bool(role_matches(job, target_roles) and location_match)


class _HTMLText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self.skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"} and self.skip:
            self.skip -= 1

    def handle_data(self, data: str) -> None:
        if not self.skip:
            self.parts.append(data)


def plain_text(value: str) -> str:
    parser = _HTMLText()
    try:
        parser.feed(html.unescape(html.unescape(value or "")))
        return " ".join(" ".join(parser.parts).split())
    except Exception:
        return value or ""


def extract_resume_text(path: Path) -> str:
    """Extract resume text locally; never sends resume contents to a service."""
    if path.suffix.lower() == ".docx":
        try:
            with zipfile.ZipFile(path) as archive:
                xml = archive.read("word/document.xml")
            root = ET.fromstring(xml)
            text = " ".join(node.text or "" for node in root.iter() if node.tag.endswith("}t"))
        except (OSError, KeyError, zipfile.BadZipFile, ET.ParseError) as exc:
            raise ValueError("Could not read this DOCX resume") from exc
    elif path.suffix.lower() == ".pdf":
        import shutil
        converter = shutil.which("pdftotext")
        if not converter:
            raise ValueError("PDF scoring needs pdftotext installed. Upload a DOCX resume or install Poppler/pdftotext.")
        try:
            result = subprocess.run([converter, "-q", "-layout", str(path), "-"], capture_output=True,
                                    text=True, timeout=20, check=True)
            text = result.stdout
        except (OSError, subprocess.SubprocessError) as exc:
            raise ValueError("Could not extract text from this PDF resume") from exc
    else:
        raise ValueError("Resume matching supports PDF and DOCX files")
    if len(text.strip()) < 40:
        raise ValueError("No readable text found in the resume; try a text-based PDF or DOCX")
    return text


STOP_WORDS = set("a an the and or but if then else of to in on at for from by with as is are was were be been being it its this that these those you your we our they their will can should must may have has had do does did not no yes about into over under between within across all any each both more most other some such than very also using use used work working role job team company people candidate candidates experience years year ability strong excellent good knowledge skill skills required preferred minimum responsibilities qualifications plus bonus support build design develop maintain include including including new help make one two three provide ensure based related required qualifications engineering engineer intern internship developer developers".split())
SKILL_ALIASES = {
    "kubernetes": ("kubernetes", "k8s"), "amazon web services": ("amazon web services", "aws"),
    "google cloud": ("google cloud", "gcp"), "microsoft azure": ("microsoft azure", "azure"),
    "continuous integration": ("continuous integration", "ci/cd", "cicd"),
    "site reliability engineering": ("site reliability engineering", "site reliability", "sre"),
    "infrastructure as code": ("infrastructure as code", "iac"),
    "linux": ("linux",), "terraform": ("terraform",), "docker": ("docker",), "prometheus": ("prometheus",),
    "grafana": ("grafana",), "python": ("python",), "golang": ("golang", "go language"),
    "java": ("java",), "javascript": ("javascript",), "typescript": ("typescript",), "sql": ("sql",),
    "postgresql": ("postgresql", "postgres"), "redis": ("redis",), "kafka": ("kafka",),
    "ansible": ("ansible",), "jenkins": ("jenkins",), "github actions": ("github actions",),
    "gitlab": ("gitlab",), "datadog": ("datadog",), "opentelemetry": ("opentelemetry",),
    "incident response": ("incident response",), "on call": ("on-call", "on call"),
    "networking": ("networking",), "microservices": ("microservices",), "observability": ("observability",),
    "load balancing": ("load balancing",), "distributed systems": ("distributed systems",),
    "configuration management": ("configuration management",), "shell scripting": ("shell scripting", "bash"),
}


def _contains_term(text: str, term: str) -> bool:
    pattern = r"(?<![a-z0-9])" + re.escape(term.casefold()).replace(r"\ ", r"\s+") + r"(?![a-z0-9])"
    return re.search(pattern, text.casefold()) is not None


def resume_match_score(job: Job, resume_text: str) -> Job:
    """Estimate weighted job-description keyword coverage, not hiring probability."""
    description = plain_text(job.description)
    if not description.strip():
        return job
    job_text = description.casefold()
    resume = plain_text(resume_text).casefold()
    terms: dict[str, int] = {}
    for canonical, aliases in SKILL_ALIASES.items():
        if any(_contains_term(job_text, alias) for alias in aliases):
            terms[canonical] = 3
    job_words = re.findall(r"[a-z0-9+#./-]+", job_text)
    resume_words = set(re.findall(r"[a-z0-9+#./-]+", resume))
    counts: dict[str, int] = {}
    for word in job_words:
        normalized = word.strip(".-/+")
        if len(normalized) >= 4 and normalized not in STOP_WORDS and not normalized.isdigit():
            counts[normalized] = counts.get(normalized, 0) + 1
    top_terms = sorted(counts, key=lambda term: (-counts[term], term))[:40]
    for term in top_terms:
        terms.setdefault(term, 1)
    for canonical, aliases in SKILL_ALIASES.items():
        if any(_contains_term(resume, alias) for alias in aliases):
            resume_words.add(canonical)
    if not terms:
        return job
    matched = [term for term, weight in sorted(terms.items(), key=lambda item: (-item[1], item[0]))
               if term in resume_words or _contains_term(resume, term)]
    total_weight = sum(terms.values())
    matched_weight = sum(terms[term] for term in matched)
    score = round(100 * matched_weight / total_weight)
    return replace(job, resume_match=score, matched_terms=tuple(matched[:8]))


def prompt_target_roles(config: dict[str, Any], config_path: Path) -> None:
    if config.get("target_roles"):
        return
    if not sys.stdin.isatty():
        raise ValueError("set target_roles in the private config; interactive setup is unavailable")
    print("What job roles are you targeting?")
    print("Enter role titles separated by commas (for example: Backend Engineer, SRE Intern).")
    answer = input("> ").strip()
    roles = [part.strip() for part in answer.split(",") if part.strip()]
    if not roles:
        raise ValueError("at least one target role is required")
    config["target_roles"] = roles
    config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")


def init_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(mode=0o700 if path.parent.name == "data" else 0o755, parents=True, exist_ok=True)
    if path.parent.name == "data":
        os.chmod(path.parent, 0o700)
    if path.is_symlink():
        raise ValueError("Database path must not be a symbolic link")
    conn = sqlite3.connect(path)
    os.chmod(path, 0o600)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA secure_delete=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS jobs (
            job_key TEXT PRIMARY KEY, company TEXT NOT NULL, ats TEXT NOT NULL, job_id TEXT NOT NULL,
            title TEXT NOT NULL, location TEXT NOT NULL, url TEXT NOT NULL, description TEXT NOT NULL,
            first_seen TEXT NOT NULL, last_seen TEXT NOT NULL, is_open INTEGER NOT NULL DEFAULT 1,
            resume_match INTEGER, matched_terms TEXT NOT NULL DEFAULT '[]'
        );
        CREATE TABLE IF NOT EXISTS runs (
            run_id INTEGER PRIMARY KEY AUTOINCREMENT, started_at TEXT NOT NULL, finished_at TEXT,
            fetched INTEGER NOT NULL DEFAULT 0, matching INTEGER NOT NULL DEFAULT 0,
            surfaced INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS notifications (
            job_key TEXT PRIMARY KEY, sent_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS email_drafts (
            draft_id INTEGER PRIMARY KEY AUTOINCREMENT, job_key TEXT NOT NULL, recipient TEXT NOT NULL,
            subject TEXT NOT NULL, body TEXT NOT NULL, resume_path TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft', created_at TEXT NOT NULL, sent_at TEXT,
            UNIQUE(job_key, recipient)
        );
    """)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(jobs)")}
    if "resume_match" not in columns:
        conn.execute("ALTER TABLE jobs ADD COLUMN resume_match INTEGER")
    if "matched_terms" not in columns:
        conn.execute("ALTER TABLE jobs ADD COLUMN matched_terms TEXT NOT NULL DEFAULT '[]'")
    return conn


def telegram_send(token: str, chat_id: str, jobs: list[Job], run_time: str) -> None:
    if not token or not chat_id:
        raise ValueError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are required to notify")
    chunks: list[str] = []
    current = f"Career Watcher · {len(jobs)} new match(es) · {run_time}\n"
    for job in jobs:
        source = " · via Adzuna" if job.ats == "adzuna" else ""
        score = f"\nResume keyword overlap: {job.resume_match}%" if job.resume_match is not None else ""
        line = f"\n{job.company} — {job.title}{source}{score}\n{job.location or 'Location not specified'}\n{job.url}"
        if len(current) + len(line) > 3800:
            chunks.append(current)
            current = "Career Watcher · continued\n"
        current += line
    if current.strip():
        chunks.append(current)
    for chunk in chunks:
        data = urllib.parse.urlencode({"chat_id": chat_id, "text": chunk, "disable_web_page_preview": "true"}).encode()
        req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=data,
                                    headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8"))
                if not payload.get("ok"):
                    raise RuntimeError("Telegram rejected the notification")
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"Telegram returned HTTP {exc.code}; check your bot token and chat ID") from None


def run(config: dict[str, Any], db_path: Path, *, notifier=telegram_send, env=None) -> dict[str, int]:
    env = env or os.environ
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    conn = init_db(db_path)
    run_id = conn.execute("INSERT INTO runs(started_at) VALUES (?)", (now,)).lastrowid
    fetched: list[Job] = []
    try:
        for index, company in enumerate(config["companies"]):
            if index:
                time.sleep(float(config["request_delay_seconds"]))
            fetched.extend(fetch_company(company, int(config["timeout_seconds"])))
        adzuna = config.get("adzuna", {})
        countries = [c for c in adzuna.get("countries", []) if c in ADZUNA_COUNTRIES]
        if adzuna.get("app_id") and adzuna.get("app_key") and countries:
            requests = [(country, role) for country in countries for role in config["target_roles"]]
            if fetched and requests:
                time.sleep(float(config["request_delay_seconds"]))
            for index, (country, role) in enumerate(requests):
                if index:
                    time.sleep(float(config["request_delay_seconds"]))
                fetched.extend(fetch_adzuna(country, role, adzuna["app_id"], adzuna["app_key"],
                                            int(config["timeout_seconds"])))
        hits = [job for job in fetched if job.id and job.url and matches(job, config["target_roles"], config["locations"])]
        resume_path = config.get("resume_path")
        if resume_path:
            resume_text = extract_resume_text(Path(resume_path))
            hits = [resume_match_score(job, resume_text) for job in hits]
            hits.sort(key=lambda job: job.resume_match if job.resume_match is not None else -1, reverse=True)
        conn.execute("UPDATE jobs SET is_open=0 WHERE ats != 'adzuna'")
        adzuna_expiry = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat(timespec="seconds")
        conn.execute("UPDATE jobs SET is_open=0 WHERE ats='adzuna' AND last_seen < ?", (adzuna_expiry,))
        matching_keys = {job.key for job in hits}
        for job in fetched:
            if job.ats == "adzuna" and job.id and job.key not in matching_keys:
                conn.execute("UPDATE jobs SET is_open=0,last_seen=? WHERE job_key=?", (now, job.key))
        new_jobs: list[Job] = []
        for job in hits:
            exists = conn.execute("SELECT 1 FROM jobs WHERE job_key=?", (job.key,)).fetchone()
            conn.execute("""INSERT INTO jobs(job_key,company,ats,job_id,title,location,url,description,first_seen,last_seen,is_open,resume_match,matched_terms)
                VALUES (?,?,?,?,?,?,?,?,?,?,1,?,?)
                ON CONFLICT(job_key) DO UPDATE SET title=excluded.title, location=excluded.location,
                url=excluded.url, description=excluded.description, last_seen=excluded.last_seen, is_open=1,
                resume_match=excluded.resume_match, matched_terms=excluded.matched_terms""",
                (job.key, job.company, job.ats, job.id, job.title, job.location, job.url, job.description, now, now,
                 job.resume_match, json.dumps(job.matched_terms)))
            if not exists and not conn.execute("SELECT 1 FROM notifications WHERE job_key=?", (job.key,)).fetchone():
                new_jobs.append(job)
        # Only current matches count as open matches; disappeared or nonmatching roles are closed in our log.
        if new_jobs:
            notifier(env.get("TELEGRAM_BOT_TOKEN", ""), env.get("TELEGRAM_CHAT_ID", ""), new_jobs, now)
            conn.executemany("INSERT OR IGNORE INTO notifications(job_key,sent_at) VALUES (?,?)",
                             [(job.key, now) for job in new_jobs])
        conn.execute("UPDATE runs SET finished_at=?, fetched=?, matching=?, surfaced=? WHERE run_id=?",
                     (datetime.now(timezone.utc).isoformat(timespec="seconds"), len(fetched), len(hits), len(new_jobs), run_id))
        conn.commit()
        return {"fetched": len(fetched), "matching": len(hits), "surfaced": len(new_jobs)}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def report(db_path: Path) -> None:
    conn = init_db(db_path)
    surfaced = conn.execute("SELECT COUNT(*) FROM notifications").fetchone()[0]
    missed = conn.execute("SELECT COUNT(*) FROM jobs WHERE is_open=1").fetchone()[0]
    runs = conn.execute("SELECT COUNT(*) FROM runs WHERE finished_at IS NOT NULL").fetchone()[0]
    print(f"Completed runs: {runs}\nNew matching listings surfaced: {surfaced}\nCurrently open matches: {missed}")
    conn.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Watch public company job boards and send private Telegram alerts")
    parser.add_argument("command", choices=["ui", "run", "report"], nargs="?", default="ui")
    parser.add_argument("--config", type=Path, default=Path("config/companies.json"))
    parser.add_argument("--db", type=Path, default=Path("data/career-watcher.sqlite3"))
    parser.add_argument("--data", type=Path, default=Path("data"), help="Private UI settings and state directory")
    parser.add_argument("--port", type=int, default=8765, help="Local UI port")
    parser.add_argument("--host", default="127.0.0.1", help="UI bind address (use 0.0.0.0 only inside a container)")
    parser.add_argument("--display-host", default="127.0.0.1", help="Host printed in the local browser URL")
    parser.add_argument("--no-browser", action="store_true", help="Do not try to open a browser")
    parser.add_argument("--interval-seconds", type=int, default=0, help="Poll automatically after setup at this interval")
    args = parser.parse_args(argv)
    try:
        if args.command == "ui":
            from .web import serve
            serve(args.data, args.port, open_browser=not args.no_browser, host=args.host,
                  display_host=args.display_host, interval_seconds=args.interval_seconds)
            return 0
        if args.command == "report":
            report(args.db)
            return 0
        config = load_config(args.config)
        prompt_target_roles(config, args.config)
        stats = run(config, args.db)
        print(f"Fetched {stats['fetched']} listings; {stats['matching']} match current filters; surfaced {stats['surfaced']} new listings.")
        return 0
    except Exception as exc:
        print(f"career-watcher: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
