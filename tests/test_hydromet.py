"""Live-data tool tests. The Hydromet endpoint is always mocked: CI never calls the network."""
from app import hydromet

SAMPLE = [
    {"siteNumber": 2958, "location": "Mansfield Dam", "dateTime": "2026-10-27T01:15:00Z", "elevation": 675.5},
    {"siteNumber": 1995, "location": "Buchanan Dam", "dateTime": "2026-10-27T01:15:00Z", "elevation": 1018.33},
]


def test_only_live_questions_trigger_the_tool():
    assert hydromet.wants_live("What is the current level of Lake Travis?") == ["travis"]
    assert hydromet.wants_live("At what level does Lake Travis spill?") == []


def test_live_context_reports_level_and_distance_from_full():
    ctx = hydromet.live_context("What is Lake Travis at right now?", fetcher=lambda: SAMPLE)
    assert "675.5" in ctx["text"] and "-5.5" in ctx["text"]
    assert ctx["label"] == "public" and ctx["source_url"] == hydromet.REPORT_URL


def test_fetch_failure_falls_back_to_documents():
    def boom():
        raise TimeoutError
    assert hydromet.live_context("current Lake Buchanan level", fetcher=boom) is None


def test_rag_mixes_live_data_and_documents(rag):
    rag.s.hydromet_live = True
    rag.hydromet_fetch = lambda: SAMPLE
    r = rag.ask("guest", "What is the current level of Lake Buchanan?")
    assert r["sources"][0]["doc"] == "hydromet-live"
    assert "1018.33" in r["answer"]
    assert len(r["sources"]) > 1  # documents still retrieved alongside the live reading


def test_live_tool_is_off_by_default(rag):
    rag.hydromet_fetch = lambda: SAMPLE
    r = rag.ask("guest", "What is the current level of Lake Buchanan?")
    assert all(s["doc"] != "hydromet-live" for s in r["sources"])
