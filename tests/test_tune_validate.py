def test_validate_full_counts_fails(tmp_path):
    from tune import validate_full
    bad = tmp_path / "bad_winner.json"
    bad.write_text('{"detector": {"threshold_k": 99.0}}')
    rep = validate_full(str(bad), workers=1, timeout_s=30.0, frames_override=50)
    assert "fails" in rep and "verdict" in rep
