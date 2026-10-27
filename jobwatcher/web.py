"""A small, localhost-only setup and dashboard UI."""
from __future__ import annotations

import json
import base64
import hmac
import os
import re
import secrets
import sqlite3
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .app import ADZUNA_COUNTRIES, init_db, resolve_career_url, run
from .mail import build_draft, enqueue


PAGE = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Career Watcher</title><style>
:root{--ink:#17251f;--muted:#66776f;--line:#dce5df;--paper:#f4f7f3;--white:#fff;--green:#176d4b;--mint:#e6f2e9;--orange:#b95b2d;--shadow:0 12px 40px #163b2510}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.5 Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}button,input,textarea,select{font:inherit}button{cursor:pointer}
.shell{max-width:1160px;margin:auto;padding:32px 24px 72px}.top{display:flex;justify-content:space-between;align-items:center;gap:20px;margin-bottom:30px}.brand{display:flex;align-items:center;gap:12px}.mark{width:42px;height:42px;border-radius:14px;background:var(--green);color:#fff;display:grid;place-items:center;font-size:22px}.brand strong{display:block;font-size:17px;letter-spacing:-.3px}.brand span,.eyebrow{color:var(--muted);font-size:12px}.top-actions{display:flex;gap:10px;align-items:center}.status{font-size:13px;color:var(--muted)}
.hero{display:grid;grid-template-columns:1.25fr .75fr;gap:22px;margin-bottom:22px}.panel{background:var(--white);border:1px solid var(--line);border-radius:18px;padding:24px;box-shadow:var(--shadow)}.intro{background:#e8f1e9;border-color:#d7e7d8;min-height:202px;display:flex;flex-direction:column;justify-content:space-between}.eyebrow{text-transform:uppercase;letter-spacing:1.4px;font-weight:700}.intro h1{font-size:32px;letter-spacing:-1.1px;line-height:1.13;margin:10px 0}.intro p{color:#52645a;max-width:550px;margin:0}.stats{display:grid;grid-template-columns:1fr 1fr;gap:12px}.stat{padding:18px;background:var(--white);border:1px solid var(--line);border-radius:16px;display:flex;flex-direction:column;justify-content:center}.stat b{font-size:30px;letter-spacing:-1px}.stat span{font-size:12px;color:var(--muted)}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:22px;align-items:start}.section-title{display:flex;align-items:center;justify-content:space-between;margin-bottom:16px}.section-title h2{font-size:17px;letter-spacing:-.3px;margin:0}.section-title p{font-size:12px;color:var(--muted);margin:3px 0 0}.field{margin:15px 0}.field label{font-size:13px;font-weight:650;display:block;margin-bottom:6px}.field small,.hint{font-size:12px;color:var(--muted)}input,textarea,select{width:100%;border:1px solid #cbd8ce;border-radius:9px;background:#fff;padding:10px 11px;color:var(--ink);outline:none}input:focus,textarea:focus,select:focus{border-color:#3c936b;box-shadow:0 0 0 3px #3c936b1a}textarea{min-height:72px;resize:vertical}.row{display:grid;grid-template-columns:1fr 2fr auto;gap:8px;align-items:center}.company-row{margin:10px 0}.company-row input{padding:9px;font-size:13px}.remove{border:0;background:#f4e9e5;color:#8f4528;border-radius:8px;width:36px;height:38px}.btn{border:0;border-radius:9px;padding:10px 15px;font-weight:650}.primary{background:var(--green);color:#fff}.primary:hover{background:#10583c}.secondary{background:#edf3ee;color:var(--ink);border:1px solid var(--line)}.tiny{padding:7px 10px;font-size:12px}.actions{display:flex;gap:9px;align-items:center;flex-wrap:wrap}.save-note{font-size:12px;color:var(--green)}.divider{height:1px;background:var(--line);margin:18px 0}
.matches{margin-top:22px}.job-list{display:grid;grid-template-columns:1fr 1fr;gap:12px}.job{border:1px solid var(--line);border-radius:13px;padding:15px;background:#fff}.job h3{font-size:15px;margin:0 0 4px}.job .company{font-size:13px;color:var(--muted)}.job .location{font-size:12px;color:var(--muted);margin-top:8px}.job a{color:var(--green);font-weight:650;font-size:13px;text-decoration:none;display:inline-block;margin-top:11px}.job a:hover{text-decoration:underline}.empty{padding:25px;text-align:center;color:var(--muted);border:1px dashed #c7d5ca;border-radius:12px;grid-column:1/-1}.toolbar{display:flex;justify-content:space-between;align-items:center;margin-bottom:15px;gap:12px}.foot{margin-top:24px;color:var(--muted);font-size:12px;text-align:center}.notice{padding:11px 13px;background:#fff6e7;border-radius:9px;color:#76552e;font-size:12px;margin-top:14px}.help{margin-top:12px;color:var(--muted);font-size:12px}details summary{cursor:pointer;color:var(--green);font-weight:600}
@media(max-width:800px){.hero,.grid{grid-template-columns:1fr}.stats{grid-template-columns:1fr 1fr}.job-list{grid-template-columns:1fr}.shell{padding:20px 14px 50px}.intro h1{font-size:28px}.row{grid-template-columns:1fr}.top{align-items:flex-start}}
</style></head><body><main class="shell">
<header class="top"><div class="brand"><div class="mark">⌕</div><div><strong>Career Watcher</strong><span>Your personal job search radar</span></div></div><div class="top-actions"><span class="status" id="runStatus">Ready</span><button class="btn secondary tiny" onclick="refresh()">Refresh</button></div></header>
<section class="hero"><div class="panel intro"><div><div class="eyebrow">A calmer job search</div><h1>Spot the right role<br>when it opens.</h1><p>Search broad job indexes across countries and add direct company boards for extra coverage.</p></div><div class="hint">Private by default · Runs on this computer · Alerts go to your Telegram</div></div><div class="stats"><div class="stat"><b id="surfaced">—</b><span>new matches surfaced</span></div><div class="stat"><b id="openMatches">—</b><span>open matches right now</span></div><div class="stat"><b id="runCount">—</b><span>successful checks</span></div><div class="stat"><b id="companyCount">—</b><span>markets and direct boards</span></div></div></section>
<section class="grid"><div class="panel"><div class="section-title"><div><h2>What job roles are you targeting?</h2><p>We compare these with each source and estimate local resume keyword overlap.</p></div></div><div class="field"><label for="roles">Role titles</label><textarea id="roles" placeholder="Backend Engineer, SRE Intern, Platform Engineer"></textarea><small>Separate roles with commas or put one on each line.</small></div><div class="field"><label for="locations">Locations</label><input id="locations" placeholder="London, New York, Remote"><small>Leave blank to search all locations in selected countries. Otherwise, only locations matching your entries show.</small></div><div class="field"><label for="resumeFile">Resume used for local matching</label><input id="resumeFile" type="file" accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"><button class="btn secondary tiny" style="margin-top:8px" onclick="uploadResume()">Save resume on this computer</button><small id="resumeHelp" style="display:block;margin-top:6px">Resume stays local. DOCX works directly; PDF scoring needs pdftotext.</small></div><div class="divider"></div><div class="section-title"><div><h2>Worldwide search</h2><p>Search Adzuna's indexed listings across supported countries.</p></div></div><div class="field"><label for="adzunaId">Adzuna app ID</label><input id="adzunaId" autocomplete="off" placeholder="Optional — needed for worldwide search"></div><div class="field"><label for="adzunaKey">Adzuna app key</label><input id="adzunaKey" type="password" autocomplete="new-password" placeholder="Paste your API key"><small id="adzunaHelp">Stored only on this computer. Leave blank to keep a saved key.</small></div><div class="hint"><a href="https://developer.adzuna.com/" target="_blank" rel="noreferrer">Get an Adzuna API key</a>. Its terms allow personal job search; check current account limits.</div><div class="field"><label>Countries to search</label><div id="countries" style="display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:7px;font-size:12px"></div><small>One search per target role in each selected country.</small></div><div class="divider"></div><div class="section-title"><div><h2>Company job boards</h2><p>Paste each company's careers-page URL.</p></div><button class="btn secondary tiny" onclick="addCompany()">＋ Add company</button></div><div id="companies"></div><div class="help"><details><summary>Which links work?</summary><p>Paste a Greenhouse or Lever careers-page URL, such as <code>https://boards.greenhouse.io/company</code> or <code>https://jobs.lever.co/company</code>. Other portals need a documented public feed before this app can monitor them.</p></details></div><div class="notice">No public source contains every employer's openings worldwide. Adzuna searches its indexed ads in selected markets; supported Greenhouse/Lever URLs add direct monitoring.</div></div>
<div class="panel"><div class="section-title"><div><h2>Send alerts to Telegram</h2><p>Notifications are sent to your private chat.</p></div></div><div class="field"><label for="botToken">Bot token</label><input id="botToken" type="password" autocomplete="new-password" placeholder="Paste bot token"><small id="tokenHelp">Stored only on this computer. Leave blank to keep a saved token.</small></div><div class="field"><label for="chatId">Chat ID</label><input id="chatId" placeholder="For example: 123456789"></div><div class="hint"><a href="https://t.me/BotFather" target="_blank" rel="noreferrer">Create a Telegram bot</a>, then open it and send /start. Your chat ID is available from the bot's getUpdates response.</div><div class="notice">On your first check, all current matches are sent once. Later checks alert only for newly seen matches.</div><div class="divider"></div><div class="section-title"><div><h2>Resume email drafts</h2><p>Prepare outreach for a job; connect a mail provider later.</p></div></div><div class="notice">Enter a recipient email on a listing to queue a personalized draft. No email is sent until a mail provider is connected and enabled.</div><div class="divider"></div><div class="section-title"><div><h2>Share presence with project owner</h2><p>Optional check-ins from this installation.</p></div></div><label style="font-size:13px;display:flex;align-items:flex-start;gap:8px"><input id="presenceEnabled" type="checkbox" style="width:auto;margin-top:4px"> I agree to share my chosen label and service activity timestamps with the project owner.</label><div class="field"><label for="presenceName">Name or nickname shown to owner</label><input id="presenceName" maxlength="64" placeholder="A nickname is fine"></div><div class="field"><label for="presenceUrl">Owner dashboard HTTPS address</label><input id="presenceUrl" placeholder="https://presence.example.com"><small>The owner must provide this URL and the project token.</small></div><div class="field"><label for="presenceToken">Project presence token</label><input id="presenceToken" type="password" autocomplete="new-password" placeholder="Provided by the project owner"><small id="presenceTokenHelp">Stored only on this computer. You can disable sharing at any time.</small></div><div class="notice">If enabled, the owner receives your chosen label, a random installation ID, and timestamps for service start, dashboard use, and completed checks. Your resume, job searches, listings, and API credentials are not sent.</div><div class="divider"></div><div class="actions"><button class="btn secondary" onclick="testTelegram()">Send test alert</button><button class="btn primary" onclick="saveSettings()">Save my setup</button><button class="btn primary" id="runButton" onclick="runNow()">Check for new jobs</button></div><div id="message" class="save-note" style="margin-top:12px"></div><div class="help">Checks are polite and sequential. Resume scoring is local; resume text is not sent to job sources.</div></div></section>
<section class="panel matches"><div class="toolbar"><div><h2 style="margin:0;font-size:17px">Your current matches</h2><div class="hint">The newest roles appear first. Enter a contact email yourself; contacts are never harvested.</div></div><span class="status" id="lastCheck"></span></div><div class="job-list" id="jobList"><div class="empty">Save your setup, then check for new jobs.</div></div></section>
<section class="panel matches"><div class="toolbar"><div><h2 style="margin:0;font-size:17px">Prepared resume emails</h2><div class="hint">Private drafts waiting for a mail provider integration.</div></div></div><div id="draftList" class="job-list"><div class="empty">No email drafts prepared yet.</div></div></section>
<footer class="foot">Career Watcher checks public job sources. Review each source's terms before enabling it.</footer></main>
<script>
const $=id=>document.getElementById(id);let savedToken=false,renderedJobs='';const countryMap={gb:'United Kingdom',us:'United States',at:'Austria',au:'Australia',be:'Belgium',br:'Brazil',ca:'Canada',ch:'Switzerland',de:'Germany',es:'Spain',fr:'France',in:'India',it:'Italy',mx:'Mexico',nl:'Netherlands',nz:'New Zealand',pl:'Poland',sg:'Singapore',za:'South Africa'};
function splitList(s){return s.split(/[\n,]+/).map(x=>x.trim()).filter(Boolean)}
function addCompany(c={name:"",career_url:""}){const row=document.createElement('div');row.className='row company-row';row.innerHTML='<input class="company-name" aria-label="Company name" placeholder="Company name"><input class="career-url" aria-label="Careers-page URL" placeholder="https://jobs.lever.co/company"><button class="remove" title="Remove company" aria-label="Remove company">×</button>';row.querySelector('.company-name').value=c.name||'';row.querySelector('.career-url').value=c.career_url||(c.ats==='greenhouse'?'https://boards.greenhouse.io/':c.ats==='lever'?'https://jobs.lever.co/':'')+(c.board||'');row.querySelector('button').onclick=()=>row.remove();$('companies').appendChild(row)}
function collect(){return {target_roles:splitList($('roles').value),locations:splitList($('locations').value),companies:[...document.querySelectorAll('.company-row')].map(r=>({name:r.querySelector('.company-name').value.trim(),career_url:r.querySelector('.career-url').value.trim()})).filter(c=>c.name&&c.career_url),adzuna_app_id:$('adzunaId').value.trim(),adzuna_app_key:$('adzunaKey').value.trim(),adzuna_countries:[...document.querySelectorAll('input[name=country]:checked')].map(x=>x.value),telegram_bot_token:$('botToken').value.trim(),telegram_chat_id:$('chatId').value.trim(),presence_enabled:$('presenceEnabled').checked,presence_name:$('presenceName').value.trim(),presence_dashboard_url:$('presenceUrl').value.trim(),presence_ingest_token:$('presenceToken').value.trim()}}
const accessToken=decodeURIComponent(location.hash.slice(1));
async function api(url,body){const options={headers:{'Authorization':'Bearer '+accessToken}};if(body){options.method='POST';options.headers['Content-Type']='application/json';options.body=JSON.stringify(body)}const r=await fetch(url,options);const data=await r.json();if(!r.ok)throw Error(data.error||'Request failed');return data}
function msg(s,error=false){$('message').textContent=s;$('message').style.color=error?'#a43c2a':'var(--green)'}
async function saveSettings(silent=false){try{const d=await api('/api/settings',collect());savedToken=d.telegram_configured;$('botToken').value='';$('tokenHelp').textContent=savedToken?'A bot token is saved on this computer. Leave blank to keep it.':'Stored only on this computer.';$('adzunaKey').value='';$('adzunaHelp').textContent=d.adzuna_configured?'An Adzuna key is saved on this computer. Leave blank to keep it.':'Stored only on this computer.';$('presenceToken').value='';$('presenceTokenHelp').textContent=d.presence_configured?'A presence token is saved on this computer. Leave blank to keep it.':'Stored only on this computer.';if(!silent)msg('Setup saved on this computer.')}catch(e){msg(e.message,true);throw e}}
async function testTelegram(){try{await saveSettings(true);await api('/api/test-telegram',{});msg('Test alert sent. Check your Telegram chat.')}catch(e){msg(e.message,true)}}
async function runNow(){try{await saveSettings(true);const d=await api('/api/run',{});msg(d.message);refresh();}catch(e){msg(e.message,true)}}
function esc(s){const d=document.createElement('div');d.textContent=s||'';return d.innerHTML}
function safeLink(s){try{const u=new URL(s);return u.protocol==='https:'?esc(s):''}catch{return ''}}
async function uploadResume(){const f=$('resumeFile').files[0];if(!f){msg('Choose a PDF or DOCX resume first.',true);return}if(f.size>10000000){msg('Resume must be under 10 MB.',true);return}const reader=new FileReader();reader.onload=async()=>{try{const data=String(reader.result).split(',')[1];const d=await api('/api/resume',{name:f.name,data});$('resumeHelp').textContent='Saved '+d.name+' privately on this computer.';msg('Resume saved locally.')}catch(e){msg(e.message,true)}};reader.readAsDataURL(f)}
async function queueEmail(jobKey,button){const card=button.closest('.job'),recipient=card.querySelector('.recipient').value.trim();try{const d=await api('/api/queue-email',{job_key:jobKey,recipient});button.textContent=d.queued?'Draft queued':'Draft already queued';msg(d.queued?'Email draft queued for your mail provider.':'A draft for this recipient already exists.')}catch(e){msg(e.message,true)}}
async function refresh(){try{const d=await api('/api/state');$('surfaced').textContent=d.summary.surfaced;$('openMatches').textContent=d.summary.open_matches;$('runCount').textContent=d.summary.runs;$('companyCount').textContent=d.summary.companies;$('runStatus').textContent=d.worker.running?'Checking job sources…':(d.worker.error?'Last check failed':'Ready');$('lastCheck').textContent=d.summary.last_check?'Last check: '+new Date(d.summary.last_check).toLocaleString():'';$('runButton').disabled=d.worker.running;$('runButton').textContent=d.worker.running?'Checking…':'Check for new jobs';$('runButton').style.opacity=d.worker.running?'.65':'1';if(d.worker.error)msg(d.worker.error,true);const current=d.jobs.map(j=>j.job_key).join('|');if(current!==renderedJobs){renderedJobs=current;if(d.jobs.length){$('jobList').innerHTML=d.jobs.map(j=>`<article class="job" data-key="${esc(j.job_key)}"><h3>${esc(j.title)}</h3><div class="company">${esc(j.company)}${j.source==='adzuna'?' · via Adzuna':''}</div><div class="location">${esc(j.location||'Location not specified')}</div>${j.resume_match!==null&&j.resume_match!==undefined?`<div class="location"><strong>Resume keyword overlap: ${j.resume_match}%</strong>${j.matched_terms?.length?` · matched: ${esc(j.matched_terms.join(', '))}`:''}</div>`:''}<a href="${safeLink(j.url)}" target="_blank" rel="noreferrer">View listing ↗</a><div style="display:flex;gap:7px;margin-top:12px"><input class="recipient" type="email" placeholder="Recruiter email" aria-label="Recruiter email" style="padding:8px;font-size:12px"><button class="btn secondary tiny queue-email">Prepare email</button></div></article>`).join('');document.querySelectorAll('.queue-email').forEach(b=>b.addEventListener('click',()=>queueEmail(b.closest('.job').dataset.key,b)))}else{$('jobList').innerHTML='<div class="empty">No open matches yet. Save your setup and run your first check.</div>'}}if(d.drafts?.length){$('draftList').innerHTML=d.drafts.map(x=>`<article class="job"><h3>${esc(x.subject)}</h3><div class="company">To: ${esc(x.recipient)} · ${esc(x.status)}</div><div class="location" style="white-space:pre-wrap">${esc(x.body)}</div></article>`).join('')}else{$('draftList').innerHTML='<div class="empty">No email drafts prepared yet.</div>'}}catch(e){$('runStatus').textContent='Could not load local data';msg(e.message,true)}}
async function load(){try{const d=await api('/api/settings');$('roles').value=(d.target_roles||[]).join('\n');$('locations').value=(d.locations||[]).join(', ');$('companies').innerHTML='';(d.companies||[]).forEach(addCompany);if(!d.companies?.length)addCompany();$('chatId').value=d.telegram_chat_id||'';$('adzunaId').value=d.adzuna_app_id||'';$('presenceEnabled').checked=Boolean(d.presence_enabled);$('presenceName').value=d.presence_name||'';$('presenceUrl').value=d.presence_dashboard_url||'';const selected=d.adzuna_countries||Object.keys(countryMap);$('countries').innerHTML=Object.entries(countryMap).map(([code,name])=>`<label style="font-weight:400;display:flex;gap:5px;align-items:center"><input type="checkbox" name="country" value="${code}" ${selected.includes(code)?'checked':''} style="width:auto">${name}</label>`).join('');savedToken=d.telegram_configured;$('tokenHelp').textContent=savedToken?'A bot token is saved on this computer. Leave blank to keep it.':'Stored only on this computer.';$('adzunaHelp').textContent=d.adzuna_configured?'An Adzuna key is saved on this computer. Leave blank to keep it.':'Stored only on this computer.';$('presenceTokenHelp').textContent=d.presence_configured?'A presence token is saved on this computer. Leave blank to keep it.':'Stored only on this computer.';$('resumeHelp').textContent=d.resume_name?'Saved resume: '+d.resume_name+' on this computer.':'Upload a resume to prepare email drafts.';refresh()}catch(e){msg(e.message,true)}}
load();setInterval(refresh,5000);
</script></body></html>'''


class LocalApp:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.settings_path = data_dir / "settings.json"
        self.db_path = data_dir / "career-watcher.sqlite3"
        if self.data_dir.is_symlink():
            raise ValueError("Private data directory must not be a symbolic link")
        self.data_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.data_dir, 0o700)
        self.browser_token = secrets.token_urlsafe(32)
        self.lock = threading.Lock()
        self.presence_session_lock = threading.Lock()
        self.dashboard_seen = False
        self.worker = {"running": False, "error": ""}
        self.report_presence("service_started")

    def record_dashboard_session(self) -> None:
        with self.presence_session_lock:
            if self.dashboard_seen:
                return
            self.dashboard_seen = True
        self.report_presence("dashboard_opened")

    def report_presence(self, event_type: str) -> None:
        try:
            settings = self.settings()
            if not settings.get("presence_enabled"):
                return
            endpoint = str(settings.get("presence_dashboard_url", "")).rstrip("/") + "/api/presence"
            token = str(settings.get("presence_ingest_token", ""))
            display_name = str(settings.get("presence_name", "")).strip()[:64]
            parsed_endpoint = urllib.parse.urlparse(endpoint)
            local_hosts = {"localhost", "127.0.0.1", "::1", "host.docker.internal"}
            secure_transport = parsed_endpoint.scheme == "https" or (
                parsed_endpoint.scheme == "http" and parsed_endpoint.hostname in local_hosts
            )
            if not secure_transport or not parsed_endpoint.hostname or not token or not display_name:
                return
            identity_path = self.data_dir / "presence-install-id"
            if identity_path.is_symlink():
                return
            if identity_path.exists():
                install_id = identity_path.read_text(encoding="ascii").strip()
                if not re.fullmatch(r"[a-f0-9]{32}", install_id):
                    return
            else:
                install_id = secrets.token_hex(16)
                identity_path.write_text(install_id + "\n", encoding="ascii")
                os.chmod(identity_path, 0o600)
            payload = json.dumps({"install_id": install_id, "display_name": display_name,
                                  "event_type": event_type}).encode("utf-8")
            request = urllib.request.Request(endpoint, data=payload, headers={
                "Authorization": f"Bearer {token}", "Content-Type": "application/json"})

            def send() -> None:
                try:
                    with urllib.request.urlopen(request, timeout=4):
                        pass
                except Exception:
                    pass

            threading.Thread(target=send, name="presence-report", daemon=True).start()
        except Exception:
            # Presence reporting must never block job watching or reveal tokens in UI errors.
            return

    def settings(self) -> dict[str, Any]:
        if self.settings_path.is_symlink():
            raise ValueError("Settings file must not be a symbolic link")
        if not self.settings_path.exists():
            return {"companies": [], "target_roles": [], "locations": [], "telegram_bot_token": "", "telegram_chat_id": "",
                    "adzuna_app_id": "", "adzuna_app_key": "", "adzuna_countries": list(ADZUNA_COUNTRIES)}
        return json.loads(self.settings_path.read_text(encoding="utf-8"))

    def save_settings(self, value: dict[str, Any]) -> dict[str, Any]:
        current = self.settings()
        token = str(value.get("telegram_bot_token", "")).strip() or current.get("telegram_bot_token", "")
        adzuna_key = str(value.get("adzuna_app_key", "")).strip() or current.get("adzuna_app_key", "")
        adzuna_id = str(value.get("adzuna_app_id", "")).strip() or current.get("adzuna_app_id", "")
        presence_enabled = bool(value.get("presence_enabled", current.get("presence_enabled", False)))
        presence_name = str(value.get("presence_name", current.get("presence_name", ""))).strip()[:64]
        presence_url = str(value.get("presence_dashboard_url", current.get("presence_dashboard_url", ""))).strip().rstrip("/")
        presence_token = (str(value.get("presence_ingest_token", "")).strip() or
                          current.get("presence_ingest_token", "")) if presence_enabled else ""
        if presence_enabled:
            parsed_presence_url = urllib.parse.urlparse(presence_url)
            local_hosts = {"localhost", "127.0.0.1", "::1", "host.docker.internal"}
            if not presence_name:
                raise ValueError("Choose a display name before sharing presence")
            if not presence_token:
                raise ValueError("Enter the project presence token before sharing presence")
            if not parsed_presence_url.hostname or (parsed_presence_url.scheme != "https" and not (
                parsed_presence_url.scheme == "http" and parsed_presence_url.hostname in local_hosts
            )):
                raise ValueError("Presence sharing requires HTTPS, except for localhost testing")
            if parsed_presence_url.username or parsed_presence_url.password or parsed_presence_url.query or parsed_presence_url.fragment or parsed_presence_url.path not in {"", "/"}:
                raise ValueError("Enter only the dashboard origin, for example https://presence.example.com")
        companies = []
        for item in value.get("companies", []):
            name, career_url = str(item.get("name", "")).strip(), str(item.get("career_url", "")).strip()
            if not name and not career_url:
                continue
            if not name or not career_url:
                raise ValueError("Each company needs a name and careers-page URL")
            ats, board = resolve_career_url(career_url)
            companies.append({"name": name, "board": board, "ats": ats, "career_url": career_url})
        roles = [str(x).strip() for x in value.get("target_roles", []) if str(x).strip()]
        locations = [str(x).strip() for x in value.get("locations", []) if str(x).strip()]
        countries = list(dict.fromkeys(str(x).lower() for x in value.get("adzuna_countries", list(ADZUNA_COUNTRIES))
                                       if str(x).lower() in ADZUNA_COUNTRIES))
        if len(roles) > 30 or len(companies) > 100:
            raise ValueError("Please keep the role list under 30 and company list under 100")
        settings = {"companies": companies, "target_roles": roles, "locations": locations,
                    "telegram_bot_token": token, "telegram_chat_id": str(value.get("telegram_chat_id", "")).strip(),
                    "adzuna_app_id": adzuna_id, "adzuna_app_key": adzuna_key, "adzuna_countries": countries,
                    "presence_enabled": presence_enabled, "presence_name": presence_name,
                    "presence_dashboard_url": presence_url, "presence_ingest_token": presence_token,
                    "request_delay_seconds": 1.5, "timeout_seconds": 20}
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if self.settings_path.is_symlink():
            raise ValueError("Settings file must not be a symbolic link")
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=self.data_dir, prefix=".settings-", delete=False) as tmp:
            tmp.write(json.dumps(settings, indent=2) + "\n")
            tmp_path = Path(tmp.name)
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, self.settings_path)
        if presence_enabled:
            self.report_presence("settings_saved")
        return settings

    def summary(self) -> dict[str, Any]:
        conn = init_db(self.db_path)
        surfaced = conn.execute("SELECT COUNT(*) FROM notifications").fetchone()[0]
        open_matches = conn.execute("SELECT COUNT(*) FROM jobs WHERE is_open=1").fetchone()[0]
        runs, last_check = conn.execute("SELECT COUNT(*), MAX(finished_at) FROM runs WHERE finished_at IS NOT NULL").fetchone()
        conn.close()
        return {"surfaced": surfaced, "open_matches": open_matches, "runs": runs, "last_check": last_check}

    def jobs(self) -> list[dict[str, Any]]:
        conn = init_db(self.db_path)
        rows = conn.execute("SELECT job_key,company,title,location,url,last_seen,ats,resume_match,matched_terms FROM jobs WHERE is_open=1 ORDER BY resume_match DESC,last_seen DESC LIMIT 100").fetchall()
        conn.close()
        result = []
        for row in rows:
            job = dict(zip(("job_key", "company", "title", "location", "url", "last_seen", "source", "resume_match", "matched_terms"), row))
            job["matched_terms"] = json.loads(job["matched_terms"] or "[]")
            result.append(job)
        return result

    def drafts(self) -> list[dict[str, Any]]:
        conn = init_db(self.db_path)
        rows = conn.execute("""SELECT d.job_key,j.company,j.title,d.recipient,d.subject,d.body,d.status,d.created_at
            FROM email_drafts d LEFT JOIN jobs j ON j.job_key=d.job_key ORDER BY d.draft_id DESC LIMIT 100""").fetchall()
        conn.close()
        return [dict(zip(("job_key", "company", "title", "recipient", "subject", "body", "status", "created_at"), row)) for row in rows]

    def store_resume(self, filename: str, encoded: str) -> str:
        suffix = Path(filename).suffix.lower()
        if suffix not in {".pdf", ".docx"}:
            raise ValueError("Upload a PDF or DOCX resume")
        try:
            content = base64.b64decode(encoded, validate=True)
        except Exception as exc:
            raise ValueError("Resume upload could not be read") from exc
        if not content or len(content) > 10_000_000:
            raise ValueError("Resume must be under 10 MB")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        path = self.data_dir / f"resume{suffix}"
        if path.is_symlink():
            raise ValueError("Resume path must not be a symbolic link")
        path.write_bytes(content)
        os.chmod(path, 0o600)
        for other_suffix in {".pdf", ".docx"} - {suffix}:
            other_path = self.data_dir / f"resume{other_suffix}"
            if other_path.is_symlink():
                raise ValueError("Resume path must not be a symbolic link")
            if other_path.exists():
                other_path.unlink()
        return path.name

    def queue_email(self, job_key: str, recipient: str) -> bool:
        conn = init_db(self.db_path)
        row = conn.execute("SELECT company,title,url FROM jobs WHERE job_key=? AND is_open=1", (job_key,)).fetchone()
        if not row:
            conn.close()
            raise ValueError("That listing is no longer in the current matches")
        resume_path = next((p for p in (self.data_dir / "resume.pdf", self.data_dir / "resume.docx") if p.is_file()), None)
        if resume_path is None:
            conn.close()
            raise ValueError("Upload your resume first")
        draft = build_draft(job_key, row[0], row[1], row[2], recipient, resume_path)
        queued = enqueue(conn, draft, datetime.now(timezone.utc).isoformat(timespec="seconds"))
        conn.commit()
        conn.close()
        return queued

    def start_run(self) -> None:
        settings = self.settings()
        if not settings["target_roles"]:
            raise ValueError("Add at least one target role first")
        resume_path = next((p for p in (self.data_dir / "resume.pdf", self.data_dir / "resume.docx") if p.is_file()), None)
        if resume_path is None:
            raise ValueError("Upload your resume to calculate match scores")
        has_adzuna = bool(settings.get("adzuna_app_id") and settings.get("adzuna_app_key") and settings.get("adzuna_countries"))
        if not settings["companies"] and not has_adzuna:
            raise ValueError("Add a company board or configure worldwide Adzuna search first")
        if not settings["telegram_bot_token"] or not settings["telegram_chat_id"]:
            raise ValueError("Add your Telegram bot token and chat ID first")
        with self.lock:
            if self.worker["running"]:
                raise ValueError("A check is already running")
            self.worker = {"running": True, "error": ""}
        def work() -> None:
            try:
                config = {key: settings[key] for key in ("companies", "target_roles", "locations", "request_delay_seconds", "timeout_seconds")}
                config["adzuna"] = {"app_id": settings.get("adzuna_app_id", ""), "app_key": settings.get("adzuna_app_key", ""),
                                    "countries": settings.get("adzuna_countries", [])}
                config["resume_path"] = str(resume_path)
                stats = run(config, self.db_path, env={"TELEGRAM_BOT_TOKEN": settings["telegram_bot_token"],
                                                       "TELEGRAM_CHAT_ID": settings["telegram_chat_id"]})
                self.report_presence("check_completed")
            except Exception as exc:
                self.worker["error"] = str(exc)
                self.report_presence("check_failed")
            finally:
                self.worker["running"] = False
        threading.Thread(target=work, daemon=True).start()

    def test_telegram(self) -> None:
        settings = self.settings()
        if not settings["telegram_bot_token"] or not settings["telegram_chat_id"]:
            raise ValueError("Add and save the Telegram bot token and chat ID first")
        data = urllib.parse.urlencode({"chat_id": settings["telegram_chat_id"], "text": "Career Watcher is connected. New matching job alerts will arrive here."}).encode()
        req = urllib.request.Request(f"https://api.telegram.org/bot{settings['telegram_bot_token']}/sendMessage", data=data)
        try:
            with urllib.request.urlopen(req, timeout=20) as response:
                result = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise ValueError(f"Telegram returned HTTP {exc.code}; check your bot token and chat ID") from None
        except urllib.error.URLError:
            raise ValueError("Could not reach Telegram") from None
        if not result.get("ok"):
            raise ValueError("Telegram did not accept the test message")


def serve(data_dir: Path, port: int = 8765, open_browser: bool = True, host: str = "127.0.0.1",
          display_host: str = "127.0.0.1", interval_seconds: int = 0) -> None:
    app = LocalApp(data_dir)

    class Handler(BaseHTTPRequestHandler):
        server_version = "CareerWatcherLocal/1.0"

        def log_message(self, fmt: str, *args: Any) -> None:
            # Avoid writing request data or credentials into terminal logs.
            return

        def _local_request(self) -> bool:
            host = self.headers.get("Host", "").split(":", 1)[0].lower()
            origin = urllib.parse.urlparse(self.headers.get("Origin", "")).hostname
            return host in {"127.0.0.1", "localhost", "[::1]"} and (origin is None or origin in {"127.0.0.1", "localhost", "::1"})

        def _authorized(self) -> bool:
            presented = self.headers.get("Authorization", "")
            return hmac.compare_digest(presented, f"Bearer {app.browser_token}")

        def _security_headers(self) -> None:
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Cross-Origin-Resource-Policy", "same-origin")
            self.send_header("Cache-Control", "no-store")

        def _json(self, value: Any, status: int = 200) -> None:
            payload = json.dumps(value).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self._security_headers()
            self.end_headers()
            self.wfile.write(payload)

        def _body(self, max_size: int = 1_000_000) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            if length > max_size:
                raise ValueError("Request is too large")
            return json.loads(self.rfile.read(length) or b"{}")

        def do_GET(self) -> None:
            if not self._local_request():
                self._json({"error": "Local requests only"}, 403)
            elif self.path == "/":
                payload = PAGE.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'")
                self._security_headers()
                self.end_headers()
                self.wfile.write(payload)
            elif self.path.startswith("/api/") and not self._authorized():
                self._json({"error": "Open the private link printed by Career Watcher"}, 401)
            elif self.path == "/api/settings":
                app.record_dashboard_session()
                settings = app.settings()
                settings["telegram_configured"] = bool(settings.pop("telegram_bot_token", ""))
                settings["adzuna_configured"] = bool(settings.pop("adzuna_app_key", ""))
                settings["presence_configured"] = bool(settings.pop("presence_ingest_token", ""))
                settings["resume_name"] = next((p.name for p in (app.data_dir / "resume.pdf", app.data_dir / "resume.docx") if p.is_file()), "")
                self._json(settings)
            elif self.path == "/api/state":
                settings = app.settings()
                watched = len(settings["companies"]) + (len(settings.get("adzuna_countries", [])) if settings.get("adzuna_app_id") and settings.get("adzuna_app_key") else 0)
                self._json({"summary": {**app.summary(), "companies": watched},
                            "jobs": app.jobs(), "drafts": app.drafts(), "worker": dict(app.worker)})
            else:
                self._json({"error": "Not found"}, 404)

        def do_POST(self) -> None:
            if not self._local_request():
                self._json({"error": "Local requests only"}, 403)
                return
            if not self._authorized():
                self._json({"error": "Open the private link printed by Career Watcher"}, 401)
                return
            try:
                if self.path == "/api/settings":
                    settings = app.save_settings(self._body())
                    self._json({"saved": True, "telegram_configured": bool(settings["telegram_bot_token"]),
                                "adzuna_configured": bool(settings["adzuna_app_key"]),
                                "presence_configured": bool(settings["presence_ingest_token"])})
                elif self.path == "/api/run":
                    app.start_run()
                    self._json({"started": True, "message": "Check started. This page will update as it finishes."}, 202)
                elif self.path == "/api/test-telegram":
                    app.test_telegram()
                    self._json({"sent": True})
                elif self.path == "/api/resume":
                    payload = self._body(15_000_000)
                    name = app.store_resume(str(payload.get("name", "")), str(payload.get("data", "")))
                    self._json({"saved": True, "name": name})
                elif self.path == "/api/queue-email":
                    payload = self._body()
                    queued = app.queue_email(str(payload.get("job_key", "")), str(payload.get("recipient", "")))
                    self._json({"queued": queued}, 201 if queued else 200)
                else:
                    self._json({"error": "Not found"}, 404)
            except (ValueError, json.JSONDecodeError) as exc:
                self._json({"error": str(exc)}, 400)
            except Exception as exc:
                self._json({"error": f"Could not complete the request: {exc}"}, 500)

    server = ThreadingHTTPServer((host, port), Handler)
    url = f"http://{display_host}:{server.server_port}/#{app.browser_token}"
    print(f"Career Watcher is ready at {url} (Ctrl+C to stop)")
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    stop_scheduler = threading.Event()

    def presence_heartbeats() -> None:
        while not stop_scheduler.wait(60):
            app.report_presence("heartbeat")

    def scheduled_checks() -> None:
        while not stop_scheduler.is_set():
            try:
                settings = app.settings()
                has_source = bool(settings.get("companies") or (
                    settings.get("adzuna_app_id") and settings.get("adzuna_app_key") and
                    settings.get("adzuna_countries")
                ))
                ready = bool(settings.get("target_roles") and has_source and
                             settings.get("telegram_bot_token") and settings.get("telegram_chat_id"))
                ready = ready and any((app.data_dir / name).is_file() for name in ("resume.pdf", "resume.docx"))
                if not ready:
                    stop_scheduler.wait(5)
                    continue
                try:
                    app.start_run()
                except ValueError:
                    stop_scheduler.wait(5)
                    continue
                while app.worker["running"] and not stop_scheduler.wait(1):
                    pass
                stop_scheduler.wait(interval_seconds)
            except Exception:
                stop_scheduler.wait(30)

    if interval_seconds > 0:
        threading.Thread(target=scheduled_checks, daemon=True).start()
    threading.Thread(target=presence_heartbeats, name="presence-heartbeat", daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nCareer Watcher stopped.")
    finally:
        stop_scheduler.set()
        server.server_close()
