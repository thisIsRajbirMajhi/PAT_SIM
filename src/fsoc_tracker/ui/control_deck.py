"""Control Deck — mode-first configuration dialog.

Two independent modes, each with its own complete staged parameter set:

* **AI System** — identity/candidate/decoy pipeline and its own scene copy.
* **Deterministic / Classical** — detector -> EKF-IMM -> PID with no AI controls.

Only the active mode is applied. Switching modes never copies values
between the two staged configurations.
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
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from PyQt5.QtCore import Qt, pyqtSignal

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
    """Return an independent staged configuration for the AI mode."""
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
    """Return an independent staged configuration for the classical mode."""
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
        self.setWindowTitle("Control Deck — FSOC Tracker")
        self.resize(1180, 820)
        self.setMinimumSize(980, 680)
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
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(12)

        # ---- Header ----
        title = QLabel("CONTROL DECK")
        title.setStyleSheet("font-size:16px; font-weight:800; color:#0F172A; letter-spacing:1px;")
        lay.addWidget(title)
        intro = QLabel(
            "Pick a mode, tune its parameters, then Apply. Each mode keeps its own "
            "complete staged copy — switching never mixes values."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("color:#64748B; font-size:12px;")
        lay.addWidget(intro)

        # ---- Segmented mode switch ----
        switch_box = QWidget()
        switch_box.setStyleSheet("background:#F1F5F9; border:1px solid #E2E8F0; border-radius:10px;")
        switch_lay = QHBoxLayout(switch_box)
        switch_lay.setContentsMargins(6, 6, 6, 6)
        switch_lay.setSpacing(6)
        self.mode_ai_btn = QPushButton("◉  AI System")
        self.mode_det_btn = QPushButton("◎  Deterministic / Classical")
        for btn in (self.mode_ai_btn, self.mode_det_btn):
            btn.setCheckable(True)
            btn.setMinimumHeight(38)
            btn.setStyleSheet("font-size:13px; font-weight:700;")
        self.mode_ai_btn.clicked.connect(lambda: self._switch_mode("ai"))
        self.mode_det_btn.clicked.connect(lambda: self._switch_mode("deterministic"))
        switch_lay.addWidget(self.mode_ai_btn, 1)
        switch_lay.addWidget(self.mode_det_btn, 1)
        lay.addWidget(switch_box)

        mode_row = QHBoxLayout()
        mode_row.setSpacing(8)
        self.global_ai_check = QCheckBox("AI identification active in the AI mode")
        self.global_ai_check.setStyleSheet("font-weight:600; font-size:12px; color:#1E40AF;")
        self.global_ai_check.toggled.connect(self._on_global_ai_toggled)
        self.global_ai_check.hide()
        mode_row.addWidget(self.global_ai_check)
        mode_row.addStretch()
        mode_holder = QWidget()
        mode_holder.setLayout(mode_row)
        mode_holder.hide()
        lay.addWidget(mode_holder)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet(
            "color:#0F172A; font-size:11px; background:#EFF6FF; "
            "border:1px solid #BFDBFE; padding:8px 10px; border-radius:8px;"
        )
        lay.addWidget(self.status_label)

        # The stacked widget keeps the two configurations independent while the
        # surrounding shell exposes the inactive path instead of silently
        # removing it from the operator's mental model.
        self.system_tabs = QStackedWidget()
        self.tabs = self.system_tabs  # Compatibility alias for older integrations/tests.
        self.ai_panel = SystemControlPanel("ai", self._profiles["ai"], self._ai_presets, self)
        self.deterministic_panel = SystemControlPanel(
            "deterministic", self._profiles["deterministic"], self._deterministic_presets, self
        )
        self.system_tabs.addWidget(self.ai_panel)
        self.system_tabs.addWidget(self.deterministic_panel)
        if self._active_system == "ai":
            self.system_tabs.setCurrentWidget(self.ai_panel)
        else:
            self.system_tabs.setCurrentWidget(self.deterministic_panel)

        active_shell = QFrame()
        active_shell.setObjectName("ActivePathShell")
        active_shell.setStyleSheet(
            "QFrame#ActivePathShell { background:#FFFFFF; border:1px solid #BFDBFE; "
            "border-radius:10px; }"
        )
        active_lay = QVBoxLayout(active_shell)
        active_lay.setContentsMargins(10, 10, 10, 10)
        active_lay.setSpacing(6)
        self.active_path_title = QLabel()
        self.active_path_title.setStyleSheet(
            "color:#1D4ED8; font-size:13px; font-weight:800; letter-spacing:0.7px;"
        )
        active_lay.addWidget(self.active_path_title)
        active_lay.addWidget(self.system_tabs, 1)

        self.inactive_shell = QFrame()
        self.inactive_shell.setObjectName("InactivePathShell")
        self.inactive_shell.setStyleSheet(
            "QFrame#InactivePathShell { background:#F8FAFC; border:1px solid #E2E8F0; "
            "border-radius:10px; }"
        )
        inactive_lay = QVBoxLayout(self.inactive_shell)
        inactive_lay.setContentsMargins(18, 18, 18, 18)
        inactive_lay.setSpacing(12)
        self.inactive_path_title = QLabel()
        self.inactive_path_title.setStyleSheet(
            "color:#64748B; font-size:13px; font-weight:800; letter-spacing:0.7px;"
        )
        inactive_lay.addWidget(self.inactive_path_title)
        inactive_lay.addStretch(1)
        self.inactive_state = QLabel()
        self.inactive_state.setWordWrap(True)
        self.inactive_state.setAlignment(Qt.AlignCenter)
        self.inactive_state.setStyleSheet(
            "color:#64748B; font-size:13px; line-height:1.4; padding:18px;"
        )
        inactive_lay.addWidget(self.inactive_state)
        self.inactive_switch = QPushButton()
        self.inactive_switch.setObjectName("Accent")
        self.inactive_switch.setMinimumHeight(36)
        self.inactive_switch.clicked.connect(
            lambda: self._switch_mode("deterministic" if self._active_system == "ai" else "ai")
        )
        inactive_lay.addWidget(self.inactive_switch)
        inactive_lay.addStretch(1)

        content_row = QHBoxLayout()
        content_row.setSpacing(12)
        content_row.addWidget(active_shell, 3)
        content_row.addWidget(self.inactive_shell, 2)
        lay.addLayout(content_row, 1)

        # Compatibility controls retained for existing tests/integrations (hidden).
        self.preset_combo = QComboBox(self)
        self.preset_combo.addItems([info.display_name for info in self._all_presets] + ["Custom"])
        self.preset_desc = QLabel("", self)
        self.preset_expected = QLabel("", self)
        self.preset_combo.hide()
        self.preset_desc.hide()
        self.preset_expected.hide()
        self.preset_combo.currentTextChanged.connect(self._on_preset_selected)

        # Compatibility AI name tracks the active mode's runtime state.
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
        footer.setSpacing(8)
        self.btn_reset = QPushButton("Reset Active Mode")
        self.btn_reset.setMinimumHeight(34)
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setMinimumHeight(34)
        self.btn_apply = QPushButton("Apply Active Mode")
        self.btn_apply.setObjectName("Primary")
        self.btn_apply.setMinimumHeight(34)
        self.btn_apply.setDefault(True)
        footer.addWidget(self.btn_reset)
        footer.addStretch()
        footer.addWidget(self.btn_cancel)
        footer.addWidget(self.btn_apply)
        lay.addLayout(footer)
        self.btn_reset.clicked.connect(self._restore_active_defaults)
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_apply.clicked.connect(self._apply)

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
        self._paint_mode_switch()
        self._update_path_shell()

    # ------------------------------------------------------------------
    # Active mode helpers
    # ------------------------------------------------------------------
    def _switch_mode(self, system: str) -> None:
        if system not in {"ai", "deterministic"}:
            return
        self._syncing = True
        try:
            self.system_tabs.setCurrentWidget(self._panel_for_system(system))
        finally:
            self._syncing = False
        self._active_system = system
        self._sync_compat_from_active()
        self._sync_global_from_active()
        self._paint_mode_switch()
        self._update_path_shell()

    def _paint_mode_switch(self) -> None:
        active_style = (
            "font-size:13px; font-weight:800; background:#1E3A8A; color:#FFFFFF; "
            "border:1px solid #1E3A8A; border-radius:8px; padding:8px;"
        )
        idle_style = (
            "font-size:13px; font-weight:700; background:#FFFFFF; color:#475569; "
            "border:1px solid #E2E8F0; border-radius:8px; padding:8px;"
        )
        ai_on = self._active_system == "ai"
        self.mode_ai_btn.setChecked(ai_on)
        self.mode_det_btn.setChecked(not ai_on)
        self.mode_ai_btn.setStyleSheet(active_style if ai_on else idle_style)
        self.mode_det_btn.setStyleSheet(idle_style if ai_on else active_style)
        self.mode_ai_btn.setText("◉  AI System — active" if ai_on else "○  AI System")
        self.mode_det_btn.setText(
            "○  Deterministic / Classical" if ai_on else "◉  Deterministic / Classical — active"
        )

    def _update_path_shell(self) -> None:
        """Refresh the active/inactive path framing around the stacked panel."""
        is_ai = self._active_system == "ai"
        active_name = "AI-ENABLED PATH" if is_ai else "CLASSICAL PATH"
        inactive_name = "CLASSICAL PATH" if is_ai else "AI-ENABLED PATH"
        self.active_path_title.setText(active_name)
        self.inactive_path_title.setText(inactive_name)
        self.inactive_state.setText(
            (
                "Classical parameters hidden while the AI path is active.\n\n"
                "Switch paths to edit detector, EKF–IMM, PID and search settings."
            )
            if is_ai
            else (
                "AI parameters hidden while the Classical path is active.\n\n"
                "Switch paths to edit detection, identity and optical-signature settings."
            )
        )
        self.inactive_switch.setText(
            "Switch to Classical" if is_ai else "Switch to AI"
        )
        self.inactive_shell.setStyleSheet(
            "QFrame#InactivePathShell { background:#F8FAFC; border:1px solid #E2E8F0; "
            "border-radius:10px; }"
        )

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
            state = "AI ON" if ai_checked else "AI OFF (staged but disabled)"
            self.status_label.setText(
                f"Active mode: AI System · {state}. "
                "Deterministic parameters stay staged separately, untouched."
            )
        else:
            self.status_label.setText(
                "Active mode: Deterministic / Classical · AI OFF by design. "
                "AI-only parameters stay staged separately, untouched."
            )
        self._paint_mode_switch()

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
            self.preset_desc.setText("Custom: this mode has unsaved independent changes.")
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
        self._update_path_shell()

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
        self._update_path_shell()

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
        self._update_path_shell()

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
            QMessageBox.warning(self, "Reset failed", f"Could not reset active mode:\n{exc}")
            return
        self._profiles[self._active_system] = copy.deepcopy(loaded)
        self.cfg = copy.deepcopy(loaded)
        self._sync_compat_from_active(panel.current_preset())
        self._sync_global_from_active()
        self._update_path_shell()

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
                self, "Invalid settings", f"Cannot apply the active mode:\n{exc}"
            )
            return
        self._profiles[self._active_system] = copy.deepcopy(staged)
        self.cfg = copy.deepcopy(staged)
        self._sync_compat_from_active(panel.current_preset())
        self._sync_global_from_active()
        self._update_path_shell()
        self.configApplied.emit(copy.deepcopy(staged))
        self.accept()
