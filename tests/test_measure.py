"""Dashboard, gap report, feedback and eval history. All offline."""
from app import measure
from evals.run_evals import run


def test_ask_returns_qid_and_records_outcome(client):
    r = client.post("/ask", json={"question": "At what Lake Travis elevation can LCRA begin floodgate releases?"},
                    headers={"X-User": "guest"}).json()
    assert len(r["qid"]) == 32
    d = client.get("/api/dashboard").json()
    assert d["totals"]["asked"] == 1 and d["totals"]["unanswered"] == 0
    assert d["per_day"][0]["questions"] == 1 and d["per_day"][0]["cost_usd"] > 0


def test_unanswered_questions_land_in_gap_report_by_topic(client):
    for q in ["Who won the football game?", "When is the next drought curtailment stage expected?"]:
        client.post("/ask", json={"question": q}, headers={"X-User": "guest"})
    rag = client.app.state.rag
    # Force the drought question to look low-confidence regardless of the retrieval score.
    rag.store.q("UPDATE outcomes SET answered = 0")
    gaps = client.get("/api/gaps").json()
    topics = {g["topic"]: g for g in gaps}
    assert "Drought and curtailment" in topics and "Other" in topics
    assert any("Drought Contingency Plan" in s for s in topics["Drought and curtailment"]["suggested_docs"])
    assert client.get("/api/dashboard").json()["totals"]["unanswered_rate"] == 1.0


def test_is_unanswered_rules():
    assert measure.is_unanswered("I don't know based on the documents.", 0.9)
    assert measure.is_unanswered("Some answer", 0.01)
    assert measure.is_unanswered("Some answer", None)
    assert not measure.is_unanswered("Releases begin at 681 feet [1].", 0.5)


def test_feedback_round_trip_and_thumbs_down_is_a_gap(client):
    qid = client.post("/ask", json={"question": "Is FONS a flood warning service?"}).json()["qid"]
    assert client.post("/feedback", json={"qid": qid, "rating": -1, "comment": "too short"}).json()["ok"]
    assert client.post("/feedback", json={"qid": qid, "rating": 1}).status_code == 200
    d = client.get("/api/dashboard").json()
    assert d["totals"]["thumbs_up"] == 1 and d["totals"]["thumbs_down"] == 1
    assert d["feedback_comments"][0]["comment"] == "too short"
    assert any(q["question"].startswith("Is FONS") for g in d["gaps"] for q in g["questions"])


def test_feedback_validation(client):
    assert client.post("/feedback", json={"qid": "nope", "rating": 1}).status_code == 404
    qid = client.post("/ask", json={"question": "FONS"}).json()["qid"]
    assert client.post("/feedback", json={"qid": qid, "rating": 5}).status_code == 422


def test_evals_are_stored_and_not_counted_as_usage(rag):
    run(rag)
    d = measure.dashboard(rag.store)
    assert d["latest_eval"]["n"] >= 20 and d["latest_eval"]["answer_accuracy"] >= 0.75
    assert d["totals"]["queries"] == 0


def test_run_evals_endpoint_is_admin_only(client):
    assert client.post("/admin/run-evals", headers={"X-User": "guest"}).status_code == 403
    r = client.post("/admin/run-evals", headers={"X-User": "tim"}).json()
    assert r["retrieval_hit_rate"] >= 0.9
    assert client.get("/api/dashboard").json()["latest_eval"]["provider"] == "fake"


def test_reingest_is_admin_only(client):
    assert client.post("/admin/reingest", headers={"X-User": "maria"}).status_code == 403
    assert client.post("/admin/reingest", headers={"X-User": "dev"}).json()["chunks"] > 0


def test_dashboard_page(client):
    assert "Gap report" in client.get("/dashboard").text
