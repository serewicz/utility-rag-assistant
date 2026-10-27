"""FastAPI app. Run: uvicorn app.main:app --reload"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .config import Settings
from . import measure, rbac
from .briefing import flood_briefing
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


class Feedback(BaseModel):
    qid: str
    rating: int  # 1 = thumbs up, -1 = thumbs down
    comment: str = ""


def require_admin(user: str):
    if not rbac.is_admin(user):
        raise HTTPException(403, "admin role required")


def create_app(rag: RAG | None = None, docs_dir: Path = ROOT / "data" / "docs") -> FastAPI:
    rag = rag or build()
    app = FastAPI(title="Utility RAG Assistant")
    app.state.rag = rag
    measure.init(rag.store)
    if rag.store.stats()["chunks"] == 0:
        ingest_dir(docs_dir, rag.store, rag.provider)

    @app.post("/ask")
    def ask(body: Ask, x_user: str = Header(default="guest")):
        # Demo auth: the X-User header. Replace with SSO/OIDC in production.
        return rag.ask(x_user, body.question)

    @app.post("/briefing/flood")
    def briefing_flood(x_user: str = Header(default="guest")):
        # Storm briefing: live lake levels + flood rules + FONS, with citations.
        return flood_briefing(rag, x_user)

    @app.get("/metrics")
    def metrics():
        return {**rag.store.stats(), "provider": rag.provider.name, "recent": rag.store.recent(10)}

    @app.post("/feedback")
    def feedback(body: Feedback, x_user: str = Header(default="guest")):
        try:
            measure.add_feedback(rag.store, body.qid, x_user, body.rating, body.comment)
        except KeyError:
            raise HTTPException(404, "unknown answer id")
        except ValueError as e:
            raise HTTPException(422, str(e))
        return {"ok": True}

    @app.get("/api/dashboard")
    def api_dashboard():
        return measure.dashboard(rag.store)

    @app.get("/api/gaps")
    def api_gaps():
        return measure.gap_report(rag.store)

    @app.get("/dashboard")
    def dashboard_page():
        return FileResponse(ROOT / "app" / "static" / "dashboard.html")

    @app.post("/admin/reingest")
    def reingest(x_user: str = Header(default="guest")):
        require_admin(x_user)
        return {"chunks": ingest_dir(docs_dir, rag.store, rag.provider)}

    @app.post("/admin/run-evals")
    def run_evals(x_user: str = Header(default="guest")):
        # Runs the golden set against the live model and stores the scores for the dashboard.
        # With a real provider this costs a few cents, so it is admin-only and manual.
        require_admin(x_user)
        from evals.run_evals import run
        res = run(rag)
        return {k: v for k, v in res.items() if k != "rows"}

    @app.get("/healthz")
    def health():
        return {"ok": True}

    @app.get("/")
    def index():
        return FileResponse(ROOT / "app" / "static" / "index.html")

    return app

