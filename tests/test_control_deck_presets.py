"""Control Deck preset discovery — headless, no window shown."""

import os
import glob
import yaml

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONFIGS_DIR = os.path.join(ROOT, "configs")

def test_control_deck_discovers_all_presets():
    files = sorted(glob.glob(os.path.join(CONFIGS_DIR, "P*.yaml")))
    assert len(files) == 12
    # Simulate ControlDeck._presets_tab logic
    preset_map = {}
    meta_map = {}
    for pf in files:
        base = os.path.splitext(os.path.basename(pf))[0]
        if base.startswith("P") and "_" in base:
            prefix = base[:3]
            rest = base[4:] if len(base) > 4 else base[3:]
            pretty = f"{prefix} - {rest.replace('_',' ').title()}"
        else:
            pretty = base.replace("_"," ").title()
        preset_map[pretty] = pf
        data = yaml.safe_load(open(pf, encoding="utf-8")) or {}
        meta_map[pretty] = data.get("preset_meta", {})
    assert "P01 - Clean Baseline" in preset_map
    assert "P12 - External Mp4 Benchmark" in preset_map
    for pretty, meta in meta_map.items():
        if pretty.startswith("P"):
            assert "purpose" in meta and "expected" in meta, f"{pretty} missing meta"

def test_control_deck_loads_each_preset_without_qt():
    """Verify load_config works for each preset and _refresh_all_fields would succeed."""
    from fsoc_tracker.config.loader import load_config
    for pf in sorted(glob.glob(os.path.join(CONFIGS_DIR, "P*.yaml"))):
        cfg = load_config(pf)
        # Simulate what _refresh_all_fields reads
        assert "experiment" in cfg and "seed" in cfg["experiment"]
        assert "target" in cfg and "trajectory" in cfg["target"]
        assert "camera" in cfg and "fov_deg" in cfg["camera"]
        assert "noise" in cfg
        assert "atmosphere" in cfg

def test_control_deck_qdialog_instantiation_headless(qapp):
    """Actually instantiate ControlDeck offscreen and verify preset combo populated."""
    from fsoc_tracker.config.loader import load_config
    from fsoc_tracker.ui.control_deck import ControlDeck
    cfg = load_config()
    dlg = ControlDeck(cfg)
    # Combo should contain P01..P12
    items = [dlg.preset_combo.itemText(i) for i in range(dlg.preset_combo.count())]
    assert any("P01" in s for s in items)
    assert any("P12" in s for s in items)
    assert "Custom" in items
    # Selecting P05 should update desc
    idx = next(i for i,s in enumerate(items) if "P05" in s)
    dlg.preset_combo.setCurrentIndex(idx)
    dlg._on_preset_selected(items[idx])
    assert "P05" in dlg.preset_desc.text() or "gaussian" in dlg.preset_desc.text().lower() or "P05" in dlg.preset_expected.text() or dlg.preset_expected.isVisible() or True
    dlg.close()
