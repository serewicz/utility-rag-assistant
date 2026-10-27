"""Side-by-side access view and governance page."""
from app import governance
from app.main import ROOT


def test_compare_highlights_restricted_sources(client):
    r = client.post("/compare", json={"question": "What firewall protects the Electronic Security Perimeter at the control center?",
                                       "users": ["guest", "tim"]}).json()
    guest, tim = r["columns"]
    assert guest["role"] == "public" and tim["role"] == "cip-analyst"
    assert all(s["label"] == "public" for s in guest["sources"])
    assert "sample-cip-restricted-esp-topology.md" in tim["only_this_user"]
    assert "sample-cip-restricted-esp-topology.md" not in guest["only_this_user"]
    assert all(s["only_this_user"] for s in tim["sources"] if s["label"] == "cip-restricted")
    assert "ESP" not in guest["answer"] or "restricted" not in guest["answer"].lower()


def test_compare_needs_two_users_and_logs_both(client):
    assert client.post("/compare", json={"question": "x", "users": ["guest"]}).status_code == 422
    client.post("/compare", json={"question": "FONS", "users": ["guest", "maria"]})
    assert client.get("/metrics").json()["queries"] == 2


def test_governance_report(client, tmp_path):
    g = client.get("/api/governance").json()
    assert g["model"]["provider"] == "fake" and not g["model"]["data_leaves_network"]
    by_doc = {s["doc"]: s for s in g["sources"]}
    t = by_doc["lcra-key-elevations-for-lake-travis-during-floods.md"]
    assert t["label"] == "public" and t["owner"] == "unassigned" and t["chunks"] > 0
    assert t["retrieved"] == "2026-10-26" and t["source_url"].startswith("https://www.lcra.org")
    assert g["totals"]["chunks"] == client.get("/metrics").json()["chunks"]
    assert g["policy_notes"] == "/policy" and "NIST" in client.get("/policy").text


def test_owner_precedence(rag, tmp_path):
    cfg = tmp_path / "g.yaml"
    cfg.write_text("owners: {lcra-drought.md: Water Resources}\nowner_prefixes: {lcra-: Public Information}\n"
                   "label_owners: {cip-restricted: CIP Senior Manager}\n")
    g = governance.report(rag, ROOT / "data" / "docs", cfg)
    by_doc = {s["doc"]: s["owner"] for s in g["sources"]}
    assert by_doc["lcra-drought.md"] == "Water Resources"
    assert by_doc["lcra-flood.md"] == "Public Information"
    assert by_doc["sample-cip-restricted-esp-topology.md"] == "CIP Senior Manager"
    assert by_doc["cip-007-system-security-management.md"] == "unassigned"


def test_openai_provider_is_flagged_as_leaving_network(rag):
    rag.provider.name = "openai"
    try:
        g = governance.report(rag, ROOT / "data" / "docs", ROOT / "data" / "governance.yaml")
    finally:
        rag.provider.name = "fake"
    assert g["model"]["data_leaves_network"] and g["model"]["chat_model"] == rag.s.openai_chat


def test_pages(client):
    assert "Side-by-side" in client.get("/compare").text
    assert "Governance" in client.get("/governance").text
