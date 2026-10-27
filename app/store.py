"""Storage: chunks + vectors + query log.

Two backends with the same interface:
- SQLiteStore: zero setup, brute-force cosine search. Used by tests and laptops.
- PgVectorStore: Postgres + pgvector, used by docker compose. Scales to millions of chunks.
"""
from __future__ import annotations

import json
import math
import sqlite3
import time


def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(x * x for x in b)) or 1.0
    return dot / (na * nb)


LOG_COLS = "ts, user_name, role, question, latency_ms, tokens_in, tokens_out, cost_usd, provider, sources"


class SQLiteStore:
    def __init__(self, path=":memory:"):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS chunks(id INTEGER PRIMARY KEY, doc TEXT, title TEXT, label TEXT,
            source_url TEXT, ord INTEGER, text TEXT, embedding TEXT);
        CREATE TABLE IF NOT EXISTS query_log(id INTEGER PRIMARY KEY, ts REAL, user_name TEXT, role TEXT,
            question TEXT, latency_ms REAL, tokens_in INTEGER, tokens_out INTEGER, cost_usd REAL,
            provider TEXT, sources TEXT);""")

    def clear(self):
        self.db.execute("DELETE FROM chunks"); self.db.commit()

    def add(self, rows):
        self.db.executemany(
            "INSERT INTO chunks(doc,title,label,source_url,ord,text,embedding) VALUES(?,?,?,?,?,?,?)",
            [(r["doc"], r["title"], r["label"], r["source_url"], r["ord"], r["text"], json.dumps(r["embedding"])) for r in rows])
        self.db.commit()

    def search(self, qvec, labels, k):
        marks = ",".join("?" * len(labels))
        # The label filter is part of the query itself. Restricted rows are never loaded.
        cur = self.db.execute(
            f"SELECT doc,title,label,source_url,ord,text,embedding FROM chunks WHERE label IN ({marks})",
            sorted(labels))
        scored = []
        for doc, title, label, url, ord_, text, emb in cur:
            scored.append((cosine(qvec, json.loads(emb)), dict(doc=doc, title=title, label=label,
                                                                source_url=url, ord=ord_, text=text)))
        scored.sort(key=lambda x: -x[0])
        return [dict(score=s, **c) for s, c in scored[:k]]

    def log(self, **r):
        self.db.execute(f"INSERT INTO query_log({LOG_COLS}) VALUES(?,?,?,?,?,?,?,?,?,?)",
                        (time.time(), r["user"], r["role"], r["question"], r["latency_ms"], r["tokens_in"],
                         r["tokens_out"], r["cost_usd"], r["provider"], json.dumps(r["sources"])))
        self.db.commit()

    def stats(self):
        row = self.db.execute("""SELECT COUNT(*), COALESCE(AVG(latency_ms),0), COALESCE(SUM(tokens_in),0),
            COALESCE(SUM(tokens_out),0), COALESCE(SUM(cost_usd),0) FROM query_log""").fetchone()
        by_role = dict(self.db.execute("SELECT role, COUNT(*) FROM query_log GROUP BY role").fetchall())
        chunks = self.db.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        return dict(queries=row[0], avg_latency_ms=round(row[1], 1), tokens_in=row[2], tokens_out=row[3],
                    est_cost_usd=round(row[4], 6), queries_by_role=by_role, chunks=chunks)

    def recent(self, n=20):
        cur = self.db.execute(f"SELECT {LOG_COLS} FROM query_log ORDER BY id DESC LIMIT ?", (n,))
        cols = [c.strip() for c in LOG_COLS.split(",")]
        return [dict(zip(cols, r)) for r in cur]


class PgVectorStore(SQLiteStore):
    """Postgres + pgvector. Same interface; search runs in the database with an index.
    NOTE: not exercised by the offline test suite (no docker on the build box)."""

    def __init__(self, url, dim):
        import psycopg
        self.dim = dim
        self.pg = psycopg.connect(url, autocommit=True)
        self.pg.execute("CREATE EXTENSION IF NOT EXISTS vector")
        self.pg.execute(f"""CREATE TABLE IF NOT EXISTS chunks(id SERIAL PRIMARY KEY, doc TEXT, title TEXT,
            label TEXT, source_url TEXT, ord INT, text TEXT, embedding vector({dim}))""")
        self.pg.execute("""CREATE TABLE IF NOT EXISTS query_log(id SERIAL PRIMARY KEY, ts DOUBLE PRECISION,
            user_name TEXT, role TEXT, question TEXT, latency_ms REAL, tokens_in INT, tokens_out INT,
            cost_usd REAL, provider TEXT, sources TEXT)""")
        self.pg.execute("CREATE INDEX IF NOT EXISTS chunks_label ON chunks(label)")

    def clear(self):
        self.pg.execute("DELETE FROM chunks")

    def add(self, rows):
        with self.pg.cursor() as c:
            c.executemany("INSERT INTO chunks(doc,title,label,source_url,ord,text,embedding) VALUES(%s,%s,%s,%s,%s,%s,%s::vector)",
                          [(r["doc"], r["title"], r["label"], r["source_url"], r["ord"], r["text"], str(r["embedding"])) for r in rows])

    def search(self, qvec, labels, k):
        cur = self.pg.execute("""SELECT doc,title,label,source_url,ord,text, 1-(embedding <=> %s::vector) AS score
            FROM chunks WHERE label = ANY(%s) ORDER BY embedding <=> %s::vector LIMIT %s""",
                              (str(qvec), sorted(labels), str(qvec), k))
        cols = ["doc", "title", "label", "source_url", "ord", "text", "score"]
        return [dict(zip(cols, r)) for r in cur]

    def log(self, **r):
        self.pg.execute(f"INSERT INTO query_log({LOG_COLS}) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (time.time(), r["user"], r["role"], r["question"], r["latency_ms"], r["tokens_in"],
                         r["tokens_out"], r["cost_usd"], r["provider"], json.dumps(r["sources"])))

    def stats(self):
        row = self.pg.execute("""SELECT COUNT(*), COALESCE(AVG(latency_ms),0), COALESCE(SUM(tokens_in),0),
            COALESCE(SUM(tokens_out),0), COALESCE(SUM(cost_usd),0) FROM query_log""").fetchone()
        by_role = dict(self.pg.execute("SELECT role, COUNT(*) FROM query_log GROUP BY role").fetchall())
        chunks = self.pg.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        return dict(queries=row[0], avg_latency_ms=round(float(row[1]), 1), tokens_in=int(row[2]),
                    tokens_out=int(row[3]), est_cost_usd=round(float(row[4]), 6), queries_by_role=by_role, chunks=chunks)

    def recent(self, n=20):
        cur = self.pg.execute(f"SELECT {LOG_COLS} FROM query_log ORDER BY id DESC LIMIT %s", (n,))
        cols = [c.strip() for c in LOG_COLS.split(",")]
        return [dict(zip(cols, r)) for r in cur]
