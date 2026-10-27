"""Storm briefing: one button that combines live lake levels with the flood rules.

Decision support, not a decision. It puts three things on one screen:
  1. current Lake Travis and Lake Buchanan levels (LCRA Hydromet, best-effort),
  2. the key elevations and operations from LCRA documents the user may read (RBAC applies),
  3. who gets notified and how to sign up for FONS.
Every rule comes from a retrieved sentence with a citation. Nothing is predicted.

With the offline `fake` provider the briefing is a deterministic template filled from
retrieved sentences. With `openai` or `ollama` the same facts go to the model for a
richer summary, and the structured facts are still returned alongside it.
"""
from __future__ import annotations

import re
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from . import hydromet, rbac

# The ingester drops link targets, so the FONS sign-up URL (from that page) is kept here and
# shown only when the FONS page itself was retrieved for this user.
FONS_DOC = "lcra-floodgate-operations-notification-system.md"
FONS_SIGNUP = "https://getrave.com/login/extlcra"
CENTRAL = ZoneInfo("America/Chicago")
QUESTION = "Storm briefing: Lake Travis and Lake Buchanan levels, flood operations, FONS"
DISCLAIMER = ("Decision support only. LCRA River Operations decides flood releases. For warnings, "
              "follow the National Weather Service and local emergency management. FONS is not a flood warning service.")

# Lake key -> threshold elevation used to compute "feet from" in the briefing. Each value is
# shown only if a retrieved, citable sentence states it.
THRESHOLDS = {
    "travis": [(681.0, r"\b681 feet", "floodgate releases can begin / full for water supply"),
               (714.0, r"\b714 feet", "water flows over the Mansfield Dam spillway")],
    "buchanan": [(1020.0, r"1,020 feet", "maximum managed level; no flood storage above full")],
}

# Retrieval queries, one per section of the briefing.
QUERIES = {
    "rules": ["Lake Travis exceeds 681 feet msl LCRA can begin floodgate releases Mansfield Dam spillway 714 feet",
              "Lake Buchanan maximum level 1,020 feet no room to store floodwaters"],
    "notify": ["FONS Flood Operations Notification Service subscribers notified email text phone sign up registration",
               "FONS is not a flood warning service"],
}
RULE_PAT = re.compile(r"(681 feet|714 feet|1,020 feet|flood pool|floodgate releases|halted or reduced)", re.I)
NOTIFY_PAT = re.compile(r"(FONS|notif|subscrib|registration|register)", re.I)

SYSTEM = ("You write a short storm briefing for utility staff using ONLY the numbered context. "
          "Sections: Current levels (with reading time), Key elevations and what happens at each, "
          "Who is notified and how to sign up for FONS. Cite sources like [1]. Never predict releases "
          "or give safety instructions beyond the context. If live data is missing, say so.")


def to_central(ts: str | None) -> str | None:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return ts
    if dt.tzinfo is None:  # Hydromet times are UTC
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt.astimezone(CENTRAL).strftime("%b %d, %Y %I:%M %p %Z").replace(" 0", " ")


def _sentences(text: str) -> list[str]:
    # Markdown links -> "text (url)" for absolute URLs, "text" for site-relative ones.
    text = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r"\1 (\2)", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = text.replace("**", "")
    out = []
    for s in re.split(r"(?<=[.!?])\s+(?=[A-Z])|\n+", text):
        s = s.strip(" *-")
        if len(s) > 25 and not s.startswith("#"):
            out.append(s)
    return out


def _live(rag) -> tuple[list[dict], str | None]:
    """Return (readings, error). Never raises."""
    if not rag.s.hydromet_live:
        return [], "Live lake levels are turned off (HYDROMET_LIVE=0)."
    try:
        rows = (rag.hydromet_fetch or hydromet.fetch)()
        by_loc = {r.get("location"): r for r in rows}
    except Exception as e:  # noqa: BLE001
        return [], f"Live Hydromet data is unavailable right now ({type(e).__name__})."
    out = []
    for key in ("travis", "buchanan"):
        loc, name, _ = hydromet.LAKES[key]
        r = by_loc.get(loc)
        if r and r.get("elevation") is not None:
            out.append(dict(lake=key, name=name, gauge=loc, elevation_ft=float(r["elevation"]),
                            time_utc=r.get("dateTime"), time_central=to_central(r.get("dateTime"))))
    if not out:
        return [], "Live Hydromet data returned no Travis or Buchanan readings."
    return out, None


def flood_briefing(rag, user: str) -> dict:
    t0 = time.perf_counter()
    role, labels = rbac.labels_for(user)

    # 1. Retrieve, filtered by the user's labels, then re-checked (defense in depth).
    hits, seen = [], set()
    for qs in QUERIES.values():
        for q in qs:
            for h in rag.store.search(rag.provider.embed([q])[0], labels, rag.s.top_k):
                key = (h["doc"], h["text"][:80])
                if h["label"] in labels and key not in seen:
                    seen.add(key)
                    hits.append(h)
    sources, doc_n = [], {}
    for h in hits:
        if h["doc"] not in doc_n:
            doc_n[h["doc"]] = len(sources) + 1
            sources.append(dict(n=doc_n[h["doc"]], doc=h["doc"], title=h["title"], label=h["label"],
                                source_url=h["source_url"]))

    # 2. Pull the rule and notification sentences, each with its citation number.
    cands, notify, seen_s = [], [], set()
    for h in hits:
        for s in _sentences(h["text"]):
            if s in seen_s:
                continue
            seen_s.add(s)
            n = doc_n[h["doc"]]
            if RULE_PAT.search(s):
                cands.append(dict(text=s, cite=n))
            elif NOTIFY_PAT.search(s) and len(notify) < 5:
                notify.append(dict(text=s, cite=n))
    # First the earliest sentence stating each key elevation, then up to two general rules.
    rules = []
    for lake in THRESHOLDS.values():
        for _, pat, _ in lake:
            hit = next((c for c in cands if re.search(pat, c["text"]) and c not in rules), None)
            if hit:
                rules.append(hit)
    rules += [c for c in cands if c not in rules and re.search(r"halted or reduced|flood pool", c["text"])][:2]

    # 3. Live levels, compared only against thresholds a cited sentence supports.
    readings, live_error = _live(rag)
    if readings:
        live_n = len(sources) + 1
        sources.append(dict(n=live_n, doc="hydromet-live", title="LCRA Hydromet live lake levels",
                            label="public", source_url=hydromet.REPORT_URL))
    for r in readings:
        r["cite"] = live_n
        r["vs_key_elevations"] = []
        for ft, pat, meaning in THRESHOLDS[r["lake"]]:
            support = next((x for x in rules if re.search(pat, x["text"])), None)
            if support:
                r["vs_key_elevations"].append(dict(elevation_ft=ft, meaning=meaning, cite=support["cite"],
                                                   feet_from=round(r["elevation_ft"] - ft, 2)))

    fons = next((x["n"] for x in sources if x["doc"].endswith(FONS_DOC)), None)
    text = _template(readings, live_error, rules, notify, fons)
    tokens_in, tokens_out = 0, len(text) // 4
    if rag.provider.name != "fake":
        ctx = "\n".join(f"[{s['n']}] {s['title']}" for s in sources) + "\n\nFacts:\n" + text
        res = rag.provider.chat(SYSTEM, f"Question: {QUESTION}\n\nContext:\n{ctx}")
        text, tokens_in, tokens_out = res.text.strip() + "\n\n" + DISCLAIMER, res.tokens_in, res.tokens_out
    else:
        tokens_in = sum(len(h["text"]) for h in hits) // 4

    cost = tokens_in / 1e6 * rag.s.price_in + tokens_out / 1e6 * rag.s.price_out
    latency = (time.perf_counter() - t0) * 1000
    rag.store.log(user=user, role=role, question="[briefing/flood] " + QUESTION, latency_ms=latency,
                  tokens_in=tokens_in, tokens_out=tokens_out, cost_usd=cost, provider=rag.provider.name,
                  sources=[s["doc"] for s in sources])
    return dict(kind="flood", answer=text, role=role, live_ok=live_error is None, live_error=live_error,
                readings=readings, rules=rules, notify=notify, sources=sources, disclaimer=DISCLAIMER,
                latency_ms=round(latency, 1), tokens_in=tokens_in, tokens_out=tokens_out,
                est_cost_usd=round(cost, 6))


def _template(readings, live_error, rules, notify, signup=None) -> str:
    out = ["STORM BRIEFING: Highland Lakes", "", "Current levels"]
    if live_error:
        out.append(f"- {live_error} Using documents only. Check {hydromet.REPORT_URL}.")
    for r in readings:
        line = f"- {r['name']}: {r['elevation_ft']:g} ft msl at {r['time_central']} [{r['cite']}]"
        for k in r["vs_key_elevations"]:
            d = k["feet_from"]
            where = f"{abs(d):g} ft below" if d < 0 else f"{d:g} ft above"
            line += f"; {where} {k['elevation_ft']:g} ft ({k['meaning']}) [{k['cite']}]"
        out.append(line)
    out += ["", "Key elevations and operations"]
    out += [f"- {x['text']} [{x['cite']}]" for x in rules] or ["- No flood-operation documents available to this user."]
    out += ["", "Who is notified and how"]
    out += [f"- {x['text']} [{x['cite']}]" for x in notify] or ["- No FONS documents available to this user."]
    if signup:
        out.append(f"- Sign up for FONS: {FONS_SIGNUP} [{signup}]")
    out += ["", DISCLAIMER]
    return "\n".join(out)
