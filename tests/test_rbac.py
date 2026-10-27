"""Access control tests. These are the tests a CIP auditor cares about."""
import pytest

SECRET_TERMS = ["ZEPHYR", "BLUEHERON", "break-glass"]
PROBES = ["What is the electronic access point firewall name?", "Which jump host is used for remote access?",
          "control center ESP break-glass account", "ZEPHYR BLUEHERON"]


@pytest.mark.parametrize("user", ["guest", "maria", "nobody-unknown"])
@pytest.mark.parametrize("q", PROBES)
def test_restricted_never_leaks(client, user, q):
    j = client.post("/ask", json={"question": q}, headers={"X-User": user}).json()
    assert all(s["label"] != "cip-restricted" for s in j["sources"])
    for t in SECRET_TERMS:
        assert t.lower() not in j["answer"].lower()


def test_guest_cannot_see_field_procedures(client):
    j = client.post("/ask", json={"question": "feeder trip switching order"}, headers={"X-User": "guest"}).json()
    assert all(s["label"] == "public" for s in j["sources"])


def test_analyst_can_see_restricted(client):
    j = client.post("/ask", json={"question": "electronic access point firewall name"}, headers={"X-User": "dev"}).json()
    assert "ZEPHYR" in j["answer"]
