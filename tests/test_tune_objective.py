def test_composite_loss_prefers_strict_over_fail():
    from tune import composite_loss
    strict = [{"verdict": "STRICT-PASS", "lock_pct": 80, "rmse": 3.0, "first_lock": 100, "losses": 0, "bkey": "X1", "intermittent": False}]
    failed = [{"verdict": "FAIL", "lock_pct": 0, "rmse": 99.0, "first_lock": None, "losses": 9, "bkey": "X1", "intermittent": False}]
    assert composite_loss(strict) < composite_loss(failed)

def test_composite_loss_rejects_intermittent_on_strict_case():
    from tune import composite_loss
    strict_case = [{"verdict": "INTERMITTENT-PASS", "lock_pct": 5, "rmse": 20.0, "first_lock": 900, "losses": 9, "acq": 5, "valid_pct": 50.0, "bkey": "X1", "intermittent": False}]
    strict_win = [{"verdict": "STRICT-PASS", "lock_pct": 60, "rmse": 4.0, "first_lock": 400, "losses": 1, "bkey": "X1", "intermittent": False}]
    assert composite_loss(strict_win) < composite_loss(strict_case)

def test_case_loss_coerces_nonfinite_metrics():
    import math
    from tune import _case_loss
    from headless import BENCHMARKS
    nan_case = {"verdict": "FAIL", "lock_pct": float("nan"), "rmse": float("inf"),
                "first_lock": None, "losses": 0, "bkey": "X1", "intermittent": False}
    loss = _case_loss(nan_case, BENCHMARKS)
    assert math.isfinite(loss)
    good = {"verdict": "STRICT-PASS", "lock_pct": 80, "rmse": 3.0,
            "first_lock": 100, "losses": 0, "bkey": "X1", "intermittent": False}
    assert _case_loss(good, BENCHMARKS) < loss  # fail penalty still dominates
