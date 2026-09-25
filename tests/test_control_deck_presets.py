"""Control Deck preset discovery and AI-state propagation tests."""

import glob
import os

import pytest


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONFIGS_DIR = os.path.join(ROOT, "configs")
PRESETS_DIR = os.path.join(CONFIGS_DIR, "presets")
BENCHMARKS_DIR = os.path.join(CONFIGS_DIR, "benchmarks")


def test_control_deck_discovers_only_curated_presets():
    from fsoc_tracker.config.presets import discover_presets

    presets = discover_presets(PRESETS_DIR)
    assert len(presets) == 33
    ids = {preset.preset_id for preset in presets}
    assert len(ids) == 33
    assert {p.system for p in presets} == {"ai", "deterministic"}
    assert sum(1 for p in presets if p.system == "ai") == 16
    assert sum(1 for p in presets if p.system == "deterministic") == 17
    assert not any("P01" in preset.display_name for preset in presets)
    assert not any(os.path.basename(path).startswith("P") for path in glob.glob(os.path.join(PRESETS_DIR, "*.yaml")))


def test_benchmark_configs_remain_available_for_regression():
    files = sorted(glob.glob(os.path.join(BENCHMARKS_DIR, "P*.yaml")))
    assert len(files) == 12
    for path in files:
        assert os.path.exists(path)


def test_control_deck_loads_each_curated_preset_without_qt():
    from fsoc_tracker.config.loader import load_config
    from fsoc_tracker.config.presets import discover_presets

    for preset in discover_presets(PRESETS_DIR):
        cfg = load_config(str(preset.path))
        assert "experiment" in cfg and "seed" in cfg["experiment"]
        assert "target" in cfg and "trajectory" in cfg["target"]
        assert "camera" in cfg and "fov_deg" in cfg["camera"]
        assert "noise" in cfg and "atmosphere" in cfg
        assert cfg["ai"]["enabled"] is preset.is_ai_preset


def test_control_deck_qdialog_instantiation_headless(qapp):
    """The actual dialog exposes four file-backed presets plus Custom."""
    from fsoc_tracker.config.loader import load_config
    from fsoc_tracker.ui.control_deck import ControlDeck

    dlg = ControlDeck(load_config())
    items = [dlg.preset_combo.itemText(i) for i in range(dlg.preset_combo.count())]
    assert items[-1] == "Custom"
    assert len(items) == 34
    assert not any("P01" in item or "P12" in item for item in items)
    assert any("AI" in item and "Primary" in item for item in items)
    assert any("Classical" in item for item in items)

    ai_index = next(i for i, item in enumerate(items) if "Primary" in item)
    dlg.preset_combo.setCurrentIndex(ai_index)
    dlg._on_preset_selected(items[ai_index])
    assert "AI ON" in dlg.preset_desc.text()
    assert dlg.preset_expected.text().startswith("Expected:")
    dlg.close()


@pytest.mark.parametrize(
    ("preset_id", "expected_ai", "expected_count"),
    [
        ("ai_primary_decoys", True, 1),
        ("classical_baseline", False, 1),
        ("ai_hard_negatives", True, 1),
        ("classical_high_noise", False, 1),
        ("ai_fast_acquisition", True, 1),
        ("classical_video_benchmark", False, 1),
        ("ai_circle_target", True, 1),
        ("classical_circle_target", False, 1),
        ("ai_gaussian_target", True, 1),
        ("classical_gaussian_target", False, 1),
        ("ai_cross_target", True, 1),
        ("classical_cross_and_spiral", False, 1),
        ("ai_random_motion", True, 1),
        ("classical_linear_platform", False, 1),
        ("ai_multi_target_scene", True, 5),
        ("classical_random_platform", False, 1),
        ("ai_signature_disabled", True, 1),
        ("classical_spiral_platform", False, 1),
        ("ai_model_path_test", True, 1),
        ("classical_figure8_platform", False, 1),
        ("ai_failure_fallback", True, 1),
        ("classical_all_noise", False, 1),
        ("ai_rain_low_light", True, 1),
        ("classical_environment_full", False, 1),
        ("ai_user_defined_geometry", True, 1),
        ("classical_colour_camera", False, 1),
        ("ai_platform_linear", True, 1),
        ("classical_raster_search", False, 1),
        ("ai_platform_spiral", True, 1),
        ("classical_hybrid_search", False, 1),
        ("ai_platform_figure8", True, 1),
        ("classical_video_calibrated", False, 1),
        ("classical_custom_geometry", False, 1),
    ],
)
def test_control_deck_loading_preset_preserves_ai_state(
    qapp, monkeypatch, preset_id, expected_ai, expected_count
):
    from PyQt5.QtWidgets import QMessageBox
    from fsoc_tracker.config.loader import load_config
    from fsoc_tracker.config.presets import discover_presets
    from fsoc_tracker.ui.control_deck import ControlDeck

    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
    dlg = ControlDeck(load_config())
    preset = next(item for item in discover_presets(PRESETS_DIR) if item.preset_id == preset_id)
    dlg.preset_combo.setCurrentText(preset.display_name)
    dlg._load_preset()
    assert dlg.cfg["ai"]["enabled"] is expected_ai
    assert dlg.global_ai_check.isChecked() is expected_ai
    assert dlg.ai_enabled_check.isChecked() is expected_ai
    assert dlg.cfg["target"]["count"] == expected_count
    dlg.close()
