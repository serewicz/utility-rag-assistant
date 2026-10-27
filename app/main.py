"""FastAPI app. Run: uvicorn app.main:app --reload"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel

from .config import Settings
from . import measure, rbac
from . import governance
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


class Compare(BaseModel):
    question: str
    users: list[str] = ["guest", "tim"]


class Feedback(BaseModel):
    qid: str
    rating: int  # 1 = thumbs up, -1 = thumbs down
    comment: str = ""


def require_admin(user: str):
    if not rbac.is_admin(user):
        raise HTTPException(403, "admin role required")


def compare(rag: RAG, question: str, users: list[str]) -> dict:
    """Ask the same question as two users. Highlight sources only one of them could see."""
    if len(users) != 2:
        raise HTTPException(422, "pick exactly two users")
    cols = [dict(user=u, **rag.ask(u, question)) for u in users]
    docs = [{s["doc"] for s in c["sources"]} for c in cols]
    for i, c in enumerate(cols):
        other = docs[1 - i]
        for s in c["sources"]:
            s["only_this_user"] = s["doc"] not in other
        c["only_this_user"] = sorted(docs[i] - other)
    return dict(question=question, columns=cols, shared=sorted(docs[0] & docs[1]))


def create_app(rag: RAG | None = None, docs_dir: Path = ROOT / "data" / "docs",
               gov_path: Path = ROOT / "data" / "governance.yaml") -> FastAPI:
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

    @app.post("/compare")
    def compare_ep(body: Compare):
        # Each column runs with that user's own role. Nothing is shared between the two calls.
        return compare(rag, body.question, body.users)

    @app.get("/compare")
    def compare_page():
        return FileResponse(ROOT / "app" / "static" / "compare.html")

    @app.get("/api/governance")
    def api_governance():
        return governance.report(rag, docs_dir, gov_path)

    @app.get("/governance")
    def governance_page():
        return FileResponse(ROOT / "app" / "static" / "governance.html")

    @app.get("/policy", response_class=PlainTextResponse)
    def policy():
        return (ROOT / "docs" / "policy-notes.md").read_text()

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

