"""Governance: what data the assistant uses, who owns it, and what model reads it.

A governance review asks the same questions every time: Which sources? Who owns each one?
How sensitive is it? When was it last refreshed? Which model and provider see it?
This module answers them from the live index plus one small config file,
data/governance.yaml. It is deliberately the seed of a separate governance repo
(model and use-case registry, risk assessment, NIST AI RMF mapping).
"""
from __future__ import annotations

from pathlib import Path

import yaml

from .ingest import parse_front_matter

DEFAULT_OWNER = "unassigned"


def load_config(path: Path) -> dict:
    if path.exists():
        return yaml.safe_load(path.read_text()) or {}
    return {}


def _file_meta(docs_dir: Path) -> dict[str, dict]:
    """Front matter per file name (title, retrieved date). PDFs have none."""
    out = {}
    for p in docs_dir.rglob("*"):
        if p.suffix.lower() in {".md", ".txt"}:
            meta, _ = parse_front_matter(p.read_text(encoding="utf-8"))
            out[p.name] = meta
    return out


def _owner(cfg: dict, doc: str, label: str) -> str:
    owners = cfg.get("owners") or {}
    if doc in owners:
        return owners[doc]
    for prefix, who in (cfg.get("owner_prefixes") or {}).items():
        if doc.startswith(prefix):
            return who
    return (cfg.get("label_owners") or {}).get(label, DEFAULT_OWNER)


def report(rag, docs_dir: Path, cfg_path: Path) -> dict:
    cfg = load_config(cfg_path)
    meta = _file_meta(docs_dir)
    refreshed = {}
    try:  # the nightly refresh (refresh.py) records the latest check per document
        for doc, ts_checked, ts_changed in rag.store.q("SELECT doc, last_checked, last_changed FROM source_state"):
            refreshed[doc] = dict(last_checked=ts_checked, last_changed=ts_changed)
    except Exception:  # noqa: BLE001  table not there yet
        pass
    rows = rag.store.q("""SELECT doc, title, label, source_url, COUNT(*) FROM chunks
                          GROUP BY doc, title, label, source_url ORDER BY label, doc""")
    sources = []
    for doc, title, label, url, n in rows:
        m = meta.get(doc, {})
        r = refreshed.get(doc, {})
        sources.append(dict(doc=doc, title=title, label=label, source_url=url or None, chunks=int(n),
                            owner=_owner(cfg, doc, label), retrieved=str(m.get("retrieved") or "") or None,
                            last_checked=r.get("last_checked"), last_changed=r.get("last_changed")))
    s = rag.s
    p = rag.provider.name
    chat_model = {"openai": s.openai_chat, "ollama": s.ollama_chat}.get(p, "fake (offline extractive, no model)")
    embed_model = {"openai": s.openai_embed, "ollama": s.ollama_embed}.get(p, "fake (hashed bag of words)")
    endpoint = {"openai": s.openai_base, "ollama": s.ollama_base}.get(p, "none, runs in-process")
    return dict(
        system=dict(name=cfg.get("system_name", "Utility RAG Assistant"),
                    business_owner=cfg.get("business_owner", DEFAULT_OWNER),
                    use_case=cfg.get("use_case", ""), risk_tier=cfg.get("risk_tier", "unassessed")),
        model=dict(provider=p, chat_model=chat_model, embedding_model=embed_model, endpoint=endpoint,
                   data_leaves_network=p == "openai" and "api.openai.com" in s.openai_base,
                   live_tools=["LCRA Hydromet lake levels"] if s.hydromet_live else []),
        policy_notes=cfg.get("policy_notes", "/policy"),
        totals=dict(sources=len(sources), chunks=sum(x["chunks"] for x in sources),
                    unowned=sum(x["owner"] == DEFAULT_OWNER for x in sources),
                    by_label={lb: sum(x["label"] == lb for x in sources) for lb in sorted({x["label"] for x in sources})}),
        sources=sources)
