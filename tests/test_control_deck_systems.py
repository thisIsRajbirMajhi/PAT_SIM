"""Two-portion Control Deck regression tests."""

from fsoc_tracker.config.presets import presets_for_system


def _panel_items(panel):
    return [
        panel.preset_combo.itemText(i) for i in range(panel.preset_combo.count())
    ]


def test_control_deck_splits_ai_and_deterministic_portions(qapp):
    from fsoc_tracker.config.loader import load_config
    from fsoc_tracker.ui.control_deck import ControlDeck

    dlg = ControlDeck(load_config())
    try:
        assert dlg.system_tabs.count() == 2
        assert dlg.system_tabs.tabText(0) == "AI System"
        assert dlg.system_tabs.tabText(1) == "Deterministic / Classical"

        ai_items = _panel_items(dlg.ai_panel)
        det_items = _panel_items(dlg.deterministic_panel)
        assert ai_items == [info.display_name for info in presets_for_system("ai")] + ["Custom"]
        assert det_items == [info.display_name for info in presets_for_system("deterministic")] + ["Custom"]
        assert set(ai_items).isdisjoint(det_items[:-1])
        assert "ai.enabled" in dlg.ai_panel.controls
        assert "ai.enabled" not in dlg.deterministic_panel.controls
        assert "ai.thresholds.primary_threshold" in dlg.ai_panel.controls
        assert "ai.thresholds.primary_threshold" not in dlg.deterministic_panel.controls
    finally:
        dlg.close()


def test_control_deck_stages_ai_and_deterministic_values_separately(qapp):
    from fsoc_tracker.config.loader import load_config
    from fsoc_tracker.ui.control_deck import ControlDeck

    dlg = ControlDeck(load_config())
    try:
        dlg.ai_panel.controls["experiment.seed"][1].setValue(111)
        dlg.deterministic_panel.controls["experiment.seed"][1].setValue(222)

        ai_cfg = dlg.ai_panel.collect_config()
        det_cfg = dlg.deterministic_panel.collect_config()

        assert ai_cfg["experiment"]["seed"] == 111
        assert det_cfg["experiment"]["seed"] == 222
        assert ai_cfg["ai"]["enabled"] is True
        assert det_cfg["ai"]["enabled"] is False
    finally:
        dlg.close()


def test_control_deck_preset_loading_preserves_inactive_portion(qapp):
    from fsoc_tracker.config.loader import load_config
    from fsoc_tracker.config.presets import preset_by_id
    from fsoc_tracker.ui.control_deck import ControlDeck

    dlg = ControlDeck(load_config())
    try:
        ai_info = preset_by_id("ai_primary_decoys")
        det_info = preset_by_id("classical_baseline")
        assert ai_info is not None and det_info is not None

        dlg._apply_panel_preset("ai", ai_info)
        dlg.ai_panel.controls["experiment.seed"][1].setValue(777)
        dlg._apply_panel_preset("deterministic", det_info)

        assert dlg._active_system == "deterministic"
        assert dlg.cfg["ai"]["enabled"] is False
        assert dlg.deterministic_panel.collect_config()["experiment"]["seed"] == 42
        assert dlg.ai_panel.controls["experiment.seed"][1].value() == 777
        assert dlg.ai_panel.collect_config()["ai"]["enabled"] is True
    finally:
        dlg.close()


def test_control_deck_apply_sends_only_active_portion(qapp):
    from fsoc_tracker.config.loader import load_config
    from fsoc_tracker.ui.control_deck import ControlDeck

    dlg = ControlDeck(load_config())
    received = []
    dlg.configApplied.connect(received.append)
    try:
        dlg.system_tabs.setCurrentWidget(dlg.deterministic_panel)
        dlg.deterministic_panel.controls["experiment.seed"][1].setValue(555)
        dlg._apply()

        assert len(received) == 1
        assert received[0]["experiment"]["seed"] == 555
        assert received[0]["ai"]["enabled"] is False
    finally:
        dlg.close()
