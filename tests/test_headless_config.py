"""Tests for headless.py --config winner injection (Task 1)."""


def test_config_flag_rejects_nonsystem_keys(tmp_path):
    from headless import set_winner_overrides
    p = tmp_path / "w.json"
    p.write_text('{"detector": {"threshold_k": 3.5}, "target": {"speed_px_per_frame": 99}, "camera": {"fov_deg": [12, 12]}}')
    got = set_winner_overrides(str(p))
    assert got["detector"]["threshold_k"] == 3.5
    assert "target" not in got
    assert "fov_deg" not in got.get("camera", {})


def test_set_winner_overrides_none_resets(tmp_path):
    import headless
    from headless import set_winner_overrides
    p = tmp_path / "w.json"
    p.write_text('{"detector": {"threshold_k": 3.5}}')
    set_winner_overrides(str(p))
    assert headless.WINNER_OVERRIDES["detector"]["threshold_k"] == 3.5
    got = set_winner_overrides(None)
    assert got == {}
    assert headless.WINNER_OVERRIDES == {}


def test_camera_keeps_only_update_interval_hz(tmp_path):
    from headless import set_winner_overrides
    p = tmp_path / "w.json"
    p.write_text('{"camera": {"update_interval_hz": 30.0, "fov_deg": [12, 12], "jitter_px": 99}}')
    got = set_winner_overrides(str(p))
    assert got["camera"] == {"update_interval_hz": 30.0}


def test_camera_rejects_update_interval_below_floor(tmp_path):
    from headless import set_winner_overrides
    p = tmp_path / "w.json"
    p.write_text('{"camera": {"update_interval_hz": 5.0}}')
    got = set_winner_overrides(str(p))
    assert "update_interval_hz" not in got.get("camera", {})


def test_camera_rejects_fixed_hardware(tmp_path):
    from headless import set_winner_overrides
    p = tmp_path / "w.json"
    p.write_text('{"camera": {"update_interval_hz": 30.0, "initial_pan": 1.0,'
                 ' "fps": 99, "max_pan_speed": 99, "max_tilt_speed": 99,'
                 ' "fov_deg": [12, 12], "resolution": [99, 99]}}')
    got = set_winner_overrides(str(p))
    assert got["camera"] == {"update_interval_hz": 30.0, "initial_pan": 1.0}


def test_build_case_config_applies_winner(tmp_path):
    import headless
    from headless import X_DEFS, build_case_config, set_winner_overrides
    set_winner_overrides(None)
    try:
        xd = next(d for d in X_DEFS if d["key"] == "X1")
        baseline = build_case_config(xd, 42)
        base_speed = baseline["target"]["speed_px_per_frame"]
        p = tmp_path / "w.json"
        p.write_text('{"detector": {"threshold_k": 3.5}, "target": {"speed_px_per_frame": 99}}')
        set_winner_overrides(str(p))
        cfg = build_case_config(xd, 42)
        assert cfg["detector"]["threshold_k"] == 3.5
        # dropped test-condition key must not leak into the case config
        assert cfg["target"]["speed_px_per_frame"] == base_speed != 99
    finally:
        headless.set_winner_overrides(None)


def test_build_edge_config_applies_winner(tmp_path):
    import headless
    from headless import E_DEFS, build_edge_config, set_winner_overrides
    set_winner_overrides(None)
    try:
        p = tmp_path / "w.json"
        p.write_text('{"tracker": {"gate_sigma": 2.0}}')
        set_winner_overrides(str(p))
        cfg = build_edge_config(E_DEFS[0], 42)
        assert cfg["tracker"]["gate_sigma"] == 2.0
    finally:
        headless.set_winner_overrides(None)


def test_camera_start_applies_after_far_start(tmp_path):
    import headless
    from headless import set_winner_overrides, build_case_config, X_DEFS
    p = tmp_path / "w.json"
    p.write_text('{"camera": {"initial_position": "user-defined", "initial_pan": 2.0, "initial_tilt": -1.5}}')
    set_winner_overrides(str(p))
    try:
        xd = next(d for d in X_DEFS if d["key"] == "X1")
        cfg = build_case_config(xd, 42)
        assert cfg["camera"].get("initial_pan") == 2.0
        assert cfg["camera"].get("initial_tilt") == -1.5
        assert cfg["target"]["initial_mode"] == "user-defined"  # far corner intact
    finally:
        set_winner_overrides(None)


def test_apply_spec_winner_propagates_to_workers():
    import headless
    from headless import _apply_spec_winner, set_winner_overrides
    set_winner_overrides(None)
    try:
        _apply_spec_winner({"kind": "X", "winner": {"detector": {"threshold_k": 3.5}}})
        assert headless.WINNER_OVERRIDES["detector"]["threshold_k"] == 3.5
    finally:
        headless.set_winner_overrides(None)


def test_apply_spec_winner_resets_without_winner():
    import headless
    from headless import _apply_spec_winner
    headless.WINNER_OVERRIDES = {"detector": {"threshold_k": 3.5}}
    try:
        _apply_spec_winner({"kind": "X"})
        assert headless.WINNER_OVERRIDES == {}
        headless.WINNER_OVERRIDES = {"detector": {"threshold_k": 3.5}}
        _apply_spec_winner({"kind": "X", "winner": {}})
        assert headless.WINNER_OVERRIDES == {}
    finally:
        headless.set_winner_overrides(None)


def test_set_winner_overrides_returns_copy(tmp_path):
    import headless
    from headless import set_winner_overrides
    p = tmp_path / "w.json"
    p.write_text('{"detector": {"threshold_k": 3.5}}')
    try:
        got = set_winner_overrides(str(p))
        got["detector"]["threshold_k"] = 99.0
        got["injected"] = True
        assert headless.WINNER_OVERRIDES["detector"]["threshold_k"] == 3.5
        assert "injected" not in headless.WINNER_OVERRIDES
    finally:
        headless.set_winner_overrides(None)


def test_main_missing_config_exits_friendly(tmp_path, monkeypatch, capsys):
    import sys
    import headless
    missing = str(tmp_path / "nope.json")
    monkeypatch.setattr(sys, "argv", ["headless.py", "--config", missing])
    rc = headless.main()
    assert rc == 2
    out = capsys.readouterr().out
    assert missing in out


def test_main_bad_json_config_exits_friendly(tmp_path, monkeypatch, capsys):
    import sys
    import headless
    p = tmp_path / "bad.json"
    p.write_text("{not json")
    monkeypatch.setattr(sys, "argv", ["headless.py", "--config", str(p)])
    rc = headless.main()
    assert rc == 2
    out = capsys.readouterr().out
    assert str(p) in out


def test_verdict_zero_losses_passes_losses_gate():
    import headless
    summary = {
        "lock_retention_pct": 58.1,
        "rmse_px": 0.69,
        "first_lock_frame": 377,
        "loss_count": 0,
        "acquisition_count": 1,
        "valid_detection_pct": 58.6,
    }
    v, reason = headless.verdict(summary, False, "X1")
    assert v == "STRICT-PASS", reason
    assert reason.startswith("beat bench")


def test_verdict_missing_loss_count_stays_pessimistic():
    import headless
    summary = {
        "lock_retention_pct": 58.1,
        "rmse_px": 0.69,
        "first_lock_frame": 377,
        "acquisition_count": 1,
        "valid_detection_pct": 58.6,
    }
    v, reason = headless.verdict(summary, False, "X1")
    assert v == "FAIL" and "losses 99>2" in reason
