"""Optional live-data tool: current Highland Lakes levels from LCRA Hydromet.

Source: https://hydromet.lcra.org/Reports/LakeLevel (public page). The page loads its table
from the JSON endpoint below. It is not a documented, supported API, so treat it as best-effort:
short timeout, no retries, and the assistant still answers from documents if it fails.

Off by default. Turn on with HYDROMET_LIVE=1. Tests replace `fetch` with a mock.
"""
from __future__ import annotations

import re

import httpx

URL = "https://hydromet.lcra.org/api/GetLakeLevelsForAllSites"
REPORT_URL = "https://hydromet.lcra.org/Reports/LakeLevel"

# Question keyword -> Hydromet "location" for the dam headwater gauge, plus the
# reference level from the LCRA documents in data/docs/lcra.
LAKES = {
    "travis": ("Mansfield Dam", "Lake Travis", (681.0, "full for water supply")),
    "buchanan": ("Buchanan Dam", "Lake Buchanan", (1020.0, "maximum managed level")),
    "inks": ("Inks Dam", "Inks Lake", None),
    "lbj": ("Wirtz Dam", "Lake LBJ", None),
    "marble falls": ("Starcke Dam", "Lake Marble Falls", None),
    "lake austin": ("Tom Miller Dam", "Lake Austin", None),
}
_LIVE = re.compile(r"\b(current|currently|now|today|right now|latest|live)\b", re.I)


def fetch(timeout: float = 5.0) -> list[dict]:
    r = httpx.get(URL, timeout=timeout, headers={"User-Agent": "utility-rag-assistant (POC)"})
    r.raise_for_status()
    return r.json()


def wants_live(question: str) -> list[str]:
    """Return lake keys if the question asks for a current level, else []."""
    if not _LIVE.search(question):
        return []
    q = question.lower()
    return [k for k in LAKES if k in q]


def live_context(question: str, fetcher=None) -> dict | None:
    keys = wants_live(question)
    if not keys:
        return None
    try:
        rows = (fetcher or fetch)()
    except Exception:  # live data is a bonus, never a hard dependency
        return None
    by_loc = {r.get("location"): r for r in rows}
    lines = []
    for k in keys:
        loc, name, full = LAKES[k]
        r = by_loc.get(loc)
        if not r or r.get("elevation") is None:
            continue
        line = (f"LIVE Hydromet reading: the current level of {name} (gauge at {loc}) is "
                f"{r['elevation']} feet msl as of {r.get('dateTime')} (UTC).")
        if full:
            ref, what = full
            line += f" That is {round(r['elevation'] - ref, 2)} feet relative to {ref:g} feet msl ({what}, per LCRA)."
        lines.append(line)
    if not lines:
        return None
    return dict(doc="hydromet-live", title="LCRA Hydromet live lake levels", label="public",
                source_url=REPORT_URL, score=1.0, text=" ".join(lines))
