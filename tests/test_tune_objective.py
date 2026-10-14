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
