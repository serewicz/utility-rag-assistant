# 5. Cost and logging

Directors get asked two questions: "Is anyone using it?" and "What does it cost?" Log from day one.

## What we log (`query_log` table)

user, role, question, latency in ms, tokens in, tokens out, estimated cost in USD, provider, and the documents cited.

## How cost is estimated

`cost = tokens_in / 1M * PRICE_INPUT_PER_M + tokens_out / 1M * PRICE_OUTPUT_PER_M`

Real providers return token counts. The fake provider estimates 4 characters per token. Prices live in `.env` because they change.

Typical numbers: a query with 4 chunks is about 800 input tokens. At $0.15 per million input tokens that is about $0.0001. A thousand staff asking 10 questions a day is about $1 a day in model cost. The real cost is people and integration, which is the point to make to leadership.

## See it

`GET /metrics` returns totals, average latency, queries by role, and the last 10 queries.

## Exercise

Add a `GET /metrics/daily` endpoint that groups cost by day. Then argue, in one paragraph, whether logging the question text is acceptable under your privacy policy.
