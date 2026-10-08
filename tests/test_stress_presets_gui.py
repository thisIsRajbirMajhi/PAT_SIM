import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def test_shared_list_has_all_ten():
    from fsoc_tracker.config.stress_presets import SCENARIOS
    assert len(SCENARIOS) == 10
    for k in ("X1-baseline", "X8-cold-start", "X10-combined-hell"):
        assert k in SCENARIOS


def test_gui_panel_lists_all_ten():
    from PyQt5.QtWidgets import QApplication, QMessageBox
    QMessageBox.information = staticmethod(lambda *a, **k: None)
    QMessageBox.warning = staticmethod(lambda *a, **k: None)
    from fsoc_tracker.config.loader import load_config
    from fsoc_tracker.ui.control_deck import ControlDeck
    app = QApplication.instance() or QApplication([])
    deck = ControlDeck(load_config())
    items = [deck.preset_combo.itemText(i) for i in range(deck.preset_combo.count())]
    stress = [t for t in items if t.startswith("Stress:")]
    assert len(stress) == 10


def test_gui_load_applies_overrides():
    from PyQt5.QtWidgets import QApplication, QMessageBox
    QMessageBox.information = staticmethod(lambda *a, **k: None)
    QMessageBox.warning = staticmethod(lambda *a, **k: None)
    from fsoc_tracker.config.loader import load_config
    from fsoc_tracker.ui.control_deck import ControlDeck
    app = QApplication.instance() or QApplication([])
    deck = ControlDeck(load_config())
    deck.preset_combo.setCurrentText("Stress: X4-speed-demon")
    deck._load_preset()
    assert float(deck.cfg["target"]["speed_px_per_frame"]) == 20.0
    deck.preset_combo.setCurrentText("Stress: X8-cold-start")
    deck._load_preset()
    assert deck.cfg["target"]["trajectory"] == "straight"
    assert deck.cfg["target"]["initial_pos"] == [300, 300]
