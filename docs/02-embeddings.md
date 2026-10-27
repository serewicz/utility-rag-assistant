# 2. Embeddings

An **embedding** turns text into a list of numbers so that texts with similar meaning land close together. Search becomes "find the vectors nearest the question's vector" (cosine similarity).

## Why the fake provider uses hashed words

`FakeProvider.embed` in `app/providers.py` hashes each word into one of 256 slots. It only matches shared words, not meaning. We use it because:

- Tests must be deterministic and run with no key, no network, and no GPU.
- Access control and logging don't depend on embedding quality, so we can test them with a cheap stand-in.

Real models (`text-embedding-3-small`, `nomic-embed-text`) match meaning, so "remove access when someone leaves" finds "terminated". Swap with `LLM_PROVIDER`.

## Design decision: one interface

Every provider has `embed(texts)` and `chat(system, user)`. Nothing else in the code knows which one is running. That is what makes on-prem a configuration change instead of a rewrite.

## Exercise

Ask "What happens when an employee quits?" with the fake provider. It will likely miss CIP-004. Explain why, then add a synonym line to the CIP-004 doc and re-run. Note that you just did manual work that a real embedding model does for you.
