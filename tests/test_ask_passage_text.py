"""/ask returns passage text, limited to what the caller is allowed to see."""
def _ask(client, user=None, q="ESP access electronic security perimeter topology"):
    headers = {"X-User": user} if user else {}
    return client.post("/ask", json={"question": q}, headers=headers).json()


def test_sources_include_passage_text(client):
    body = _ask(client, "tim")
    assert body["sources"]
    for s in body["sources"]:
        assert isinstance(s["text"], str) and s["text"]


def test_cip_analyst_can_get_restricted_text(client):
    labels = {s["label"] for s in _ask(client, "tim")["sources"]}
    assert "cip-restricted" in labels


def _restricted_texts(rag):
    rows = rag.store.q("SELECT text FROM chunks WHERE label = ?", ("cip-restricted",))
    assert rows, "fixture corpus should contain cip-restricted chunks"
    return [r[0] for r in rows]


def _assert_no_restricted(body, restricted):
    assert body["sources"], "query should retrieve something"
    for s in body["sources"]:
        assert s["label"] != "cip-restricted"
        assert s["text"] not in restricted
    for r in restricted:
        assert r not in body["answer"]


def test_anonymous_never_gets_restricted_text(client, rag):
    _assert_no_restricted(_ask(client), _restricted_texts(rag))


def test_unknown_user_treated_as_guest(client, rag):
    body = _ask(client, "nobody-xyz")
    _assert_no_restricted(body, _restricted_texts(rag))
    assert {s["label"] for s in body["sources"]} <= {"public"}


def test_field_tech_never_gets_restricted_text(client, rag):
    body = _ask(client, "maria")
    _assert_no_restricted(body, _restricted_texts(rag))
    assert {s["label"] for s in body["sources"]} <= {"public", "field-tech"}


def test_compare_does_not_gain_passage_text(client):
    body = client.post("/compare", json={"question": "ESP access"}).json()
    assert body["columns"]
    for col in body["columns"]:
        for s in col["sources"]:
            assert "text" not in s
