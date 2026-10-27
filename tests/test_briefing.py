"""Storm briefing tests. Hydromet is always mocked: CI never calls the network."""
from app import briefing

SAMPLE = [
    {"location": "Mansfield Dam", "dateTime": "2026-10-27T01:15:00Z", "elevation": 677.2},
    {"location": "Buchanan Dam", "dateTime": "2026-10-27T01:15:00Z", "elevation": 1018.33},
]


def _live(rag, fetch=lambda: SAMPLE):
    rag.s.hydromet_live = True
    rag.hydromet_fetch = fetch
    return rag


def test_briefing_compares_live_levels_to_cited_key_elevations(rag):
    b = briefing.flood_briefing(_live(rag), "guest")
    assert b["live_ok"]
    travis = next(r for r in b["readings"] if r["lake"] == "travis")
    assert travis["time_central"] == "Oct 26, 2026 8:15 PM CDT"
    assert {k["elevation_ft"]: k["feet_from"] for k in travis["vs_key_elevations"]} == {681.0: -3.8, 714.0: -36.8}
    buch = next(r for r in b["readings"] if r["lake"] == "buchanan")
    assert buch["vs_key_elevations"][0]["feet_from"] == -1.67
    assert "3.8 ft below 681 ft" in b["answer"] and "8:15 PM CDT" in b["answer"]


def test_briefing_covers_operations_and_fons_with_citations(rag):
    b = briefing.flood_briefing(_live(rag), "guest")
    assert any("can begin floodgate releases" in r["text"] for r in b["rules"])
    assert any("1,020 feet" in r["text"] for r in b["rules"])
    assert any("FONS" in n["text"] for n in b["notify"])
    assert briefing.FONS_SIGNUP in b["answer"] and "not a flood warning service" in b["answer"]
    nums = {s["n"] for s in b["sources"]}
    assert all(x["cite"] in nums for x in b["rules"] + b["notify"])


def test_briefing_is_deterministic_offline(rag):
    _live(rag)
    a = briefing.flood_briefing(rag, "guest")["answer"]
    assert a == briefing.flood_briefing(rag, "guest")["answer"]


def test_live_failure_is_stated_and_documents_still_used(rag):
    def boom():
        raise TimeoutError
    b = briefing.flood_briefing(_live(rag, boom), "guest")
    assert not b["live_ok"] and "unavailable" in b["live_error"]
    assert "unavailable" in b["answer"] and b["readings"] == []
    assert b["rules"] and all(s["doc"] != "hydromet-live" for s in b["sources"])


def test_briefing_respects_rbac(rag):
    b = briefing.flood_briefing(_live(rag), "guest")
    assert all(s["label"] == "public" for s in b["sources"])
    assert briefing.flood_briefing(_live(rag), "nobody")["role"] == "public"


def test_briefing_endpoint_and_metrics(client):
    rag = client.app.state.rag
    _live(rag)
    r = client.post("/briefing/flood", headers={"X-User": "tim"}).json()
    assert r["kind"] == "flood" and r["role"] == "cip-analyst"
    recent = client.get("/metrics").json()["recent"]
    assert recent[0]["question"].startswith("[briefing/flood]")


def test_llm_provider_gets_facts_and_adds_disclaimer(rag):
    from app.providers import ChatResult

    class Stub:
        name = "openai"
        seen = {}

        def embed(self, texts):
            return fake.embed(texts)

        def chat(self, system, user):
            Stub.seen["user"] = user
            return ChatResult("Lake Travis is 3.8 ft below 681 ft [1].", 500, 20)

    fake = rag.provider
    rag.provider = Stub()
    b = briefing.flood_briefing(_live(rag), "guest")
    assert "677.2" in Stub.seen["user"] and "681" in Stub.seen["user"]
    assert b["answer"].startswith("Lake Travis") and briefing.DISCLAIMER in b["answer"]
    assert b["tokens_in"] == 500 and b["readings"]
