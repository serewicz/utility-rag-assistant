# 8. Status and next steps

## Tested (offline)

- Ingestion, chunking, front matter, fail-closed labels
- RBAC leak tests across users and probing questions
- Query logging and `/metrics`
- Golden-set evals with CI thresholds
- Web chat page and API

## Written, not yet verified

- `PgVectorStore` and `docker compose` (the build machine had no Docker). First thing to run: `docker compose up --build` and the same tests against Postgres.
- `OpenAIProvider` and `OllamaProvider` against live endpoints.

## To do

- Integration test job in CI with a pgvector service container
- SSO instead of the `X-User` header
- Admin endpoint protection (`/admin/reingest` is open in the demo)
- Hybrid search (keyword + vector) and a re-ranker
- Streaming answers
- A small dashboard over `query_log`
