"""Two-portion Control Deck: AI system and deterministic system.

The dialog no longer mixes AI-only fields with the classical pipeline. Each
top-level portion owns an independent :class:`SystemControlPanel` and staged
configuration copy. Applying the dialog sends only the active portion to the
simulator, while the inactive portion remains staged in the dialog.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Dict, Optional

from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
)
from PyQt5.QtCore import pyqtSignal

from ..config.loader import load_config, save_config
from ..config.presets import (
    GUI_PRESET_DIR,
    PresetInfo,
    discover_presets,
    preset_by_id,
    presets_for_system,
)
from .control_panel import SystemControlPanel


def _initial_ai_config(cfg: Dict) -> Dict:
    """Return an independent staged configuration for the AI portion."""
    if bool(cfg.get("ai", {}).get("enabled", False)):
        staged = copy.deepcopy(cfg)
    else:
        info = preset_by_id("ai_primary_decoys")
        try:
            staged = load_config(str(info.path)) if info is not None else load_config()
        except Exception:
            staged = copy.deepcopy(cfg)
    staged.setdefault("ai", {})["enabled"] = True
    return staged


def _initial_deterministic_config(cfg: Dict) -> Dict:
    """Return an independent staged configuration for the classical portion."""
    if bool(cfg.get("ai", {}).get("enabled", False)):
        info = preset_by_id("classical_baseline")
        try:
            staged = load_config(str(info.path)) if info is not None else load_config()
        except Exception:
            staged = load_config()
    else:
        staged = copy.deepcopy(cfg)
    staged.setdefault("ai", {})["enabled"] = False
    staged.setdefault("decoys", {})["enabled"] = False
    return staged


class ControlDeck(QDialog):
    configApplied = pyqtSignal(dict)

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Control Deck  —  FSOC Tracker")
        self.resize(680, 860)
        self.cfg = copy.deepcopy(cfg)
        from .theme import STYLESHEET
        self.setStyleSheet(STYLESHEET)

        self._all_presets = discover_presets()
        self._preset_map = {info.display_name: info for info in self._all_presets}
        self._ai_presets = presets_for_system("ai")
        self._deterministic_presets = presets_for_system("deterministic")
        self._syncing = False

        self._profiles: Dict[str, Dict] = {
            "ai": _initial_ai_config(self.cfg),
            "deterministic": _initial_deterministic_config(self.cfg),
        }
        self._active_system = (
            "ai" if bool(self.cfg.get("ai", {}).get("enabled", False)) else "deterministic"
        )

        lay = QVBoxLayout(self)
        intro = QLabel(
            "Choose a system portion. Each portion has its own complete parameter set. "
            "Only the active portion is applied."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("color:#475569; font-size:11px;")
        lay.addWidget(intro)

        mode_row = QHBoxLayout()
        mode_label = QLabel("Runtime mode")
        mode_label.setStyleSheet("font-weight:800; font-size:12px;")
        self.global_ai_check = QCheckBox("AI system active — primary/decoy identification")
        self.global_ai_check.setStyleSheet("font-weight:700; color:#1e40af;")
        self.global_ai_check.toggled.connect(self._on_global_ai_toggled)
        mode_row.addWidget(mode_label)
        mode_row.addWidget(self.global_ai_check)
        mode_row.addStretch()
        lay.addLayout(mode_row)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet(
            "color:#0f172a; font-size:10px; background:#f1f5f9; padding:6px; border-radius:4px;"
        )
        lay.addWidget(self.status_label)

        self.system_tabs = QTabWidget()
        self.tabs = self.system_tabs  # Compatibility alias for older integrations/tests.
        self.ai_panel = SystemControlPanel("ai", self._profiles["ai"], self._ai_presets, self)
        self.deterministic_panel = SystemControlPanel(
            "deterministic", self._profiles["deterministic"], self._deterministic_presets, self
        )
        self.system_tabs.addTab(self.ai_panel, "AI System")
        self.system_tabs.addTab(self.deterministic_panel, "Deterministic / Classical")
        if self._active_system == "ai":
            self.system_tabs.setCurrentWidget(self.ai_panel)
        else:
            self.system_tabs.setCurrentWidget(self.deterministic_panel)
        lay.addWidget(self.system_tabs, 1)

        # Compatibility controls retained for existing tests/integrations. They
        # are hidden because each visible portion now has its own preset
        # selector; these objects preserve the old unified names/behavior.
        self.preset_combo = QComboBox(self)
        self.preset_combo.addItems([info.display_name for info in self._all_presets] + ["Custom"])
        self.preset_desc = QLabel("", self)
        self.preset_expected = QLabel("", self)
        self.preset_combo.hide()
        self.preset_desc.hide()
        self.preset_expected.hide()
        self.preset_combo.currentTextChanged.connect(self._on_preset_selected)

        # Compatibility AI name tracks the active portion's runtime mode. The
        # AI-only panel checkbox remains available as ai_panel.ai_enabled_check.
        self.ai_enabled_check = self.global_ai_check
        self.ai_panel.ai_enabled_check.toggled.connect(self._on_ai_panel_toggled)
        self.ai_panel.presetLoadRequested.connect(lambda info: self._apply_panel_preset("ai", info))
        self.deterministic_panel.presetLoadRequested.connect(
            lambda info: self._apply_panel_preset("deterministic", info)
        )
        self.ai_panel.presetSaveRequested.connect(self._save_active_preset)
        self.deterministic_panel.presetSaveRequested.connect(self._save_active_preset)
        self.system_tabs.currentChanged.connect(self._on_system_changed)

        footer = QHBoxLayout()
        self.btn_reset = QPushButton("Reset Active Portion")
        self.btn_cancel = QPushButton("Cancel")
        self.btn_apply = QPushButton("Apply Active Portion")
        self.btn_apply.setDefault(True)
        footer.addWidget(self.btn_reset)
        footer.addStretch()
        footer.addWidget(self.btn_cancel)
        footer.addWidget(self.btn_apply)
        lay.addLayout(footer)
        self.btn_reset.clicked.connect(self._restore_active_defaults)
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_apply.clicked.connect(self._apply)

        # Mark the staged initial presets so both portions display their owner.
        ai_initial = preset_by_id("ai_primary_decoys")
        if ai_initial is not None and self.ai_panel.preset_infos.get(ai_initial.display_name):
            self.ai_panel.set_preset(ai_initial)
        det_initial_id = self._profiles["deterministic"].get("preset_meta", {}).get("preset")
        det_initial = preset_by_id(det_initial_id) if det_initial_id else None
        if det_initial is not None and self.deterministic_panel.preset_infos.get(det_initial.display_name):
            self.deterministic_panel.set_preset(det_initial)
        else:
            self.deterministic_panel.set_preset(None)
        self._sync_compat_from_active()
        self._sync_global_from_active()

    # ------------------------------------------------------------------
    # Active portion helpers
    # ------------------------------------------------------------------
    def _active_panel(self) -> SystemControlPanel:
        return self.ai_panel if self._active_system == "ai" else self.deterministic_panel

    def _panel_for_system(self, system: str) -> SystemControlPanel:
        return self.ai_panel if system == "ai" else self.deterministic_panel

    def _sync_global_from_active(self) -> None:
        ai_checked = self.ai_panel.ai_enabled_check.isChecked()
        self._syncing = True
        try:
            self.global_ai_check.setChecked(self._active_system == "ai" and ai_checked)
        finally:
            self._syncing = False
        if self._active_system == "ai":
            state = "AI ON" if ai_checked else "AI OFF (AI portion staged but disabled)"
            self.status_label.setText(
                f"Active portion: AI System · {state}. "
                "Deterministic parameters are staged separately and untouched."
            )
        else:
            self.status_label.setText(
                "Active portion: Deterministic / Classical · AI OFF by design. "
                "AI-only parameters are staged separately and untouched."
            )

    def _sync_compat_from_active(self, info: Optional[PresetInfo] = None) -> None:
        panel = self._active_panel()
        selected = info if info is not None else panel.current_preset()
        self._syncing = True
        try:
            if selected is not None and self.preset_combo.findText(selected.display_name) >= 0:
                self.preset_combo.setCurrentText(selected.display_name)
            else:
                self.preset_combo.setCurrentText("Custom")
        finally:
            self._syncing = False
        self._update_compat_description(selected)

    def _update_compat_description(self, info: Optional[PresetInfo]) -> None:
        if info is None:
            self.preset_desc.setText("Custom: this portion has unsaved independent changes.")
            self.preset_expected.setText("")
            return
        mode = "AI ON" if info.is_ai_preset else "AI OFF"
        self.preset_desc.setText(f"{mode} · {info.purpose}")
        if info.expected:
            self.preset_expected.setText(
                "Expected: " + ", ".join(f"{key}: {value}" for key, value in info.expected.items())
            )
        else:
            self.preset_expected.setText("")

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------
    def _on_system_changed(self, _index: int) -> None:
        widget = self.system_tabs.currentWidget()
        self._active_system = "ai" if widget is self.ai_panel else "deterministic"
        self._sync_compat_from_active()
        self._sync_global_from_active()

    def _on_ai_panel_toggled(self, _checked: bool) -> None:
        if self._active_system == "ai":
            self._sync_global_from_active()

    def _on_global_ai_toggled(self, checked: bool) -> None:
        if self._syncing:
            return
        if checked:
            self._syncing = True
            try:
                self.system_tabs.setCurrentWidget(self.ai_panel)
            finally:
                self._syncing = False
            self._active_system = "ai"
            self.ai_panel.set_ai_enabled(True)
        elif self._active_system == "ai":
            self.ai_panel.set_ai_enabled(False)
        self._sync_global_from_active()

    # ------------------------------------------------------------------
    # Presets
    # ------------------------------------------------------------------
    def _on_preset_selected(self, name: str) -> None:
        if self._syncing:
            return
        info = self._preset_map.get(name)
        self._update_compat_description(info)
        if info is None:
            return
        # Loading from the compatibility selector moves to the preset's owner.
        self._apply_panel_preset("ai" if info.is_ai_preset else "deterministic", info)

    def _load_preset(self) -> None:
        info = self._preset_map.get(self.preset_combo.currentText())
        if info is None:
            return
        self._apply_panel_preset("ai" if info.is_ai_preset else "deterministic", info)

    def _apply_panel_preset(self, system: str, info: PresetInfo) -> None:
        if system != self._active_system:
            self._syncing = True
            try:
                self.system_tabs.setCurrentWidget(self._panel_for_system(system))
            finally:
                self._syncing = False
            self._active_system = system
        panel = self._panel_for_system(system)
        try:
            loaded = panel.load_preset(info)
        except Exception as exc:
            QMessageBox.warning(self, "Preset failed", f"Could not load {info.display_name}:\n{exc}")
            return
        self._profiles[system] = copy.deepcopy(loaded)
        self.cfg = copy.deepcopy(loaded)
        self._sync_compat_from_active(info)
        self._sync_global_from_active()

    def _restore_active_defaults(self) -> None:
        panel = self._active_panel()
        try:
            if self._active_system == "ai":
                info = preset_by_id("ai_primary_decoys")
                loaded = panel.load_preset(info) if info else panel.collect_config()
            else:
                loaded = load_config()
                loaded.setdefault("ai", {})["enabled"] = False
                panel.set_config(loaded)
                panel.set_preset(None)
                panel.cfg = copy.deepcopy(loaded)
        except Exception as exc:
            QMessageBox.warning(self, "Reset failed", f"Could not reset active portion:\n{exc}")
            return
        self._profiles[self._active_system] = copy.deepcopy(loaded)
        self.cfg = copy.deepcopy(loaded)
        self._sync_compat_from_active(panel.current_preset())
        self._sync_global_from_active()

    def _save_active_preset(self) -> None:
        panel = self._active_panel()
        try:
            staged = panel.collect_config()
        except Exception as exc:
            QMessageBox.warning(self, "Save failed", f"Cannot save invalid settings:\n{exc}")
            return
        default_name = "ai_custom_preset.yaml" if self._active_system == "ai" else "deterministic_custom_preset.yaml"
        path, _ = QFileDialog.getSaveFileName(
            self,
            f"Save {self._active_system} preset",
            str(GUI_PRESET_DIR / default_name),
            "YAML files (*.yaml *.yml)",
        )
        if not path:
            return
        file_path = Path(path)
        stem = file_path.stem.strip().replace(" ", "_").lower() or file_path.stem
        expected = {
            "targets": f"{staged['target']['count']} staged",
            "mode": "AI ON" if self._active_system == "ai" else "AI OFF",
        }
        staged["preset_meta"] = {
            "preset": stem,
            "display_name": stem.replace("_", " ").strip().title(),
            "order": 90,
            "system": self._active_system,
            "ai_mode": "ON" if self._active_system == "ai" else "OFF",
            "purpose": f"User-saved {self._active_system} Control Deck preset.",
            "expected": expected,
        }
        try:
            save_config(staged, str(file_path))
        except Exception as exc:
            QMessageBox.warning(self, "Save failed", f"Could not write preset:\n{exc}")
            return
        info = PresetInfo(
            preset_id=stem,
            display_name=staged["preset_meta"]["display_name"],
            path=file_path,
            ai_mode=staged["preset_meta"]["ai_mode"],
            purpose=staged["preset_meta"]["purpose"],
            expected=expected,
            order=90,
            system=self._active_system,
        )
        self._all_presets.append(info)
        self._preset_map[info.display_name] = info
        panel.preset_infos[info.display_name] = info
        panel.presets.append(info)
        panel.preset_combo.addItem(info.display_name)
        panel.set_preset(info)
        panel.cfg = copy.deepcopy(staged)
        self._profiles[self._active_system] = copy.deepcopy(staged)
        self._sync_compat_from_active(info)
        QMessageBox.information(self, "Preset saved", f"Saved {info.display_name}.")

    # ------------------------------------------------------------------
    # Apply
    # ------------------------------------------------------------------
    def _apply(self) -> None:
        panel = self._active_panel()
        try:
            staged = panel.collect_config()
        except Exception as exc:
            QMessageBox.warning(
                self, "Invalid settings", f"Cannot apply the active portion:\n{exc}"
            )
            return
        self._profiles[self._active_system] = copy.deepcopy(staged)
        self.cfg = copy.deepcopy(staged)
        self._sync_compat_from_active(panel.current_preset())
        self._sync_global_from_active()
        self.configApplied.emit(copy.deepcopy(staged))
        self.accept()
