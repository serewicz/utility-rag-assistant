"""Quality gate. CI fails if retrieval or answers regress below the thresholds."""
from evals.run_evals import run


def test_golden_set(rag):
    res = run(rag)
    print(res)
    assert res["retrieval_hit_rate"] >= 0.9
    assert res["answer_accuracy"] >= 0.75
