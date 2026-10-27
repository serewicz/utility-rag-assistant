# 7. Running on-prem

Utilities often can't send operational data to a public cloud. This repo supports three modes with one variable:

| `LLM_PROVIDER` | Data leaves the network? | Use for |
|---|---|---|
| `fake` | no | tests, CI, demos |
| `openai` | yes, unless `OPENAI_BASE_URL` points to an internal server | fastest start |
| `ollama` | no | on-prem production pilots |

## Steps

```bash
docker compose --profile onprem up -d ollama
docker compose exec ollama ollama pull llama3.1:8b
docker compose exec ollama ollama pull nomic-embed-text
LLM_PROVIDER=ollama docker compose up --build app
```

Changing the embedding model changes vector dimensions, so re-ingest (`POST /admin/reingest`) and recreate the `chunks` table after switching.

## Why the model is pluggable

Maintaining local models is real work: drivers, updates, GPU memory. Pluggability lets you start hosted, prove value, then move on-prem without changing application code. Run the eval suite against both and compare before you switch.
