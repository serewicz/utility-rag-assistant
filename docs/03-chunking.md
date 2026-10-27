# 3. Chunking and ingestion

Models have limited context and retrieval works on pieces, so we split documents into **chunks**.

## Choices in `app/ingest.py`

- **Split on paragraphs, pack to ~800 characters.** Paragraphs keep sentences whole. 800 characters is about 200 tokens: small enough to be specific, big enough to carry context.
- **150-character overlap.** If an answer straddles a cut, the next chunk still has the lead-in.
- **Front matter on every file** (`title`, `label`, `source_url`). Metadata travels with each chunk, which is how citations and access control work.
- **Unlabeled means restricted.** If someone drops a file in without a label, it is treated as `cip-restricted`. Fail closed.
- **PDFs** go through `pypdf`. Scanned PDFs need OCR, which is not included.

## Exercise

1. Download an official CIP standard PDF from the NERC site into `data/docs/`.
2. Add it to `data/docs/labels.yaml` with `label: public`.
3. `python -m app.ingest` and ask a question about it.
4. Change chunk size to 300 and 2000. Re-run `python -m evals.run_evals`. Write down what changed.
