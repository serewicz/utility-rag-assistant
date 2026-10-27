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
