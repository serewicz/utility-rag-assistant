# 6. Evals

Without evals, every prompt or model change is a guess. An eval is a test for quality.

## The golden set

`evals/golden.yaml` lists questions, who asks them, which document must be retrieved, and words the answer must contain. Two metrics:

- **Retrieval hit-rate**: did the expected document appear in the top-k? If this fails, the model never had a chance.
- **Answer accuracy**: does the answer contain the key facts?

Measure retrieval separately from generation. When quality drops, you need to know which half broke.

## In CI

`tests/test_evals.py` fails the build if hit-rate drops below 90% or accuracy below 75%. `.github/workflows/ci.yml` runs it on every push with the offline provider, so CI needs no secrets.

## Going further

- Run the same set against the real provider on a schedule and track the trend.
- Add LLM-as-judge or Ragas metrics for faithfulness. Keep the simple string checks as a floor.
- Add every bad answer a user reports to the golden set. That is how the set grows.

## Exercise

Add three questions, including one the documents can't answer, and assert the answer says "don't know".
