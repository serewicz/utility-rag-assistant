"""Drought briefing. Hydromet is always mocked."""
from app import drought

SAMPLE = [{"location": "Mansfield Dam", "dateTime": "2026-10-27T01:15:00Z", "elevation": 677.2},
          {"location": "Buchanan Dam", "dateTime": "2026-10-27T01:15:00Z", "elevation": 1018.33}]


def _live(rag, fetch=lambda: SAMPLE):
    rag.s.hydromet_live, rag.hydromet_fetch = True, fetch
    return rag


def test_levels_vs_full_in_central_time(rag):
    b = drought.drought_briefing(_live(rag), "guest")
    t = next(r for r in b["readings"] if r["lake"] == "travis")
    assert t["time_central"] == "Oct 26, 2026 8:15 PM CDT" and t["vs_full"]["feet_from"] == -3.8
    assert "3.8 ft below 681 ft" in b["answer"]


def test_curtailment_and_storage_facts_are_cited(rag):
    b = drought.drought_briefing(_live(rag), "guest")
    assert any("initial minimum curtailment of 20%" in f["text"] for f in b["facts"]["curtailment"])
    assert any("combined storage" in f["text"].lower() for f in b["facts"]["storage"])
    nums = {s["n"] for s in b["sources"]}
    assert all(f["cite"] in nums for fs in b["facts"].values() for f in fs)
    assert all(f["text"][0].isupper() for fs in b["facts"].values() for f in fs)  # no overlap fragments


def test_live_failure_falls_back_to_documents(rag):
    def boom():
        raise TimeoutError
    b = drought.drought_briefing(_live(rag, boom), "guest")
    assert not b["live_ok"] and b["readings"] == [] and "unavailable" in b["answer"]
    assert b["facts"]["curtailment"]


def test_rbac_and_endpoint_logging(client):
    _live(client.app.state.rag)
    b = client.post("/briefing/drought", headers={"X-User": "nobody"}).json()
    assert b["kind"] == "drought" and b["role"] == "public"
    assert all(s["label"] == "public" for s in b["sources"])
    assert client.get("/metrics").json()["recent"][0]["question"].startswith("[briefing/drought]")


def test_llm_path_adds_disclaimer(rag):
    from app.providers import ChatResult
    fake = rag.provider

    class Stub:
        name = "openai"

        def embed(self, t):
            return fake.embed(t)

        def chat(self, system, user):
            assert "20%" in user
            return ChatResult("Summary [1].", 400, 10)
    rag.provider = Stub()
    b = drought.drought_briefing(_live(rag), "guest")
    assert b["answer"].endswith(drought.DISCLAIMER) and b["tokens_in"] == 400
