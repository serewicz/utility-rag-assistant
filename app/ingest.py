"""Ingestion: read files, split into chunks, embed, store.

Each file starts with a small front-matter block:
---
title: ...
label: public | field-tech | cip-restricted
source_url: ...
---
PDFs and files without front matter get label from data/docs/labels.yaml or default to cip-restricted
(fail closed: if nobody labeled it, treat it as sensitive).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

DEFAULT_LABEL = "cip-restricted"


def read_file(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        from pypdf import PdfReader
        return "\n".join(p.extract_text() or "" for p in PdfReader(str(path)).pages)
    return path.read_text(encoding="utf-8")


def parse_front_matter(text: str) -> tuple[dict, str]:
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        return {}, text
    return yaml.safe_load(m.group(1)) or {}, text[m.end():]


_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")


def clean(text: str) -> str:
    """Keep link text, drop link targets. URLs waste tokens and confuse retrieval."""
    return _LINK.sub(r"\1", text)


def chunk(text: str, size: int = 800, overlap: int = 150) -> list[str]:
    """Split on paragraphs, then pack paragraphs into ~size-char chunks with overlap.
    Paragraph boundaries keep sentences whole; overlap keeps context across the cut."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks, cur = [], ""
    for p in paras:
        if cur and len(cur) + len(p) > size:
            chunks.append(cur)
            cur = cur[-overlap:] + "\n" + p
        else:
            cur = (cur + "\n\n" + p) if cur else p
    if cur:
        chunks.append(cur)
    return chunks


def ingest_dir(root: Path, store, provider) -> int:
    overrides = {}
    lf = root / "labels.yaml"
    if lf.exists():
        overrides = yaml.safe_load(lf.read_text()) or {}
    rows = []
    for path in sorted(root.rglob("*")):
        if path.suffix.lower() not in {".md", ".txt", ".pdf"}:
            continue
        meta, body = parse_front_matter(read_file(path))
        ov = overrides.get(path.name, {})
        if isinstance(ov, str):  # allow the short form `file.pdf: public`
            ov = {"label": ov}
        meta = {**meta, **ov}
        for i, c in enumerate(chunk(clean(body))):
            rows.append(dict(doc=path.name, title=meta.get("title", path.stem), label=meta.get("label", DEFAULT_LABEL),
                             source_url=meta.get("source_url", ""), ord=i, text=c))
    store.clear()
    for i in range(0, len(rows), 64):
        batch = rows[i:i + 64]
        for r, e in zip(batch, provider.embed([r["text"] for r in batch])):
            r["embedding"] = e
        store.add(batch)
    return len(rows)


if __name__ == "__main__":
    from .main import build
    rag = build()
    n = ingest_dir(Path(sys.argv[1] if len(sys.argv) > 1 else "data/docs"), rag.store, rag.provider)
    print(f"ingested {n} chunks")
