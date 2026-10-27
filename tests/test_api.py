def test_metrics_logs_queries(client):
    client.post("/ask", json={"question": "patch evaluation days"}, headers={"X-User": "maria"})
    m = client.get("/metrics").json()
    assert m["queries"] == 1 and m["queries_by_role"] == {"field-tech": 1}
    assert m["tokens_in"] > 0 and m["est_cost_usd"] > 0
    assert m["recent"][0]["user_name"] == "maria"


def test_index_page(client):
    assert "Utility RAG Assistant" in client.get("/").text
