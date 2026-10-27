"""Run the golden set and print retrieval hit-rate and answer accuracy.
Usage: python -m evals.run_evals   (uses LLM_PROVIDER from env; fake by default)"""
from __future__ import annotations

from pathlib import Path

import yaml

from app.config import Settings
from app.ingest import ingest_dir
from app.main import ROOT, build

GOLDEN = yaml.safe_load((Path(__file__).parent / "golden.yaml").read_text())


def run(rag=None, k=None):
    if rag is None:
        rag = build(Settings(), sqlite_path=":memory:")
        ingest_dir(ROOT / "data" / "docs", rag.store, rag.provider)
    hits = correct = 0
    rows = []
    for g in GOLDEN:
        r = rag.ask(g["user"], g["question"])
        docs = [s["doc"] for s in r["sources"]]
        hit = g["expect_doc"] in docs
        ok = all(w.lower() in r["answer"].lower() for w in g["answer_contains"])
        hits += hit; correct += ok
        rows.append((hit, ok, g["question"]))
    n = len(GOLDEN)
    return dict(n=n, retrieval_hit_rate=hits / n, answer_accuracy=correct / n, rows=rows)


if __name__ == "__main__":
    res = run()
    for hit, ok, q in res["rows"]:
        print(f"{'HIT ' if hit else 'MISS'} {'PASS' if ok else 'FAIL'}  {q}")
    print(f"\nretrieval hit-rate: {res['retrieval_hit_rate']:.0%}   answer accuracy: {res['answer_accuracy']:.0%}")
