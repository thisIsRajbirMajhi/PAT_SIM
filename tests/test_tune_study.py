def test_evaluate_subset_returns_scored_results():
    from tune import evaluate_subset
    out = evaluate_subset({"detector": {"threshold_k": 3.0}}, [("X1", 42)], timeout_s=60.0)
    assert len(out) == 1 and out[0]["verdict"] in ("STRICT-PASS", "INTERMITTENT-PASS", "FAIL", "ERROR")
