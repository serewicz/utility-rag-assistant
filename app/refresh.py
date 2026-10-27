"""Nightly document refresh: keep the public LCRA pages current, and keep a record.

Every utility asks "who keeps this current?" This is the answer:
  1. data/sources.yaml lists each public page and the local file it feeds.
  2. A scheduler (off by default; REFRESH_ENABLED=1) runs once a night at REFRESH_HOUR Central time.
     An admin can also trigger it: POST /admin/refresh with X-User: tim.
  3. For each page: check robots.txt, fetch it, extract the readable text, and hash it.
     - First time seen: record the hash as a baseline. The committed file is NOT rewritten,
       because the committed files were cleaned by hand and are what the evals were tuned on.
     - Hash changed since last check: rewrite the local file (front matter kept, `retrieved`
       updated), log it, and re-ingest.
     - Unchanged: just update "last checked".
  4. Every event goes into refresh_log, shown on the governance page.

Network calls go through `fetch(url) -> (status, text)`, which tests replace with a mock.
"""
from __future__ import annotations

import hashlib
import re
import threading
import time
from datetime import date, datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser
from zoneinfo import ZoneInfo

import httpx
import yaml

from .ingest import ingest_dir, parse_front_matter

CENTRAL = ZoneInfo("America/Chicago")
USER_AGENT = "utility-rag-assistant-refresh (POC; +https://github.com/serewicz/utility-rag-assistant)"
SCHEMA = [
    """CREATE TABLE IF NOT EXISTS source_state(doc TEXT, url TEXT, content_hash TEXT,
        last_checked DOUBLE PRECISION, last_changed DOUBLE PRECISION)""",
    "CREATE TABLE IF NOT EXISTS refresh_log(ts DOUBLE PRECISION, doc TEXT, event TEXT, detail TEXT)",
]
_lock = threading.Lock()


def init(store):
    for sql in SCHEMA:
        store.q(sql)


def http_fetch(url: str) -> tuple[int, str]:
    r = httpx.get(url, timeout=20, follow_redirects=True, headers={"User-Agent": USER_AGENT})
    return r.status_code, r.text


class _Text(HTMLParser):
    """Readable text from a page: headings, paragraphs, list items. Skips scripts, nav, header, footer."""
    SKIP = {"script", "style", "nav", "header", "footer", "noscript", "svg", "form"}
    BLOCK = {"p": "", "li": "- ", "h1": "# ", "h2": "## ", "h3": "### ", "h4": "#### ", "td": "", "th": ""}

    def __init__(self):
        super().__init__()
        self.skip = 0
        self.lines, self.cur, self.prefix = [], [], ""

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        elif tag in self.BLOCK:
            self._flush()
            self.prefix = self.BLOCK[tag]

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            self.skip = max(0, self.skip - 1)
        elif tag in self.BLOCK:
            self._flush()

    def handle_data(self, data):
        if not self.skip:
            self.cur.append(data)

    def _flush(self):
        t = re.sub(r"\s+", " ", "".join(self.cur)).strip()
        if t:
            self.lines.append(self.prefix + t)
        self.cur, self.prefix = [], ""


def extract_text(html: str) -> str:
    m = re.search(r"<main\b.*?</main>", html, re.S | re.I) or re.search(r"<article\b.*?</article>", html, re.S | re.I)
    p = _Text()
    p.feed(m.group(0) if m else html)
    p._flush()
    return "\n\n".join(p.lines)


def load_manifest(path: Path) -> list[dict]:
    return (yaml.safe_load(path.read_text()) or {}).get("sources", []) if path.exists() else []


class Robots:
    def __init__(self, fetch):
        self.fetch, self.cache = fetch, {}

    def allowed(self, url: str) -> bool:
        u = urlparse(url)
        host = f"{u.scheme}://{u.netloc}"
        if host not in self.cache:
            rp = RobotFileParser()
            try:
                status, text = self.fetch(host + "/robots.txt")
                if status >= 400:  # no robots.txt: allowed, per the robots convention
                    text = ""
                rp.parse(text.splitlines())
            except Exception:  # noqa: BLE001  can't read robots.txt: be polite and skip the host
                rp.parse(["User-agent: *", "Disallow: /"])
            self.cache[host] = rp
        return self.cache[host].can_fetch(USER_AGENT, url)


def _log(store, doc, event, detail=""):
    store.q("INSERT INTO refresh_log(ts,doc,event,detail) VALUES(?,?,?,?)", (time.time(), doc, event, detail[:500]))


def _write_doc(path: Path, text: str, url: str):
    meta, _ = parse_front_matter(path.read_text(encoding="utf-8")) if path.exists() else ({}, "")
    meta.update(source_url=url, retrieved=date.today().isoformat())
    meta.setdefault("label", "public")  # manifest pages are public lcra.org pages
    path.write_text("---\n" + yaml.safe_dump(meta, sort_keys=False, allow_unicode=True) + "---\n\n" + text + "\n",
                    encoding="utf-8")


def run_refresh(rag, docs_dir: Path, manifest: Path, fetch=None) -> dict:
    """One refresh pass. Returns counts. Never raises for a single bad page."""
    if not _lock.acquire(blocking=False):
        return dict(status="already running")
    try:
        fetch = fetch or http_fetch
        store = rag.store
        init(store)
        robots = Robots(fetch)
        counts = dict(checked=0, baseline=0, changed=0, unchanged=0, skipped=0, errors=0)
        for src in load_manifest(manifest):
            url, rel = src["url"], src["file"]
            doc = Path(rel).name
            now = time.time()
            if not robots.allowed(url):
                counts["skipped"] += 1
                _log(store, doc, "skipped", f"robots.txt disallows {url}")
                continue
            try:
                status, html = fetch(url)
                if status != 200:
                    raise RuntimeError(f"HTTP {status}")
                text = extract_text(html)
                if len(text) < 200:
                    raise RuntimeError("page had almost no readable text")
            except Exception as e:  # noqa: BLE001
                counts["errors"] += 1
                _log(store, doc, "error", f"{url}: {e}")
                continue
            counts["checked"] += 1
            h = hashlib.sha256(text.encode()).hexdigest()
            prev = store.q("SELECT content_hash, last_changed FROM source_state WHERE doc = ?", (doc,))
            store.q("DELETE FROM source_state WHERE doc = ?", (doc,))
            if not prev:
                counts["baseline"] += 1
                store.q("INSERT INTO source_state VALUES(?,?,?,?,?)", (doc, url, h, now, None))
                _log(store, doc, "baseline", "first check; hash recorded, file left as committed")
            elif prev[0][0] != h:
                counts["changed"] += 1
                _write_doc(docs_dir / rel, text, url)
                store.q("INSERT INTO source_state VALUES(?,?,?,?,?)", (doc, url, h, now, now))
                _log(store, doc, "changed", f"page content changed; file rewritten from {url}")
            else:
                counts["unchanged"] += 1
                store.q("INSERT INTO source_state VALUES(?,?,?,?,?)", (doc, url, h, now, prev[0][1]))
        if counts["changed"]:
            chunks = ingest_dir(docs_dir, store, rag.provider)
            _log(store, "*", "reingested", f"{counts['changed']} changed page(s); index now {chunks} chunks")
        _log(store, "*", "run", ", ".join(f"{k} {v}" for k, v in counts.items()))
        return dict(status="ok", **counts)
    finally:
        _lock.release()


def changelog(store, n=50) -> list[dict]:
    init(store)
    return [dict(ts=ts, doc=d, event=e, detail=x) for ts, d, e, x in
            store.q("SELECT ts, doc, event, detail FROM refresh_log ORDER BY ts DESC LIMIT ?", (n,))]


def seconds_until(hour: int, now: datetime | None = None) -> float:
    now = now or datetime.now(CENTRAL)
    nxt = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if nxt <= now:
        nxt += timedelta(days=1)
    return (nxt - now).total_seconds()


def start_scheduler(rag, docs_dir: Path, manifest: Path, hour: int) -> threading.Thread:
    """A plain daemon thread: sleep until REFRESH_HOUR Central, refresh, repeat. Simple enough to read in one sitting."""
    def loop():
        while True:
            time.sleep(seconds_until(hour))
            try:
                run_refresh(rag, docs_dir, manifest)
            except Exception as e:  # noqa: BLE001  never kill the thread
                _log(rag.store, "*", "error", f"refresh run failed: {e}")
    t = threading.Thread(target=loop, name="nightly-refresh", daemon=True)
    t.start()
    return t
