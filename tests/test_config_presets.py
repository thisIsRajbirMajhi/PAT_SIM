"""Tests for config loading, validation, and curated/benchmark presets."""

import copy
import os

import pytest
import yaml

from fsoc_tracker.config.loader import deep_merge, load_config, save_config
from fsoc_tracker.config.presets import discover_presets
from fsoc_tracker.config.schema import validate_config


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BENCHMARKS_DIR = os.path.join(ROOT, "configs", "benchmarks")
PRESETS_DIR = os.path.join(ROOT, "configs", "presets")


def test_defaults_validate():
    cfg = load_config()
    assert cfg["world"]["width"] == 2000
    assert cfg["camera"]["resolution"] == [640, 480]


def test_deep_merge():
    a = {"x": {"a": 1, "b": 2}, "y": 5}
    b = {"x": {"b": 3, "c": 4}, "z": 9}
    out = deep_merge(a, b)
    assert out["x"] == {"a": 1, "b": 3, "c": 4}
    assert out["y"] == 5
    assert out["z"] == 9
    assert a["x"]["b"] == 2


def test_overrides():
    cfg = load_config(overrides={"target": {"speed_px_per_frame": 9.9}})
    assert cfg["target"]["speed_px_per_frame"] == pytest.approx(9.9)


def test_nonexistent_path_uses_defaults():
    cfg = load_config("nonexistent.yaml")
    assert cfg["experiment"]["seed"] == 42


def test_schema_rejects_bad_world():
    cfg = load_config()
    cfg["world"]["width"] = 100
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
    cfg["target"]["custom_polygon"] = [[-5, -5], [5, -5], [0, 5]]
    validate_config(cfg)


@pytest.mark.parametrize(
    "preset_file",
    sorted(
        os.path.join(BENCHMARKS_DIR, name)
        for name in os.listdir(BENCHMARKS_DIR)
        if name.startswith("P") and name.endswith(".yaml")
    ),
)
def test_each_benchmark_loads_and_validates(preset_file):
    cfg = load_config(preset_file)
    assert "world" in cfg and "camera" in cfg and "target" in cfg
    assert 0 <= cfg["experiment"]["seed"] <= 999999
    assert 30 <= cfg["camera"]["fps"] <= 60
    assert 0 <= cfg["camera"]["jitter_px"] <= 20
    assert 0 <= cfg["noise"]["gaussian_std"] <= 20
    assert 0 <= cfg["noise"]["salt_pepper_prob"] <= 0.15
    meta = cfg.get("preset_meta", {})
    assert "preset" in meta, f"{preset_file} missing preset_meta.preset"
    assert "purpose" in meta
    assert "expected" in meta
    assert isinstance(meta["expected"], dict)


def test_all_12_benchmarks_present():
    files = sorted(
        os.path.join(BENCHMARKS_DIR, name)
        for name in os.listdir(BENCHMARKS_DIR)
        if name.startswith("P") and name.endswith(".yaml")
    )
    assert len(files) == 12, f"Expected 12 benchmark scenarios, found {len(files)}"
    seeds = [load_config(path)["experiment"]["seed"] for path in files]
    assert seeds == list(range(42, 54))
    trajectories = {load_config(path)["target"]["trajectory"] for path in files}
    for needed in ["straight", "circular", "figure_eight", "random"]:
        assert needed in trajectories


def test_p01_shared_defaults():
    cfg = load_config(os.path.join(BENCHMARKS_DIR, "P01_clean_baseline.yaml"))
    assert cfg["camera"]["fov_deg"] == [4.0, 3.0]
    assert cfg["camera"]["max_pan_speed"] == 5.0
    assert cfg["target"]["size"] == 10
    assert cfg["controller"]["kp_pan"] == pytest.approx(1.0)
    assert cfg["controller"]["kd"] == pytest.approx(0.15)
    assert cfg["tracker"]["gate_sigma"] == pytest.approx(3.0)


def test_p11_visibility_schedule_preserved():
    cfg = load_config(os.path.join(BENCHMARKS_DIR, "P11_forced_loss_reacquisition.yaml"))
    schedule = cfg["target"].get("visibility_schedule") or cfg.get("visibility_schedule")
    assert schedule is not None
    assert len(schedule) == 3
    assert schedule[1][2] == "hidden"


def test_p12_video_fields():
    cfg = load_config(os.path.join(BENCHMARKS_DIR, "P12_external_mp4_benchmark.yaml"))
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


def test_curated_gui_presets_are_thirty_three_and_declare_system():
    presets = discover_presets(PRESETS_DIR)
    assert [preset.preset_id for preset in presets] == [
        "ai_primary_decoys",
        "classical_baseline",
        "ai_hard_negatives",
        "classical_high_noise",
        "ai_fast_acquisition",
        "classical_video_benchmark",
        "ai_circle_target",
        "classical_circle_target",
        "ai_gaussian_target",
        "classical_gaussian_target",
        "ai_cross_target",
        "classical_cross_and_spiral",
        "ai_random_motion",
        "classical_linear_platform",
        "ai_multi_target_scene",
        "classical_random_platform",
        "ai_signature_disabled",
        "classical_spiral_platform",
        "ai_model_path_test",
        "classical_figure8_platform",
        "ai_failure_fallback",
        "classical_all_noise",
        "ai_rain_low_light",
        "classical_environment_full",
        "ai_user_defined_geometry",
        "classical_colour_camera",
        "ai_platform_linear",
        "classical_raster_search",
        "ai_platform_spiral",
        "classical_hybrid_search",
        "ai_platform_figure8",
        "classical_video_calibrated",
        "classical_custom_geometry",
    ]
    systems = [preset.system for preset in presets]
    assert systems.count("ai") == 16
    assert systems.count("deterministic") == 17
    for preset in presets:
        assert os.path.exists(preset.path)
        cfg = load_config(str(preset.path))
        assert cfg["ai"]["enabled"] is preset.is_ai_preset
        assert "purpose" in preset.__dict__
        assert isinstance(preset.expected, dict)


def test_curated_preset_metadata_and_targets():
    ai = load_config(os.path.join(PRESETS_DIR, "ai_primary_decoys.yaml"))
    assert ai["target"]["count"] == 1
    assert ai["ai"]["enabled"] is True
    assert len(ai["decoys"]["profiles"]) == 2
    classical = load_config(os.path.join(PRESETS_DIR, "classical_baseline.yaml"))
    assert classical["target"]["count"] == 1
    assert classical["ai"]["enabled"] is False
    noisy = load_config(os.path.join(PRESETS_DIR, "classical_high_noise.yaml"))
    assert noisy["ai"]["enabled"] is False
    assert noisy["noise"]["gaussian_enabled"] is True
    assert noisy["atmosphere"]["type"] == "fog"


def test_benchmark_files_are_not_gui_presets():
    gui_ids = {preset.preset_id for preset in discover_presets(PRESETS_DIR)}
    assert not any(preset_id.startswith("P") for preset_id in gui_ids)
    assert not any("P01" in preset.display_name for preset in discover_presets(PRESETS_DIR))


def test_p09_platform_extra_fields_preserved():
    cfg = load_config(os.path.join(BENCHMARKS_DIR, "P09_linear_platform_motion.yaml"))
    platform = cfg["platform"]
    assert platform["type"] == "linear"
    assert platform.get("velocity_px_frame") == [12, -8]
    assert platform.get("max_displacement_px") == 500


def test_search_fields_preserved():
    for preset_id in ["P10_edge_of_fov_acquisition", "P11_forced_loss_reacquisition"]:
        cfg = load_config(os.path.join(BENCHMARKS_DIR, f"{preset_id}.yaml"))
        assert "search" in cfg
        assert "mode" in cfg["search"]
