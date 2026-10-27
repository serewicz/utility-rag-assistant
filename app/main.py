"""FastAPI app. Run: uvicorn app.main:app --reload"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Header
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .config import Settings
from .ingest import ingest_dir
from .providers import get_provider
from .rag import RAG
from .store import PgVectorStore, SQLiteStore

ROOT = Path(__file__).resolve().parent.parent


def build(settings: Settings | None = None, sqlite_path: str | None = None) -> RAG:
    s = settings or Settings()
    provider = get_provider(s)
    if s.database_url.startswith("postgres"):
        dim = len(provider.embed(["dimension probe"])[0])
        store = PgVectorStore(s.database_url, dim)
    else:
        store = SQLiteStore(sqlite_path or s.sqlite_path)
    return RAG(store, provider, s)


class Ask(BaseModel):
    question: str


def create_app(rag: RAG | None = None, docs_dir: Path = ROOT / "data" / "docs") -> FastAPI:
    rag = rag or build()
    app = FastAPI(title="Utility RAG Assistant")
    app.state.rag = rag
    if rag.store.stats()["chunks"] == 0:
        ingest_dir(docs_dir, rag.store, rag.provider)

    @app.post("/ask")
    def ask(body: Ask, x_user: str = Header(default="guest")):
        # Demo auth: the X-User header. Replace with SSO/OIDC in production.
        return rag.ask(x_user, body.question)

    @app.get("/metrics")
    def metrics():
        return {**rag.store.stats(), "provider": rag.provider.name, "recent": rag.store.recent(10)}

    @app.post("/admin/reingest")
    def reingest():
        return {"chunks": ingest_dir(docs_dir, rag.store, rag.provider)}

    @app.get("/healthz")
    def health():
        return {"ok": True}

    @app.get("/")
    def index():
        return FileResponse(ROOT / "app" / "static" / "index.html")

    return app

