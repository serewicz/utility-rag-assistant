"""Measurement: outcomes, feedback, eval runs, the dashboard numbers and the gap report.

Why this exists: a director does not buy "we deployed a chatbot". They buy
"people asked 412 questions, 88% were answered with a citation, it cost $3.10,
and here are the 12 questions it could not answer, so here is what to add next."

Everything here uses three small tables next to query_log. They are created with
CREATE TABLE IF NOT EXISTS, so an existing database picks them up without a reset.
"""
from __future__ import annotations

import json
import re
import time
from collections import Counter, defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

from .providers import words

CENTRAL = ZoneInfo("America/Chicago")

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS outcomes(qid TEXT, ts DOUBLE PRECISION, user_name TEXT, role TEXT,
        question TEXT, answered INTEGER, top_score DOUBLE PRECISION, kind TEXT)""",
    """CREATE TABLE IF NOT EXISTS feedback(qid TEXT, ts DOUBLE PRECISION, user_name TEXT,
        rating INTEGER, comment TEXT)""",
    """CREATE TABLE IF NOT EXISTS eval_runs(ts DOUBLE PRECISION, provider TEXT, n INTEGER,
        retrieval_hit_rate DOUBLE PRECISION, answer_accuracy DOUBLE PRECISION, rows_json TEXT)""",
]

# An answer counts as "unanswered" if the model said so, or if the best retrieved chunk
# was a weak match. The threshold is a starting point: tune it by reading the gap report.
IDK = re.compile(r"(don't know|do not know|not in the (provided )?context|no information|cannot find|can't find)", re.I)
import os
LOW_SCORE = float(os.environ.get("LOW_CONFIDENCE_SCORE", "0.15"))

# Gap-report topics: keywords -> the topic name and the documents that would close the gap.
# Plain keyword matching on purpose: it is explainable in a meeting and easy to edit.
TOPICS = [
    ("Drought and curtailment", {"drought", "curtailment", "conservation", "restriction", "restrictions", "storage"},
     ["LCRA Drought Contingency Plan (PDF)", "Combined storage history for Lakes Travis and Buchanan"]),
    ("Floods and dam operations", {"flood", "floodgate", "floodgates", "release", "releases", "spillway", "dam", "dams", "gate"},
     ["LCRA Water Control Manual / flood operations manual (PDF)", "Dam safety and emergency action plan summaries (public parts)"]),
    ("Lake levels and forecasts", {"level", "levels", "forecast", "elevation", "rain", "rainfall", "inflow", "inflows"},
     ["Hydromet river and rainfall reports", "NWS West Gulf River Forecast Center links"]),
    ("Water contracts and rates", {"rate", "rates", "contract", "contracts", "price", "billing", "acre", "customer", "customers"},
     ["Current firm water rate schedule (PDF)", "Water contract rules (LCRA Board policy)"]),
    ("Grid, transmission and outages", {"outage", "outages", "transmission", "substation", "feeder", "line", "lines", "power", "grid"},
     ["Internal outage and switching procedures (restricted label)", "Transmission project pages on lcra.org"]),
    ("NERC CIP compliance", {"cip", "nerc", "patch", "patching", "access", "cyber", "baseline", "audit"},
     ["Full NERC CIP standard text from nerc.com", "Your internal CIP procedures (cip-restricted label)"]),
    ("Parks and recreation", {"park", "parks", "boat", "boating", "camping", "swim", "fishing"},
     ["LCRA parks pages", "Boating safety and lake closure notices"]),
]


def init(store):
    for sql in SCHEMA:
        store.q(sql)


def is_unanswered(answer: str, top_score: float | None) -> bool:
    return bool(IDK.search(answer or "")) or top_score is None or top_score < LOW_SCORE


def record_outcome(store, qid, user, role, question, answer, top_score, kind="ask"):
    store.q("INSERT INTO outcomes(qid,ts,user_name,role,question,answered,top_score,kind) VALUES(?,?,?,?,?,?,?,?)",
            (qid, time.time(), user, role, question, 0 if is_unanswered(answer, top_score) else 1,
             top_score, kind))


def add_feedback(store, qid: str, user: str, rating: int, comment: str = ""):
    if rating not in (1, -1):
        raise ValueError("rating must be 1 (thumbs up) or -1 (thumbs down)")
    if not store.q("SELECT qid FROM outcomes WHERE qid = ?", (qid,)):
        raise KeyError(qid)
    store.q("INSERT INTO feedback(qid,ts,user_name,rating,comment) VALUES(?,?,?,?,?)",
            (qid, time.time(), user, rating, (comment or "")[:1000]))


def save_eval_run(store, provider: str, res: dict):
    store.q("INSERT INTO eval_runs(ts,provider,n,retrieval_hit_rate,answer_accuracy,rows_json) VALUES(?,?,?,?,?,?)",
            (time.time(), provider, res["n"], res["retrieval_hit_rate"], res["answer_accuracy"],
             json.dumps([dict(hit=bool(h), ok=bool(o), question=q) for h, o, q in res["rows"]])))


def _day(ts: float) -> str:
    return datetime.fromtimestamp(ts, CENTRAL).strftime("%Y-%m-%d")


def topic_for(question: str) -> tuple[str, list[str]]:
    ws = set(words(question))
    best = max(TOPICS, key=lambda t: len(ws & t[1]))
    if ws & best[1]:
        return best[0], best[2]
    return "Other", []


def gap_report(store, limit: int = 200) -> list[dict]:
    rows = store.q("""SELECT question, role, top_score, ts FROM outcomes WHERE answered = 0 AND kind = 'ask'
                      ORDER BY ts DESC LIMIT ?""", (limit,))
    # Thumbs-down answers are gaps too, even if the model produced something.
    rows += store.q("""SELECT o.question, o.role, o.top_score, o.ts FROM feedback f JOIN outcomes o ON o.qid = f.qid
                       WHERE f.rating = -1 AND o.answered = 1""")
    groups: dict[str, dict] = {}
    for question, role, score, ts in rows:
        topic, suggest = topic_for(question)
        g = groups.setdefault(topic, dict(topic=topic, suggested_docs=suggest, questions=[], keywords=Counter()))
        g["questions"].append(dict(question=question, role=role,
                                   top_score=None if score is None else round(float(score), 3), day=_day(ts)))
        g["keywords"].update(words(question))
    out = []
    for g in sorted(groups.values(), key=lambda g: -len(g["questions"])):
        g["count"] = len(g["questions"])
        g["keywords"] = [w for w, _ in g["keywords"].most_common(5)]
        if not g["suggested_docs"]:
            g["suggested_docs"] = [f"Documents that cover: {', '.join(g['keywords'][:3])}"]
        out.append(g)
    return out


def dashboard(store) -> dict:
    per_day = defaultdict(lambda: dict(questions=0, cost_usd=0.0, latency_sum=0.0))
    for ts, cost, lat in store.q("SELECT ts, cost_usd, latency_ms FROM query_log"):
        d = per_day[_day(ts)]
        d["questions"] += 1
        d["cost_usd"] += float(cost or 0)
        d["latency_sum"] += float(lat or 0)
    days = []
    for day in sorted(per_day)[-30:]:
        d = per_day[day]
        days.append(dict(day=day, questions=d["questions"], cost_usd=round(d["cost_usd"], 6),
                         avg_latency_ms=round(d["latency_sum"] / d["questions"], 1)))
    total, answered = store.q("SELECT COUNT(*), COALESCE(SUM(answered),0) FROM outcomes WHERE kind = 'ask'")[0]
    up, down = store.q("""SELECT COALESCE(SUM(CASE WHEN rating=1 THEN 1 ELSE 0 END),0),
                                 COALESCE(SUM(CASE WHEN rating=-1 THEN 1 ELSE 0 END),0) FROM feedback""")[0]
    comments = [dict(question=q, rating=r, comment=c, user=u, day=_day(ts)) for q, r, c, u, ts in store.q(
        """SELECT o.question, f.rating, f.comment, f.user_name, f.ts FROM feedback f JOIN outcomes o ON o.qid = f.qid
           WHERE f.comment <> '' ORDER BY f.ts DESC LIMIT 10""")]
    evals = [dict(day=_day(ts), provider=p, n=n, retrieval_hit_rate=round(float(h), 3), answer_accuracy=round(float(a), 3))
             for ts, p, n, h, a in store.q(
                 "SELECT ts, provider, n, retrieval_hit_rate, answer_accuracy FROM eval_runs ORDER BY ts DESC LIMIT 10")]
    s = store.stats()
    total, answered, up, down = int(total), int(answered), int(up), int(down)
    return dict(
        totals=dict(queries=s["queries"], est_cost_usd=s["est_cost_usd"], avg_latency_ms=s["avg_latency_ms"],
                    asked=total, unanswered=total - answered,
                    unanswered_rate=round((total - answered) / total, 3) if total else 0.0,
                    cost_per_question=round(s["est_cost_usd"] / s["queries"], 6) if s["queries"] else 0.0,
                    thumbs_up=up, thumbs_down=down),
        per_day=days, latest_eval=evals[0] if evals else None, eval_history=evals,
        feedback_comments=comments, gaps=gap_report(store))
