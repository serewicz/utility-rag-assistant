import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.ingest import ingest_dir
from app.main import ROOT, build, create_app


@pytest.fixture
def rag():
    r = build(Settings(provider="fake"), sqlite_path=":memory:")
    ingest_dir(ROOT / "data" / "docs", r.store, r.provider)
    return r


@pytest.fixture
def client(rag):
    return TestClient(create_app(rag))
