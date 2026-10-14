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
        p = tmp_path / "w.json"
        p.write_text('{"detector": {"threshold_k": 3.5}, "target": {"speed_px_per_frame": 99}}')
        set_winner_overrides(str(p))
        xd = next(d for d in X_DEFS if d["key"] == "X1")
        cfg = build_case_config(xd, 42)
        assert cfg["detector"]["threshold_k"] == 3.5
        # dropped test-condition key must not leak into the case config
        assert cfg["target"]["speed_px_per_frame"] == 3.0
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
