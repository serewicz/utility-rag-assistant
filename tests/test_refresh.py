"""Nightly refresh. The network is always mocked; files are copied to a temp dir."""
import shutil
from datetime import datetime

from fastapi.testclient import TestClient

from app import refresh
from app.main import ROOT, create_app

URL = "https://www.lcra.org/water/drought/"
PAGE = "<html><nav>menu</nav><main><h1>Drought</h1><p>" + "LCRA is in Stage 3 of its drought response. " * 10 + "</p></main></html>"


def setup(rag, tmp_path, robots="User-agent: *\nDisallow: /wp-admin/\n"):
    docs = tmp_path / "docs"
    shutil.copytree(ROOT / "data" / "docs", docs)
    man = tmp_path / "sources.yaml"
    man.write_text(f"sources:\n- file: lcra/lcra-drought.md\n  url: {URL}\n")
    pages = {"https://www.lcra.org/robots.txt": (200, robots), URL: (200, PAGE)}
    calls = []

    def fetch(u):
        calls.append(u)
        return pages[u]
    return docs, man, pages, fetch, calls


def test_extract_text_skips_nav():
    t = refresh.extract_text(PAGE)
    assert t.startswith("# Drought") and "menu" not in t


def test_baseline_then_unchanged_then_changed(rag, tmp_path):
    docs, man, pages, fetch, _ = setup(rag, tmp_path)
    before = (docs / "lcra/lcra-drought.md").read_text()
    assert refresh.run_refresh(rag, docs, man, fetch)["baseline"] == 1
    assert (docs / "lcra/lcra-drought.md").read_text() == before  # baseline never rewrites
    assert refresh.run_refresh(rag, docs, man, fetch)["unchanged"] == 1
    pages[URL] = (200, PAGE.replace("Stage 3", "Stage 4"))
    assert refresh.run_refresh(rag, docs, man, fetch)["changed"] == 1
    new = (docs / "lcra/lcra-drought.md").read_text()
    assert "Stage 4" in new and "label: public" in new and f"source_url: {URL}" in new
    events = [e["event"] for e in refresh.changelog(rag.store)]
    assert "changed" in events and "reingested" in events and "baseline" in events
    hits = rag.store.search(rag.provider.embed(["Stage 4 drought response"])[0], {"public"}, 3)
    assert any("Stage 4" in h["text"] for h in hits)


def test_robots_disallow_is_respected(rag, tmp_path):
    docs, man, _, fetch, calls = setup(rag, tmp_path, robots="User-agent: *\nDisallow: /water/\n")
    r = refresh.run_refresh(rag, docs, man, fetch)
    assert r["skipped"] == 1 and URL not in calls


def test_fetch_errors_are_logged_not_raised(rag, tmp_path):
    docs, man, pages, fetch, _ = setup(rag, tmp_path)
    pages[URL] = (503, "")
    assert refresh.run_refresh(rag, docs, man, fetch)["errors"] == 1
    assert refresh.changelog(rag.store)[1]["event"] == "error"


def test_admin_endpoint_and_governance_changelog(rag, tmp_path):
    docs, man, _, fetch, _ = setup(rag, tmp_path)
    c = TestClient(create_app(rag, docs_dir=docs, manifest=man))
    c.app.state.refresh_fetch = fetch
    assert c.post("/admin/refresh", headers={"X-User": "guest"}).status_code == 403
    assert c.post("/admin/refresh", headers={"X-User": "tim"}).json()["baseline"] == 1
    assert any(e["event"] == "baseline" for e in c.get("/api/refresh/log").json())
    g = c.get("/api/governance").json()
    d = next(s for s in g["sources"] if s["doc"] == "lcra-drought.md")
    assert d["last_checked"] and d["last_changed"] is None and g["refresh"]["enabled"] is False


def test_scheduler_off_by_default(client):
    assert not hasattr(client.app.state, "scheduler")


def test_seconds_until_next_run():
    now = datetime(2026, 10, 26, 21, 30, tzinfo=refresh.CENTRAL)
    assert refresh.seconds_until(2, now) == 4.5 * 3600
    assert refresh.seconds_until(22, now) == 1800


def test_manifest_covers_every_lcra_doc():
    files = {s["file"] for s in refresh.load_manifest(ROOT / "data" / "sources.yaml")}
    assert files == {f"lcra/{p.name}" for p in (ROOT / "data" / "docs" / "lcra").glob("*.md")}
