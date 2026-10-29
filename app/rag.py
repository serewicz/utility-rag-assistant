"""The RAG pipeline: authorize -> retrieve -> prompt -> generate -> log."""
from __future__ import annotations

import time
import uuid

from . import hydromet, measure, rbac

SYSTEM = ("You answer questions for utility staff using ONLY the numbered context. "
          "Cite sources like [1]. If the context does not contain the answer, say you don't know. "
          "Never guess about safety or compliance steps.")


class RAG:
    def __init__(self, store, provider, settings):
        self.store, self.provider, self.s = store, provider, settings
        self.hydromet_fetch = None  # tests inject a mock here
        measure.init(store)  # outcome, feedback and eval tables (idempotent)

    def ask(self, user: str, question: str, log: bool = True, include_text: bool = False) -> dict:
        """log=False is for evals, so test traffic does not show up as real usage on the dashboard.

        include_text=True adds each passage's text to its source. Only hits that passed the
        caller's label filter are ever in `hits`, so text is limited to what the caller may see."""
        t0 = time.perf_counter()
        role, labels = rbac.labels_for(user)
        qvec = self.provider.embed([question])[0]
        hits = self.store.search(qvec, labels, self.s.top_k)
        # Defense in depth: re-check every hit even though the query already filtered.
        hits = [h for h in hits if h["label"] in labels]
        # Optional tool call: live lake levels (public data), placed first in the context.
        if self.s.hydromet_live:
            live = hydromet.live_context(question, self.hydromet_fetch)
            if live:
                hits = [live] + hits
        ctx = "\n\n".join(f"[{i+1}] ({h['title']}) {h['text']}" for i, h in enumerate(hits))
        res = self.provider.chat(SYSTEM, f"Question: {question}\n\nContext:\n{ctx}")
        cost = res.tokens_in / 1e6 * self.s.price_in + res.tokens_out / 1e6 * self.s.price_out
        latency = (time.perf_counter() - t0) * 1000
        sources = [dict(n=i + 1, doc=h["doc"], title=h["title"], label=h["label"],
                        source_url=h["source_url"], score=round(h["score"], 3), **({"text": h["text"]} if include_text else {}))
                   for i, h in enumerate(hits)]
        qid = uuid.uuid4().hex
        top = max((h["score"] for h in hits if h["doc"] != "hydromet-live"), default=None)
        if log:
            measure.record_outcome(self.store, qid, user, role, question, res.text, top)
            self.store.log(user=user, role=role, question=question, latency_ms=latency, tokens_in=res.tokens_in,
                       tokens_out=res.tokens_out, cost_usd=cost, provider=self.provider.name,
                           sources=[s["doc"] for s in sources])
        return dict(qid=qid, answer=res.text, role=role, sources=sources, latency_ms=round(latency, 1),
                    tokens_in=res.tokens_in, tokens_out=res.tokens_out, est_cost_usd=round(cost, 6))
