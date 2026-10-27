"""Drought and water-supply briefing: the dry-weather twin of the storm briefing.

One button puts on one screen:
  1. current Lake Travis and Lake Buchanan levels (LCRA Hydromet, best-effort) and how far
     each is below "full" (681 ft / 1,020 ft, only when a retrieved sentence states it),
  2. combined storage and the triggers in the Water Management Plan,
  3. how curtailment works (Drought Contingency Plan stages, DWDR, pro rata),
  4. what customers are asked to do.
Every line is a retrieved sentence with a citation, from documents the user's role may read.
Hydromet reports elevation, not storage, so storage numbers come only from the cited documents.
"""
from __future__ import annotations

import re
import time

from . import hydromet, rbac
from .briefing import _live, _sentences

QUESTION = "Drought briefing: lake levels, combined storage, Water Management Plan triggers, curtailment"
DISCLAIMER = ("Decision support only. The LCRA Board declares drought stages and curtailment. "
              "Check lcra.org and your water provider for current restrictions.")

FULL = {"travis": (681.0, r"\b681 feet", "full for water supply"),
        "buchanan": (1020.0, r"1,020 feet", "full / maximum managed level")}

SECTIONS = {
    "storage": (["combined storage of lakes Buchanan and Travis acre-feet percent full capacity",
                 "Drought Worse than Drought of Record DWDR declaration combined storage 600,000 acre-feet 30% of capacity",
                 "Lake Travis full at 681 feet Lake Buchanan 1,020 feet water supply storage"],
                re.compile(r"(combined storage|acre-feet|% (of capacity|full)|percent full|DWDR|681 feet|1,020 feet)", re.I)),
    "curtailment": (["mandatory pro rata curtailment firm customers Stage 4 Drought Contingency Plan",
                     "interruptible stored water cut off before curtailment of firm customers",
                     "initial minimum curtailment percentage"],
                    re.compile(r"(curtail|Stage \d|pro rata|interruptible)", re.I)),
    "customers": (["water use restrictions watering once a week conservation customers",
                   "firm customers develop curtailment plan allotments baseline year"],
                  re.compile(r"(restriction|water(ing)? landscapes|conserv|plan outlining|allot)", re.I)),
}
MAX_PER_SECTION = 5
NUM = re.compile(r"\d")

SYSTEM = ("You write a short drought and water-supply briefing for utility staff using ONLY the numbered context. "
          "Sections: Current levels (with reading time), Storage and triggers, How curtailment works, "
          "What customers are asked to do. Cite sources like [1]. Never predict rainfall, stages or "
          "curtailment. If live data is missing, say so.")


def drought_briefing(rag, user: str) -> dict:
    t0 = time.perf_counter()
    role, labels = rbac.labels_for(user)

    hits, seen = {}, set()
    for name, (queries, _) in SECTIONS.items():
        hits[name] = []
        for q in queries:
            for h in rag.store.search(rag.provider.embed([q])[0], labels, rag.s.top_k):
                if h["label"] in labels:  # defense in depth, same as /ask
                    hits[name].append(h)
    sources, doc_n = [], {}
    for h in (h for hs in hits.values() for h in hs):
        if h["doc"] not in doc_n:
            doc_n[h["doc"]] = len(sources) + 1
            sources.append(dict(n=doc_n[h["doc"]], doc=h["doc"], title=h["title"], label=h["label"],
                                source_url=h["source_url"]))

    facts = {}
    for name, (_, pat) in SECTIONS.items():
        picked = []
        for h in hits[name]:
            for s in _sentences(h["text"]):
                # Skip chunk-overlap fragments ("itial minimum...") and short headings.
                if s in seen or not pat.search(s) or not s[0].isupper() or len(s) < 45:
                    continue
                seen.add(s)
                picked.append(dict(text=s, cite=doc_n[h["doc"]]))
        # Sentences with numbers first: thresholds and percentages are what people act on.
        picked.sort(key=lambda x: not NUM.search(x["text"]))
        facts[name] = picked[:MAX_PER_SECTION]

    readings, live_error = _live(rag)
    if readings:
        live_n = len(sources) + 1
        sources.append(dict(n=live_n, doc="hydromet-live", title="LCRA Hydromet live lake levels",
                            label="public", source_url=hydromet.REPORT_URL))
    all_facts = [x for v in facts.values() for x in v]
    for r in readings:
        r["cite"] = live_n
        ft, pat, meaning = FULL[r["lake"]]
        support = next((x for x in all_facts if re.search(pat, x["text"])), None)
        r["vs_full"] = (dict(elevation_ft=ft, meaning=meaning, cite=support["cite"],
                             feet_from=round(r["elevation_ft"] - ft, 2)) if support else None)

    text = _template(readings, live_error, facts)
    tokens_in, tokens_out = sum(len(h["text"]) for hs in hits.values() for h in hs) // 4, len(text) // 4
    if rag.provider.name != "fake":
        ctx = "\n".join(f"[{s['n']}] {s['title']}" for s in sources) + "\n\nFacts:\n" + text
        res = rag.provider.chat(SYSTEM, f"Question: {QUESTION}\n\nContext:\n{ctx}")
        text, tokens_in, tokens_out = res.text.strip() + "\n\n" + DISCLAIMER, res.tokens_in, res.tokens_out

    cost = tokens_in / 1e6 * rag.s.price_in + tokens_out / 1e6 * rag.s.price_out
    latency = (time.perf_counter() - t0) * 1000
    rag.store.log(user=user, role=role, question="[briefing/drought] " + QUESTION, latency_ms=latency,
                  tokens_in=tokens_in, tokens_out=tokens_out, cost_usd=cost, provider=rag.provider.name,
                  sources=[s["doc"] for s in sources])
    return dict(kind="drought", answer=text, role=role, live_ok=live_error is None, live_error=live_error,
                readings=readings, facts=facts, sources=sources, disclaimer=DISCLAIMER,
                latency_ms=round(latency, 1), tokens_in=tokens_in, tokens_out=tokens_out,
                est_cost_usd=round(cost, 6))


def _template(readings, live_error, facts) -> str:
    out = ["DROUGHT AND WATER-SUPPLY BRIEFING: Highland Lakes", "", "Current levels"]
    if live_error:
        out.append(f"- {live_error} Using documents only. Check {hydromet.REPORT_URL}.")
    for r in readings:
        line = f"- {r['name']}: {r['elevation_ft']:g} ft msl at {r['time_central']} [{r['cite']}]"
        v = r.get("vs_full")
        if v:
            d = v["feet_from"]
            where = f"{abs(d):g} ft below" if d < 0 else f"{d:g} ft above"
            line += f"; {where} {v['elevation_ft']:g} ft ({v['meaning']}) [{v['cite']}]"
        out.append(line)
    heads = {"storage": "Storage and triggers", "curtailment": "How curtailment works",
             "customers": "What customers are asked to do"}
    for k, head in heads.items():
        out += ["", head]
        out += [f"- {x['text']} [{x['cite']}]" for x in facts[k]] or ["- No documents on this available to this user."]
    out += ["", DISCLAIMER]
    return "\n".join(out)
