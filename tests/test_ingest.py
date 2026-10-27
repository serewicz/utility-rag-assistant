from app.ingest import chunk, parse_front_matter


def test_front_matter():
    meta, body = parse_front_matter("---\ntitle: T\nlabel: public\n---\nhello")
    assert meta == {"title": "T", "label": "public"} and body == "hello"


def test_unlabeled_defaults_to_restricted(tmp_path, rag):
    from app.ingest import ingest_dir
    (tmp_path / "x.txt").write_text("secret substation password notes")
    ingest_dir(tmp_path, rag.store, rag.provider)
    assert rag.store.search(rag.provider.embed(["x"])[0], {"cip-restricted"}, 5)[0]["label"] == "cip-restricted"


def test_chunk_sizes():
    text = "\n\n".join("para %d " % i + "word " * 50 for i in range(20))
    cs = chunk(text, size=800, overlap=100)
    assert len(cs) > 3 and all(len(c) < 1400 for c in cs)


def test_labels_yaml_short_form(tmp_path):
    from app.ingest import ingest_dir
    from app.providers import FakeProvider
    from app.store import SQLiteStore
    (tmp_path / "a.txt").write_text("Lake Travis is full at 681 feet msl.")
    (tmp_path / "labels.yaml").write_text("a.txt: public\n")
    st = SQLiteStore(":memory:")
    ingest_dir(tmp_path, st, FakeProvider())
    assert st.search(FakeProvider().embed(["Lake Travis"])[0], {"public"}, 1)[0]["label"] == "public"
