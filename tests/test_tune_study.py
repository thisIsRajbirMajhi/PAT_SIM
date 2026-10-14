def test_evaluate_subset_returns_scored_results():
    from tune import evaluate_subset
    out = evaluate_subset({"detector": {"threshold_k": 3.0}}, [("X1", 42)], timeout_s=60.0)
    assert len(out) == 1 and out[0]["verdict"] in ("STRICT-PASS", "INTERMITTENT-PASS", "FAIL", "ERROR")

def test_evaluate_subset_rejects_nonsystem_keys():
    import pytest
    from tune import evaluate_subset
    with pytest.raises(ValueError) as ei:
        evaluate_subset({"target": {"speed_px_per_frame": 99}}, [("X1", 42)])
    assert "target" in str(ei.value)
    with pytest.raises(ValueError) as ei:
        evaluate_subset({"camera": {"fps": 99}}, [("X1", 42)])
    assert "camera.fps" in str(ei.value)

def test_workers_rejects_nonintegral():
    import pytest
    from tune import _coerce_workers, run_study, validate_full
    with pytest.raises(ValueError):
        run_study(trials=1, workers=1.9, storage=None)
    with pytest.raises(ValueError):
        validate_full("whatever.json", workers="2.5", frames_override=50)
    # integral values still accepted
    assert _coerce_workers("4") == 4
    assert _coerce_workers(4.0) == 4
    with pytest.raises(ValueError):
        _coerce_workers(0)
