def test_validate_full_counts_fails(tmp_path):
    from tune import validate_full
    bad = tmp_path / "bad_winner.json"
    bad.write_text('{"detector": {"threshold_k": 99.0}}')
    rep = validate_full(str(bad), workers=1, timeout_s=30.0, frames_override=50)
    assert "fails" in rep and "verdict" in rep

def test_validate_full_shares_stamp(tmp_path, monkeypatch):
    import headless
    from tune import validate_full, write_best_artifact
    monkeypatch.setattr(headless, "build_suite", lambda **kw: [])
    winner = tmp_path / "w.json"
    winner.write_text('{"detector": {"threshold_k": 3.0}}')
    monkeypatch.chdir(tmp_path)
    rep = validate_full(str(winner), workers=1, stamp="SHAREDSTAMP")
    best = write_best_artifact({"detector": {"threshold_k": 3.0}}, 1.0, 0, 0, 1,
                               stamp="SHAREDSTAMP")
    assert rep["report_paths"][0].endswith("tune_SHAREDSTAMP_validation.json")
    assert best.endswith("tune_SHAREDSTAMP_best.json")
