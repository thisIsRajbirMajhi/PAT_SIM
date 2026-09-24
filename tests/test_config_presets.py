"""Tests for config loader, defaults, schema and preset discovery (Control Deck)."""

import os
import glob
import copy
import yaml
import pytest

from fsoc_tracker.config.loader import load_config, deep_merge, save_config
from fsoc_tracker.config.defaults import DEFAULT_CONFIG
from fsoc_tracker.config.schema import validate_config

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONFIGS_DIR = os.path.join(ROOT, "configs")

def test_defaults_validate():
    cfg = load_config()
    # Should not raise
    assert cfg["world"]["width"] == 2000
    assert cfg["camera"]["resolution"] == [640, 480]

def test_deep_merge():
    a = {"x": {"a": 1, "b": 2}, "y": 5}
    b = {"x": {"b": 3, "c": 4}, "z": 9}
    out = deep_merge(a, b)
    assert out["x"] == {"a": 1, "b": 3, "c": 4}
    assert out["y"] == 5
    assert out["z"] == 9
    # original not mutated
    assert a["x"]["b"] == 2

def test_overrides():
    cfg = load_config(overrides={"target": {"speed_px_per_frame": 9.9}})
    assert cfg["target"]["speed_px_per_frame"] == pytest.approx(9.9)

def test_nonexistent_path_uses_defaults():
    cfg = load_config("nonexistent.yaml")
    assert cfg["experiment"]["seed"] == 42

def test_schema_rejects_bad_world():
    cfg = load_config()
    cfg["world"]["width"] = 100  # below 2000
    with pytest.raises(AssertionError):
        validate_config(cfg)

def test_schema_rejects_bad_fov():
    cfg = load_config()
    cfg["camera"]["fov_deg"] = [20, 20]
    with pytest.raises(AssertionError):
        validate_config(cfg)

def test_schema_allows_user_defined_shape():
    cfg = load_config()
    cfg["target"]["shape"] = "user-defined"
    cfg["target"]["custom_polygon"] = [[-5,-5],[5,-5],[0,5]]
    # should not raise after patch
    validate_config(cfg)

@pytest.mark.parametrize("preset_file", sorted(glob.glob(os.path.join(CONFIGS_DIR, "P*.yaml"))))
def test_each_preset_loads_and_validates(preset_file):
    cfg = load_config(preset_file)
    assert "world" in cfg and "camera" in cfg and "target" in cfg
    assert 0 <= cfg["experiment"]["seed"] <= 999999
    # fps in allowed
    assert 30 <= cfg["camera"]["fps"] <= 60
    # jitter in allowed
    assert 0 <= cfg["camera"]["jitter_px"] <= 20
    # noise in allowed
    assert 0 <= cfg["noise"]["gaussian_std"] <= 20
    assert 0 <= cfg["noise"]["salt_pepper_prob"] <= 0.15
    # preset_meta present and well-formed
    meta = cfg.get("preset_meta", {})
    assert "preset" in meta, f"{preset_file} missing preset_meta.preset"
    assert "purpose" in meta
    assert "expected" in meta
    assert isinstance(meta["expected"], dict)

def test_all_12_presets_present():
    files = sorted(glob.glob(os.path.join(CONFIGS_DIR, "P*.yaml")))
    assert len(files) == 12, f"Expected 12 presets, found {len(files)}: {files}"
    # seeds 42..53 in order
    seeds = [load_config(p)["experiment"]["seed"] for p in files]
    assert seeds == list(range(42, 54)), f"Seeds not 42..53: {seeds}"
    # trajectories coverage
    trajs = {load_config(p)["target"]["trajectory"] for p in files}
    for needed in ["straight", "circular", "figure_eight", "random"]:
        assert needed in trajs, f"Missing trajectory {needed} in {trajs}"

def test_p01_shared_defaults():
    cfg = load_config(os.path.join(CONFIGS_DIR, "P01_clean_baseline.yaml"))
    assert cfg["camera"]["fov_deg"] == [4.0, 3.0]
    assert cfg["camera"]["max_pan_speed"] == 5.0
    assert cfg["target"]["size"] == 10
    assert cfg["controller"]["kp_pan"] == pytest.approx(1.0)
    assert cfg["controller"]["kd"] == pytest.approx(0.15)
    assert cfg["tracker"]["gate_sigma"] == pytest.approx(3.0)

def test_p11_visibility_schedule_preserved():
    cfg = load_config(os.path.join(CONFIGS_DIR, "P11_forced_loss_reacquisition.yaml"))
    # visible via either cfg["target"] or top-level
    sched = cfg["target"].get("visibility_schedule") or cfg.get("visibility_schedule")
    assert sched is not None
    assert len(sched) == 3
    assert sched[1][2] == "hidden"

def test_p12_video_fields():
    cfg = load_config(os.path.join(CONFIGS_DIR, "P12_external_mp4_benchmark.yaml"))
    assert cfg["experiment"]["input_mode"] == "VIDEO"
    assert cfg["experiment"]["video_path"] == "data/input_videos/test_beacon.mp4"
    assert cfg["experiment"].get("preserve_native_fps") is True
    assert cfg["experiment"].get("bypass_virtual_ptz") is True

def test_save_and_reload_roundtrip(tmp_path):
    cfg = load_config()
    cfg["target"]["speed_px_per_frame"] = 7.7
    cfg["experiment"]["seed"] = 12345
    out = tmp_path / "roundtrip.yaml"
    save_config(cfg, str(out))
    reloaded = load_config(str(out))
    assert reloaded["target"]["speed_px_per_frame"] == pytest.approx(7.7)
    assert reloaded["experiment"]["seed"] == 12345

def test_control_deck_discovers_presets_headless():
    """Control Deck must discover P01-P12 without launching GUI window."""
    import glob as _glob
    preset_files = sorted(_glob.glob(os.path.join(CONFIGS_DIR, "*.yaml")))
    # Simulate ControlDeck discovery logic
    preset_map = {}
    for pf in preset_files:
        base = os.path.splitext(os.path.basename(pf))[0]
        if base.startswith("P") and "_" in base:
            prefix = base[:3]
            rest = base[4:] if len(base) > 4 else base[3:]
            pretty = f"{prefix} - {rest.replace('_',' ').title()}"
        else:
            pretty = base.replace("_"," ").title()
        preset_map[pretty] = pf
    assert "P01 - Clean Baseline" in preset_map
    assert "P12 - External Mp4 Benchmark" in preset_map
    assert len([k for k in preset_map if k.startswith("P")]) == 12
    # Each file must yaml-load
    for pretty, pf in preset_map.items():
        if pretty.startswith("P"):
            data = yaml.safe_load(open(pf, encoding="utf-8")) or {}
            assert "preset_meta" in data

def test_p09_platform_extra_fields_preserved():
    cfg = load_config(os.path.join(CONFIGS_DIR, "P09_linear_platform_motion.yaml"))
    plat = cfg["platform"]
    assert plat["type"] == "linear"
    # extra fields from preset plan preserved via deep_merge passthrough
    assert plat.get("velocity_px_frame") == [12, -8]
    assert plat.get("max_displacement_px") == 500

def test_search_fields_preserved():
    for pid in ["P10_edge_of_fov_acquisition", "P11_forced_loss_reacquisition"]:
        cfg = load_config(os.path.join(CONFIGS_DIR, f"{pid}.yaml"))
        assert "search" in cfg
        assert "mode" in cfg["search"]
