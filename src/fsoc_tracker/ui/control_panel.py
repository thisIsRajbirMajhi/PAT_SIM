"""Independent parameter panels for the two Control Deck systems.

Two self-contained editors:

* ``ai`` — identity/candidate/decoy pipeline plus its own staged copy of the
  scene parameters;
* ``deterministic`` — the classical detector -> EKF-IMM -> PID path.

Switching portions never copies values between systems; only the panel that
is active when Apply is pressed is sent to the simulator.

Layout: section cards with clear headings, human-readable parameter names
with units, and slider + exact-value fields with consistent fonts/spacing.
"""
from __future__ import annotations

import copy
import json
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence, Tuple

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..config.presets import PresetInfo


PathLike = Tuple[str, ...]

# Consistent type scale for the deck.
_FONT_LABEL = "font-size:12px; font-weight:600; color:#0F172A;"
_FONT_HINT = "color:#64748B; font-size:11px;"
_FONT_SECTION = "font-size:13px; font-weight:800;"
_FONT_VALUE = "font-size:12px;"


def _get_path(data: Mapping[str, Any], path: PathLike, default: Any = None) -> Any:
    value: Any = data
    for key in path:
        if isinstance(value, Mapping):
            if key not in value:
                return default
            value = value[key]
        elif isinstance(value, (list, tuple)) and isinstance(key, int):
            if key < 0 or key >= len(value):
                return default
            value = value[key]
        else:
            return default
    return value


def _set_path(data: Dict[str, Any], path: PathLike, value: Any) -> None:
    """Set a mapping path, including numeric indexes inside list values."""
    if not path:
        return
    cursor: Any = data
    for index, key in enumerate(path[:-1]):
        next_key = path[index + 1]
        if isinstance(key, int):
            if not isinstance(cursor, list):
                return
            while len(cursor) <= key:
                cursor.append(None)
            child = cursor[key]
            if isinstance(next_key, int):
                if not isinstance(child, list):
                    child = []
                    cursor[key] = child
            elif not isinstance(child, dict):
                child = {}
                cursor[key] = child
            cursor = child
        else:
            if not isinstance(cursor, dict):
                return
            child = cursor.get(key)
            if isinstance(next_key, int):
                if not isinstance(child, list):
                    child = []
                    cursor[key] = child
            elif not isinstance(child, dict):
                child = {}
                cursor[key] = child
            cursor = child
    last = path[-1]
    if isinstance(last, int):
        if not isinstance(cursor, list):
            return
        while len(cursor) <= last:
            cursor.append(None)
        cursor[last] = value
    elif isinstance(cursor, dict):
        cursor[last] = value


def _json_text(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, indent=2)
    return str(value)


def _parse_json(value: str, field_name: str) -> Any:
    text = value.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{field_name} must contain valid JSON: {exc}") from exc


class _IntSlider(QWidget):
    """Slider + exact spin box for integer parameters (exposes setValue/value)."""

    valueChanged = pyqtSignal(int)

    def __init__(self, value: Any, minimum: int, maximum: int, step: int = 1, unit: str = "", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._min = minimum
        self._max = maximum
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(minimum, maximum)
        self.slider.setSingleStep(step)
        self.slider.setPageStep(max(step, (maximum - minimum) // 10 or 1))
        self.spin = QSpinBox()
        self.spin.setRange(minimum, maximum)
        self.spin.setSingleStep(step)
        self.spin.setFixedWidth(92)
        if unit:
            self.spin.setSuffix(f" {unit}")
        try:
            ivalue = int(round(float(value if value is not None else 0)))
        except Exception:
            ivalue = minimum
        ivalue = max(minimum, min(maximum, ivalue))
        self.slider.setValue(ivalue)
        self.spin.setValue(ivalue)
        self.slider.valueChanged.connect(self._from_slider)
        self.spin.valueChanged.connect(self._from_spin)
        lay.addWidget(self.slider, 1)
        lay.addWidget(self.spin)

    def _from_slider(self, v: int) -> None:
        if self.spin.value() != v:
            self.spin.blockSignals(True)
            self.spin.setValue(v)
            self.spin.blockSignals(False)
        self.valueChanged.emit(v)

    def _from_spin(self, v: int) -> None:
        if self.slider.value() != v:
            self.slider.blockSignals(True)
            self.slider.setValue(v)
            self.slider.blockSignals(False)
        self.valueChanged.emit(v)

    def value(self) -> int:
        return int(self.spin.value())

    def setValue(self, v: Any) -> None:
        try:
            iv = int(round(float(v)))
        except Exception:
            return
        iv = max(self._min, min(self._max, iv))
        self.slider.setValue(iv)
        self.spin.setValue(iv)


class _FloatSlider(QWidget):
    """Slider + exact spin box for float parameters (exposes setValue/value)."""

    valueChanged = pyqtSignal(float)

    def __init__(self, value: Any, minimum: float, maximum: float, step: float = 0.1,
                 decimals: int = 3, unit: str = "", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._min = float(minimum)
        self._max = float(maximum)
        self._decimals = decimals
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 1000)
        self.slider.setSingleStep(1)
        self.slider.setPageStep(50)
        self.spin = QDoubleSpinBox()
        self.spin.setRange(self._min, self._max)
        self.spin.setSingleStep(step)
        self.spin.setDecimals(decimals)
        self.spin.setFixedWidth(110)
        if unit:
            self.spin.setSuffix(f" {unit}")
        try:
            fvalue = float(value if value is not None else 0.0)
        except Exception:
            fvalue = self._min
        fvalue = max(self._min, min(self._max, fvalue))
        self.spin.setValue(fvalue)
        self.slider.setValue(self._to_slider(fvalue))
        self.slider.valueChanged.connect(self._from_slider)
        self.spin.valueChanged.connect(self._from_spin)
        lay.addWidget(self.slider, 1)
        lay.addWidget(self.spin)

    def _to_slider(self, v: float) -> int:
        span = self._max - self._min
        if span <= 0:
            return 0
        return int(round((v - self._min) / span * 1000))

    def _to_value(self, s: int) -> float:
        return self._min + (self._max - self._min) * (s / 1000.0)

    def _from_slider(self, s: int) -> None:
        v = round(self._to_value(s), self._decimals)
        if abs(self.spin.value() - v) > 10 ** (-self._decimals):
            self.spin.blockSignals(True)
            self.spin.setValue(v)
            self.spin.blockSignals(False)
        self.valueChanged.emit(float(v))

    def _from_spin(self, v: float) -> None:
        s = self._to_slider(float(v))
        if self.slider.value() != s:
            self.slider.blockSignals(True)
            self.slider.setValue(s)
            self.slider.blockSignals(False)
        self.valueChanged.emit(float(v))

    def value(self) -> float:
        return float(self.spin.value())

    def setValue(self, v: Any) -> None:
        try:
            fv = float(v)
        except Exception:
            return
        fv = max(self._min, min(self._max, fv))
        self.spin.setValue(fv)
        self.slider.setValue(self._to_slider(fv))


class SystemControlPanel(QWidget):
    """A self-contained editor for one simulator system."""

    presetLoadRequested = pyqtSignal(object)
    presetSaveRequested = pyqtSignal()

    def __init__(
        self,
        system: str,
        config: Dict[str, Any],
        presets: Sequence[PresetInfo],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.system = "ai" if str(system).lower() == "ai" else "deterministic"
        self.is_ai_panel = self.system == "ai"
        self.cfg: Dict[str, Any] = copy.deepcopy(config)
        self.presets = list(presets)
        self.preset_infos: Dict[str, PresetInfo] = {
            info.display_name: info for info in self.presets
        }
        self.controls: Dict[str, Tuple[PathLike, QWidget]] = {}
        self._current_preset: Optional[PresetInfo] = None
        self._build()
        self.set_config(self.cfg)

    # ------------------------------------------------------------------
    # Widget helpers
    # ------------------------------------------------------------------
    def _group(self, body_layout: QVBoxLayout, title: str, description: str = "") -> QFormLayout:
        box = QGroupBox(title)
        box.setStyleSheet(
            f"QGroupBox {{ {_FONT_SECTION} color:#0F172A; border:1px solid #E2E8F0; "
            "border-radius:8px; background:#FFFFFF; margin-top:14px; padding-top:6px; }"
            "QGroupBox::title { subcontrol-origin: margin; left:10px; padding:0 6px; "
            "background:#FFFFFF; color:#1E3A8A; }"
        )
        form = QFormLayout(box)
        form.setContentsMargins(14, 14, 14, 14)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        if description:
            label = QLabel(description)
            label.setWordWrap(True)
            label.setStyleSheet(_FONT_HINT)
            form.addRow(label)
        body_layout.addWidget(box)
        return form

    def _add(
        self,
        form: QFormLayout,
        label: str,
        name: str,
        path: PathLike,
        widget: QWidget,
        hint: str = "",
    ) -> QWidget:
        self.controls[name] = (path, widget)
        # Keep dependent controls visually honest while the user edits the
        # staged configuration.  Signals are connected here so preset loads
        # and manual edits use the same dependency rules.
        if name in {
            "experiment.input_mode",
            "target.shape",
            "target.trajectory",
            "target.initial_mode",
            "noise.gaussian_enabled",
            "noise.salt_pepper_enabled",
            "environment.gradient_enabled",
            "environment.stars_enabled",
            "environment.vignetting_enabled",
            "ai.enabled",
            "ai.signatures.enabled",
        }:
            if isinstance(widget, QCheckBox):
                widget.toggled.connect(lambda _checked: self._on_conditional_changed())
            elif isinstance(widget, QComboBox):
                widget.currentTextChanged.connect(lambda _text: self._on_conditional_changed())
        name_label = QLabel(label)
        name_label.setStyleSheet(_FONT_LABEL)
        name_label.setWordWrap(True)
        name_label.setMinimumWidth(210)
        if hint:
            widget.setToolTip(hint)
            name_label.setToolTip(hint)
        if hint and isinstance(widget, (_IntSlider, _FloatSlider)):
            hint_label = QLabel(hint)
            hint_label.setWordWrap(True)
            hint_label.setStyleSheet("color:#94A3B8; font-size:10px;")
            holder = QWidget()
            vlay = QVBoxLayout(holder)
            vlay.setContentsMargins(0, 0, 0, 0)
            vlay.setSpacing(2)
            vlay.addWidget(widget)
            vlay.addWidget(hint_label)
            form.addRow(name_label, holder)
        else:
            form.addRow(name_label, widget)
        return widget

    def _combo(self, values: Iterable[str], value: Any) -> QComboBox:
        widget = QComboBox()
        widget.setMinimumHeight(28)
        widget.setStyleSheet(_FONT_VALUE)
        items = [str(item) for item in values]
        current = str(value if value is not None else "")
        if current and current not in items:
            items.append(current)
        widget.addItems(items)
        if current:
            widget.setCurrentText(current)
        return widget

    def _int_spin(self, value: Any, minimum: int, maximum: int, step: int = 1, unit: str = "") -> _IntSlider:
        return _IntSlider(value, minimum, maximum, step, unit, self)

    def _float_spin(
        self,
        value: Any,
        minimum: float,
        maximum: float,
        step: float = 0.1,
        decimals: int = 3,
        unit: str = "",
    ) -> _FloatSlider:
        return _FloatSlider(value, minimum, maximum, step, decimals, unit, self)

    def _check(self, value: Any, text: str) -> QCheckBox:
        widget = QCheckBox(text)
        widget.setChecked(bool(value))
        widget.setStyleSheet("font-size:12px; color:#0F172A; spacing:8px;")
        return widget

    def _line(self, value: Any, placeholder: str = "") -> QLineEdit:
        widget = QLineEdit(str(value if value is not None else ""))
        widget.setPlaceholderText(placeholder)
        widget.setMinimumHeight(28)
        widget.setStyleSheet(_FONT_VALUE)
        return widget

    def _json_editor(self, value: Any, placeholder: str = "") -> QPlainTextEdit:
        widget = QPlainTextEdit()
        widget.setMaximumHeight(96)
        widget.setMinimumHeight(56)
        widget.setPlaceholderText(placeholder)
        widget.setPlainText(_json_text(value))
        widget.setStyleSheet("font-size:11px; font-family:'Consolas','JetBrains Mono',monospace;")
        return widget

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(2, 2, 2, 2)
        root.setSpacing(10)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(6, 6, 6, 6)
        body_layout.setSpacing(12)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        cfg = self.cfg
        target = cfg.get("target", {})
        camera = cfg.get("camera", {})
        detector = cfg.get("detector", {})
        tracker = cfg.get("tracker", {})
        controller = cfg.get("controller", {})
        world = cfg.get("world", {})
        platform = cfg.get("platform", {})
        environment = cfg.get("environment", {})
        noise = cfg.get("noise", {})
        atmosphere = cfg.get("atmosphere", {})
        experiment = cfg.get("experiment", {})
        search = cfg.get("search", {})
        ai = cfg.get("ai", {})
        primary = cfg.get("primary_target", {})
        decoys = cfg.get("decoys", {})

        # ----- Presets and run -------------------------------------
        presets_form = self._group(
            body_layout,
            "1 · Presets & Run",
            "Only presets owned by this mode appear here. Benchmark P01–P12 files stay outside the GUI.",
        )
        self.preset_combo = QComboBox()
        self.preset_combo.setMinimumHeight(30)
        self.preset_combo.setStyleSheet("font-size:12px; font-weight:600;")
        self.preset_combo.addItems([info.display_name for info in self.presets] + ["Custom"])
        self._add(presets_form, "Preset", "preset", ("__preset__",), self.preset_combo,
                  "Load a curated starting point into this mode only.")
        self.preset_desc = QLabel("Select a preset and load it into this mode.")
        self.preset_desc.setWordWrap(True)
        self.preset_desc.setStyleSheet(_FONT_HINT)
        presets_form.addRow("", self.preset_desc)
        self.preset_expected = QLabel("")
        self.preset_expected.setWordWrap(True)
        self.preset_expected.setStyleSheet(
            "color:#0F172A; font-size:11px; background:#F1F5F9; padding:6px; border-radius:6px;"
        )
        self.preset_expected.hide()
        presets_form.addRow("", self.preset_expected)
        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.btn_load_preset = QPushButton("Load Preset")
        self.btn_save_preset = QPushButton("Save As…")
        self.btn_load_preset.setMinimumHeight(30)
        self.btn_save_preset.setMinimumHeight(30)
        buttons.addWidget(self.btn_load_preset)
        buttons.addWidget(self.btn_save_preset)
        buttons.addStretch()
        button_holder = QWidget()
        button_holder.setLayout(buttons)
        presets_form.addRow(button_holder)
        self._add(
            presets_form,
            "Random Seed",
            "experiment.seed",
            ("experiment", "seed"),
            self._int_spin(experiment.get("seed", 42), 0, 999999),
            "Scenario variation. Same seed replays the same run.",
        )
        self._add(
            presets_form,
            "Run Duration",
            "experiment.duration_s",
            ("experiment", "duration_s"),
            self._float_spin(experiment.get("duration_s", 30), 1, 600, 1, 1, "s"),
            "Length of one run in seconds.",
        )
        self.btn_load_preset.clicked.connect(self._request_load)
        self.btn_save_preset.clicked.connect(self.presetSaveRequested.emit)
        self.preset_combo.currentTextChanged.connect(self._on_preset_changed)

        # ----- Target and scene -------------------------------------
        target_form = self._group(
            body_layout,
            "2 · Target & Scene",
            "Private staged copy — never shared with the other mode.",
        )
        self._add(target_form, "Rendered Target Count", "target.count", ("target", "count"), self._int_spin(target.get("count", 1), 1, 5),
                  "How many beacon-like spots the scene renders (1 mandatory, multiple optional).")
        self._add(target_form, "Target Type", "target.type", ("target", "type"),
                  self._combo(["beacon_spot", "point", "extended", "custom"], target.get("type", "beacon_spot")))
        self._add(target_form, "Target Shape", "target.shape", ("target", "shape"), self._combo(["square", "circle", "gaussian", "cross", "user-defined"], target.get("shape", "square")))
        self._add(target_form, "Custom Polygon", "target.custom_polygon", ("target", "custom_polygon"),
                  self._json_editor(target.get("custom_polygon"), "[[x, y], [x, y], ...]"),
                  "Optional JSON polygon used when Target Shape is user-defined.")
        self._add(target_form, "Target Size", "target.size", ("target", "size"), self._int_spin(target.get("size", 10), 5, 20, 1, "px"),
                  "Apparent spot diameter in pixels (5–20).")
        self._add(target_form, "Target Intensity", "target.intensity", ("target", "intensity"), self._int_spin(target.get("intensity", 255), 0, 255),
                  "Peak rendered brightness 0–255.")
        self._add(target_form, "Start Position Mode", "target.initial_mode", ("target", "initial_mode"), self._combo(["random", "centre", "center", "user-defined"], target.get("initial_mode", "random")))
        self._add(target_form, "Start Position X", "target.initial_x", ("target", "initial_pos", 0), self._int_spin((target.get("initial_pos") or [1000, 1000])[0], 0, 4000, 10, "px"))
        self._add(target_form, "Start Position Y", "target.initial_y", ("target", "initial_pos", 1), self._int_spin((target.get("initial_pos") or [1000, 1000])[1], 0, 4000, 10, "px"))
        self._add(target_form, "Trajectory", "target.trajectory", ("target", "trajectory"), self._combo(["straight", "circular", "figure_eight", "random", "spiral", "sinusoidal", "user-defined"], target.get("trajectory", "circular")),
                  "Motion pattern — straight, circular, figure-8 and random required; spiral/sinusoidal optional.")
        self._add(target_form, "Custom Trajectory File", "target.custom_trajectory_file",
                  ("target", "custom_trajectory_file"),
                  self._line(target.get("custom_trajectory_file", ""), "path/to/trajectory.json"),
                  "Optional trajectory file used when Trajectory is user-defined.")
        self._add(target_form, "Target Speed", "target.speed_px_per_frame", ("target", "speed_px_per_frame"), self._float_spin(target.get("speed_px_per_frame", 2.8), 0, 20, 0.1, 2, "px/frame"),
                  "Physical speed limit feeds the identity motion check.")
        self._add(target_form, "Heading Angle (straight)", "target.angle_deg", ("target", "angle_deg"), self._float_spin(target.get("angle_deg", 30), 0, 360, 1, 1, "°"))
        self._add(target_form, "Orbit Radius (circular / figure-8)", "target.radius", ("target", "radius"), self._float_spin(target.get("radius", 180), 50, 800, 5, 1, "px"))

        # ----- Camera ------------------------------------------------
        camera_form = self._group(body_layout, "3 · Camera", "Sensor geometry and pan/tilt motion limits for this mode.")
        self._add(camera_form, "Sensor Type", "camera.type", ("camera", "type"), self._combo(["monochrome", "colour", "color"], camera.get("type", "monochrome")))
        self._add(camera_form, "Resolution Width", "camera.resolution.0", ("camera", "resolution", 0), self._int_spin((camera.get("resolution") or [640, 480])[0], 320, 1920, 10, "px"))
        self._add(camera_form, "Resolution Height", "camera.resolution.1", ("camera", "resolution", 1), self._int_spin((camera.get("resolution") or [640, 480])[1], 240, 1080, 10, "px"))
        self._add(camera_form, "Horizontal Field of View", "camera.fov_deg.0", ("camera", "fov_deg", 0), self._float_spin((camera.get("fov_deg") or [4, 3])[0], 1, 12, 0.1, 2, "°"))
        self._add(camera_form, "Vertical Field of View", "camera.fov_deg.1", ("camera", "fov_deg", 1), self._float_spin((camera.get("fov_deg") or [4, 3])[1], 1, 12, 0.1, 2, "°"))
        self._add(camera_form, "Frame Rate", "camera.fps", ("camera", "fps"), self._int_spin(camera.get("fps", 30), 30, 60, 1, "Hz"))
        self._add(camera_form, "Start Position", "camera.initial_position", ("camera", "initial_position"), self._combo(["centre", "center", "user-defined"], camera.get("initial_position", "centre")),
                  "Where the camera looks at run start (centre of the screen by default).")
        self._add(camera_form, "Initial Pan", "camera.initial_pan", ("camera", "initial_pan"),
                  self._float_spin(camera.get("initial_pan", 0), -180, 180, 0.5, 2, "°"))
        self._add(camera_form, "Initial Tilt", "camera.initial_tilt", ("camera", "initial_tilt"),
                  self._float_spin(camera.get("initial_tilt", 0), -90, 90, 0.5, 2, "°"))
        self._add(camera_form, "Max Pan Speed", "camera.max_pan_speed", ("camera", "max_pan_speed"), self._float_spin(camera.get("max_pan_speed", 5), 1, 15, 0.5, 2, "°/s"),
                  "Physical slew limit — search never exceeds it.")
        self._add(camera_form, "Max Tilt Speed", "camera.max_tilt_speed", ("camera", "max_tilt_speed"), self._float_spin(camera.get("max_tilt_speed", 5), 1, 15, 0.5, 2, "°/s"))
        self._add(camera_form, "Control Update Rate", "camera.update_interval_hz", ("camera", "update_interval_hz"), self._int_spin(camera.get("update_interval_hz", 30), 20, 60, 1, "Hz"))
        self._add(camera_form, "Camera Jitter", "camera.jitter_px", ("camera", "jitter_px"), self._float_spin(camera.get("jitter_px", 0), 0, 20, 0.5, 2, "px"),
                  "Random per-frame shake applied to the sensor.")
        self._add(camera_form, "Video Centre Offset X", "camera.video_centre_offset_x",
                  ("camera", "video_centre_offset_x"),
                  self._float_spin(camera.get("video_centre_offset_x", 0), -2000, 2000, 1, 1, "px"),
                  "Principal-point correction for external video; active only in VIDEO mode.")
        self._add(camera_form, "Video Centre Offset Y", "camera.video_centre_offset_y",
                  ("camera", "video_centre_offset_y"),
                  self._float_spin(camera.get("video_centre_offset_y", 0), -2000, 2000, 1, 1, "px"),
                  "Principal-point correction for external video; active only in VIDEO mode.")

        # ----- Detection ---------------------------------------------
        detection_form = self._group(body_layout, "4 · Detection", "Classical bright-spot stage. AI candidate settings live in section 8 (AI mode only).")
        self._add(detection_form, "Detection Threshold (k × σ)", "detector.threshold_k", ("detector", "threshold_k"), self._float_spin(detector.get("threshold_k", 3), 1.5, 8, 0.1, 2, "σ"),
                  "Pixels brighter than median + k·noise become candidates.")
        self._add(detection_form, "Minimum Blob Area", "detector.min_area", ("detector", "min_area"), self._int_spin(detector.get("min_area", 8), 2, 200, 1, "px²"))
        self._add(detection_form, "Maximum Blob Area", "detector.max_area", ("detector", "max_area"), self._int_spin(detector.get("max_area", 900), 20, 5000, 10, "px²"),
                  "Ignore blobs larger than this (clutter rejection).")
        self._add(detection_form, "Blur Kernel Size", "detector.blur_ksize", ("detector", "blur_ksize"),
                  self._int_spin(detector.get("blur_ksize", 3), 1, 31, 2, "px"),
                  "Odd-sized smoothing kernel applied before thresholding.")

        # ----- Search and tracker ------------------------------------
        search_form = self._group(body_layout, "5 · Search & Tracker", "Recovery behaviour and EKF/IMM estimator tuning for this mode.")
        self._add(search_form, "Search Pattern", "search.mode", ("search", "mode"), self._combo(["spiral", "raster", "hybrid"], search.get("mode", "spiral")))
        self._add(search_form, "Search ROI Size", "search.roi_size", ("search", "roi_size"), self._int_spin(search.get("roi_size", 160), 40, 800, 10, "px"),
                  "Local recovery window around the predicted position.")
        self._add(search_form, "Local Recovery Timeout", "tracker.lost_timeout_frames", ("tracker", "lost_timeout_frames"), self._int_spin(tracker.get("lost_timeout_frames", 15), 1, 100, 1, "frames"))
        self._add(search_form, "Global Re-acquisition Timeout", "tracker.reacq_timeout_frames", ("tracker", "reacq_timeout_frames"), self._int_spin(tracker.get("reacq_timeout_frames", 30), 1, 300, 1, "frames"),
                  "Keep short — spec requires re-acquisition ≤ 1 s.")
        self._add(search_form, "EKF Process Noise", "tracker.process_noise", ("tracker", "process_noise"), self._float_spin(tracker.get("process_noise", 0.8), 0, 20, 0.1, 3),
                  "Higher trusts the model less during manoeuvres.")
        self._add(search_form, "EKF Measurement Noise", "tracker.meas_noise", ("tracker", "meas_noise"), self._float_spin(tracker.get("meas_noise", 4), 0.1, 50, 0.1, 3, "px"))
        self._add(search_form, "Association Gate", "tracker.gate_sigma", ("tracker", "gate_sigma"), self._float_spin(tracker.get("gate_sigma", 5), 0.5, 30, 0.5, 2, "σ"))

        # ----- Estimator and controller ------------------------------
        control_form = self._group(body_layout, "6 · Controller (PID)", "Pan/tilt servo gains and safety limits.")
        self._add(control_form, "Proportional Gain — Pan", "controller.kp_pan", ("controller", "kp_pan"), self._float_spin(controller.get("kp_pan", 1.2), 0, 20, 0.1, 3))
        self._add(control_form, "Proportional Gain — Tilt", "controller.kp_tilt", ("controller", "kp_tilt"), self._float_spin(controller.get("kp_tilt", 1.2), 0, 20, 0.1, 3))
        self._add(control_form, "Integral Gain", "controller.ki", ("controller", "ki"), self._float_spin(controller.get("ki", 0.05), 0, 10, 0.01, 3),
                  "Reset automatically on target loss.")
        self._add(control_form, "Derivative Gain", "controller.kd", ("controller", "kd"), self._float_spin(controller.get("kd", 0.15), 0, 10, 0.01, 3))
        self._add(control_form, "Dead Zone", "controller.deadzone_px", ("controller", "deadzone_px"), self._float_spin(controller.get("deadzone_px", 2), 0, 50, 0.5, 2, "px"),
                  "Errors inside this zone command zero rate.")
        self._add(control_form, "Integral Limit", "controller.integral_limit", ("controller", "integral_limit"), self._float_spin(controller.get("integral_limit", 8), 0, 100, 0.5, 2),
                  "Anti-windup cap on the integral term.")

        # ----- Environment and disturbances --------------------------
        env_form = self._group(body_layout, "7 · World & Platform", "Scene size and platform motion (per requirements §Camera/Target/Platform).")
        self._add(env_form, "World Width", "world.width", ("world", "width"), self._int_spin(world.get("width", 2000), 2000, 4000, 50, "px"))
        self._add(env_form, "World Height", "world.height", ("world", "height"), self._int_spin(world.get("height", 2000), 2000, 4000, 50, "px"))
        self._add(env_form, "Background Level", "world.background", ("world", "background"), self._int_spin(world.get("background", 18), 0, 79))
        self._add(env_form, "Platform Motion", "platform.type", ("platform", "type"), self._combo(["none", "linear", "circular", "random", "spiral", "figure_of_8"], platform.get("type", "none")),
                  "Linear is mandatory; circular/random/spiral/figure-8 optional.")
        self._add(env_form, "Platform Speed", "platform.speed_px_per_frame", ("platform", "speed_px_per_frame"), self._float_spin(platform.get("speed_px_per_frame", 0), 0, 20, 0.5, 2, "px/frame"),
                  "Platform drift up to ±20 px/frame.")
        self._add(env_form, "Gradient Enabled", "environment.gradient_enabled",
                  ("environment", "gradient_enabled"),
                  self._check(environment.get("gradient_enabled", False), "Enable background gradient"))
        self._add(env_form, "Gradient Type", "environment.gradient_type",
                  ("environment", "gradient_type"),
                  self._combo(["linear", "radial"], environment.get("gradient_type", "linear")))
        self._add(env_form, "Gradient Top", "environment.gradient_top",
                  ("environment", "gradient_top"),
                  self._int_spin(environment.get("gradient_top", 12), 0, 255))
        self._add(env_form, "Gradient Bottom", "environment.gradient_bottom",
                  ("environment", "gradient_bottom"),
                  self._int_spin(environment.get("gradient_bottom", 24), 0, 255))
        self._add(env_form, "Gradient Angle", "environment.gradient_angle",
                  ("environment", "gradient_angle"),
                  self._float_spin(environment.get("gradient_angle", 90), 0, 360, 1, 1, "°"))
        self._add(env_form, "Stars Enabled", "environment.stars_enabled",
                  ("environment", "stars_enabled"),
                  self._check(environment.get("stars_enabled", False), "Render background stars"))
        self._add(env_form, "Star Density", "environment.stars_density",
                  ("environment", "stars_density"),
                  self._float_spin(environment.get("stars_density", 0.0), 0, 1, 0.001, 4))
        self._add(env_form, "Star Brightness", "environment.stars_brightness",
                  ("environment", "stars_brightness"),
                  self._int_spin(environment.get("stars_brightness", 0), 0, 255))
        self._add(env_form, "Star Min Magnitude", "environment.stars_min_mag",
                  ("environment", "stars_min_mag"),
                  self._float_spin(environment.get("stars_min_mag", 0), -10, 20, 0.1, 1))
        self._add(env_form, "Star Max Magnitude", "environment.stars_max_mag",
                  ("environment", "stars_max_mag"),
                  self._float_spin(environment.get("stars_max_mag", 10), -10, 20, 0.1, 1))
        self._add(env_form, "Star Twinkle", "environment.stars_twinkle",
                  ("environment", "stars_twinkle"),
                  self._check(environment.get("stars_twinkle", False), "Animate star intensity"))
        self._add(env_form, "Star Seed", "environment.stars_seed",
                  ("environment", "stars_seed"),
                  self._int_spin(environment.get("stars_seed", 42), 0, 999999))
        self._add(env_form, "Vignetting Enabled", "environment.vignetting_enabled",
                  ("environment", "vignetting_enabled"),
                  self._check(environment.get("vignetting_enabled", False), "Darken image edges"))
        self._add(env_form, "Vignetting Strength", "environment.vignetting_strength",
                  ("environment", "vignetting_strength"),
                  self._float_spin(environment.get("vignetting_strength", 0.0), 0, 1, 0.01, 2))
        self._add(env_form, "Vignetting Radius", "environment.vignetting_radius",
                  ("environment", "vignetting_radius"),
                  self._float_spin(environment.get("vignetting_radius", 0.8), 0, 2, 0.01, 2))
        self._add(env_form, "Vignetting Falloff", "environment.vignetting_falloff",
                  ("environment", "vignetting_falloff"),
                  self._float_spin(environment.get("vignetting_falloff", 2.0), 0.1, 10, 0.1, 2))
        self._add(env_form, "Vignetting Centre X", "environment.vignetting_center_x",
                  ("environment", "vignetting_center_x"),
                  self._float_spin(environment.get("vignetting_center_x", 0), -1, 1, 0.01, 2))
        self._add(env_form, "Vignetting Centre Y", "environment.vignetting_center_y",
                  ("environment", "vignetting_center_y"),
                  self._float_spin(environment.get("vignetting_center_y", 0), -1, 1, 0.01, 2))
        self._add(env_form, "Brightness Gain", "environment.brightness_gain",
                  ("environment", "brightness_gain"),
                  self._float_spin(environment.get("brightness_gain", 1.0), 0, 4, 0.01, 2, "×"))
        self._add(env_form, "Brightness Offset", "environment.brightness_offset",
                  ("environment", "brightness_offset"),
                  self._int_spin(environment.get("brightness_offset", 0), -255, 255))

        disturb_form = self._group(body_layout, "7b · Image Noise & Atmosphere", "Sensor noise and weather for this mode.")
        self._add(disturb_form, "Gaussian Noise", "noise.gaussian_enabled", ("noise", "gaussian_enabled"), self._check(noise.get("gaussian_enabled", False), "Enable Gaussian sensor noise"))
        self._add(disturb_form, "Gaussian Std-dev", "noise.gaussian_std", ("noise", "gaussian_std"), self._float_spin(noise.get("gaussian_std", 0), 0, 100, 0.5, 2, "px"))
        self._add(disturb_form, "Salt & Pepper Noise", "noise.salt_pepper_enabled", ("noise", "salt_pepper_enabled"), self._check(noise.get("salt_pepper_enabled", False), "Enable impulse noise"))
        self._add(disturb_form, "Impulse Probability", "noise.salt_pepper_prob", ("noise", "salt_pepper_prob"), self._float_spin(noise.get("salt_pepper_prob", 0), 0, 0.5, 0.005, 4))
        self._add(disturb_form, "Photon (Poisson) Noise", "noise.poisson", ("noise", "poisson"), self._check(noise.get("poisson", False), "Enable shot noise"))
        self._add(disturb_form, "Atmosphere", "atmosphere.type", ("atmosphere", "type"), self._combo(["clear", "haze", "fog", "rain", "low_light"], atmosphere.get("type", "clear")))
        self._add(disturb_form, "Atmosphere Strength", "atmosphere.strength", ("atmosphere", "strength"), self._float_spin(atmosphere.get("strength", 0), 0, 1, 0.05, 3))

        # ----- Input and video ---------------------------------------
        input_form = self._group(body_layout, "8 · Input Source", "Synthetic scene or external video for this mode.")
        self._add(input_form, "Input Mode", "experiment.input_mode", ("experiment", "input_mode"), self._combo(["SYNTHETIC", "VIDEO"], experiment.get("input_mode", "SYNTHETIC")))
        self._add(input_form, "Video File", "experiment.video_path", ("experiment", "video_path"), self._line(experiment.get("video_path", ""), "data/input_videos/benchmark.mp4"),
                  "External .mp4 @30 fps covering the full screen (Benchmark Performance-2).")
        self._add(input_form, "Bypass Virtual PTZ", "experiment.bypass_virtual_ptz", ("experiment", "bypass_virtual_ptz"), self._check(experiment.get("bypass_virtual_ptz", False), "Measurement-only mode for video benchmarks"))

        # ----- AI-only controls --------------------------------------
        if self.is_ai_panel:
            self._build_ai_controls(body_layout, ai, primary, decoys, search)

        # Direct names retained for integrations and tests.
        self.seed_spin = self.controls["experiment.seed"][1]
        self.duration_spin = self.controls["experiment.duration_s"][1]
        self.tgt_count_spin = self.controls["target.count"][1]
        self.tgt_shape_combo = self.controls["target.shape"][1]
        self.size_spin = self.controls["target.size"][1]
        self.tgt_type_combo = self.controls["target.type"][1]
        self.tgt_init_mode_combo = self.controls["target.initial_mode"][1]
        self.tgt_init_x_spin = self.controls["target.initial_x"][1]
        self.tgt_init_y_spin = self.controls["target.initial_y"][1]
        self.custom_polygon_edit = self.controls["target.custom_polygon"][1]
        self.custom_traj_edit = self.controls["target.custom_trajectory_file"][1]
        self.traj_combo = self.controls["target.trajectory"][1]
        self.speed_spin = self.controls["target.speed_px_per_frame"][1]
        self.angle_spin = self.controls["target.angle_deg"][1]
        self.radius_spin = self.controls["target.radius"][1]
        self.jitter_spin = self.controls["camera.jitter_px"][1]
        self.gauss_spin = self.controls["noise.gaussian_std"][1]
        self.spp_spin = self.controls["noise.salt_pepper_prob"][1]
        self.atmo_combo = self.controls["atmosphere.type"][1]
        self.atmo_strength = self.controls["atmosphere.strength"][1]
        self.kp_pan_spin = self.controls["controller.kp_pan"][1]
        self.kp_tilt_spin = self.controls["controller.kp_tilt"][1]
        self.ki_spin = self.controls["controller.ki"][1]
        self.kd_spin = self.controls["controller.kd"][1]
        self.dead_spin = self.controls["controller.deadzone_px"][1]
        self.proc_spin = self.controls["tracker.process_noise"][1]
        self.meas_spin = self.controls["tracker.meas_noise"][1]
        self.input_combo = self.controls["experiment.input_mode"][1]
        self.video_path_edit = self.controls["experiment.video_path"][1]
        self.vid_centre_x_spin = self.controls["camera.video_centre_offset_x"][1]
        self.vid_centre_y_spin = self.controls["camera.video_centre_offset_y"][1]
        self.det_thr_spin = self.controls["detector.threshold_k"][1]
        self.det_min_spin = self.controls["detector.min_area"][1]
        self.det_max_spin = self.controls["detector.max_area"][1]
        self.det_blur_spin = self.controls["detector.blur_ksize"][1]
        self.search_local_spin = self.controls["tracker.lost_timeout_frames"][1]
        self.search_spiral_spin = self.controls["tracker.reacq_timeout_frames"][1]
        self.search_roi_spin = self.controls["search.roi_size"][1]
        self.cam_type_combo = self.controls["camera.type"][1]
        self.res_w_spin = self.controls["camera.resolution.0"][1]
        self.res_h_spin = self.controls["camera.resolution.1"][1]
        self.fov_h_spin = self.controls["camera.fov_deg.0"][1]
        self.fov_v_spin = self.controls["camera.fov_deg.1"][1]
        self.fps_spin = self.controls["camera.fps"][1]
        self.cam_init_combo = self.controls["camera.initial_position"][1]
        self.cam_init_pan_spin = self.controls["camera.initial_pan"][1]
        self.cam_init_tilt_spin = self.controls["camera.initial_tilt"][1]
        self.max_pan_spin = self.controls["camera.max_pan_speed"][1]
        self.max_tilt_spin = self.controls["camera.max_tilt_speed"][1]
        self.update_hz_spin = self.controls["camera.update_interval_hz"][1]
        self.world_w_spin = self.controls["world.width"][1]
        self.world_h_spin = self.controls["world.height"][1]
        self.world_bg_spin = self.controls["world.background"][1]
        self.platform_combo = self.controls["platform.type"][1]
        self.platform_speed_spin = self.controls["platform.speed_px_per_frame"][1]
        self.grad_enabled = self.controls["environment.gradient_enabled"][1]
        self.grad_type_combo = self.controls["environment.gradient_type"][1]
        self.grad_top_spin = self.controls["environment.gradient_top"][1]
        self.grad_bottom_spin = self.controls["environment.gradient_bottom"][1]
        self.grad_angle_spin = self.controls["environment.gradient_angle"][1]
        self.stars_enabled = self.controls["environment.stars_enabled"][1]
        self.stars_density_spin = self.controls["environment.stars_density"][1]
        self.stars_brightness_spin = self.controls["environment.stars_brightness"][1]
        self.stars_minmag_spin = self.controls["environment.stars_min_mag"][1]
        self.stars_maxmag_spin = self.controls["environment.stars_max_mag"][1]
        self.stars_twinkle_check = self.controls["environment.stars_twinkle"][1]
        self.stars_seed_spin = self.controls["environment.stars_seed"][1]
        self.vig_enabled = self.controls["environment.vignetting_enabled"][1]
        self.vig_strength_spin = self.controls["environment.vignetting_strength"][1]
        self.vig_radius_spin = self.controls["environment.vignetting_radius"][1]
        self.vig_falloff_spin = self.controls["environment.vignetting_falloff"][1]
        self.vig_cx_spin = self.controls["environment.vignetting_center_x"][1]
        self.vig_cy_spin = self.controls["environment.vignetting_center_y"][1]
        self.bright_gain_spin = self.controls["environment.brightness_gain"][1]
        self.bright_offset_spin = self.controls["environment.brightness_offset"][1]
        self.gauss_check = self.controls["noise.gaussian_enabled"][1]
        self.spp_check = self.controls["noise.salt_pepper_enabled"][1]
        self.poisson_check = self.controls["noise.poisson"][1]
        if self.is_ai_panel:
            self.ai_enabled_check = self.controls["ai.enabled"][1]
            self.primary_thr_spin = self.controls["ai.thresholds.primary_threshold"][1]
            self.decoy_thr_spin = self.controls["ai.thresholds.decoy_threshold"][1]
            self.confirm_spin = self.controls["ai.thresholds.confirmation_frames"][1]
            self.blink_edit = self.controls["ai.signatures.blink_pattern"][1]
            self.freq_spin = self.controls["ai.signatures.modulation_freq_hz"][1]
            self.freq_tol_spin = self.controls["ai.signatures.freq_tolerance"][1]
            self.sig_enabled_check = self.controls["ai.signatures.enabled"][1]
            self.candidate_model_edit = self.controls["ai.candidate_model_path"][1]
            self.identity_model_edit = self.controls["ai.identity_model_path"][1]
            self.det_conf_spin = self.controls["ai.detection_threshold"][1]
            self.det_model_edit = self.controls["ai.candidate_model_path"][1]
            self.search_ai_check = self.controls["ai.search_ranking"][1]
            self.w_app_spin = self.controls["ai.weights.appearance"][1]
            self.w_motion_spin = self.controls["ai.weights.motion"][1]
            self.w_temporal_spin = self.controls["ai.weights.temporal"][1]
            self.w_sig_spin = self.controls["ai.weights.signature"][1]
            self.w_est_spin = self.controls["ai.weights.estimator"][1]
        self._on_conditional_changed()

    def _build_ai_controls(
        self,
        body_layout: QVBoxLayout,
        ai: Mapping[str, Any],
        primary: Mapping[str, Any],
        decoys: Mapping[str, Any],
        search: Mapping[str, Any],
    ) -> None:
        thresholds = ai.get("thresholds", {}) if isinstance(ai, Mapping) else {}
        signatures = ai.get("signatures", ai.get("signature", {})) if isinstance(ai, Mapping) else {}
        weights = ai.get("weights", {}) if isinstance(ai, Mapping) else {}
        optical = primary.get("optical_signature", {}) if isinstance(primary, Mapping) else {}
        profiles = decoys.get("profiles", []) if isinstance(decoys, Mapping) else []

        runtime = self._group(
            body_layout,
            "8 · AI Runtime",
            "Model paths, patch/sequence geometry and inference budget. Empty model path = safe heuristic fallback.",
        )
        self._add(runtime, "AI Identification Enabled", "ai.enabled", ("ai", "enabled"), self._check(ai.get("enabled", True), "Master switch for this mode"))
        self._add(runtime, "Fallback on AI Failure", "ai.fallback_on_failure", ("ai", "fallback_on_failure"), self._check(ai.get("fallback_on_failure", True), "Raise uncertainty and hold search instead of locking blindly"))
        self._add(runtime, "Track History Length", "ai.sequence_length", ("ai", "sequence_length"), self._int_spin(ai.get("sequence_length", 25), 10, 100, 1, "frames"),
                  "Observations per track fed to the GRU (20–30 recommended).")
        self._add(runtime, "Inference Timeout", "ai.inference_timeout_ms", ("ai", "inference_timeout_ms"), self._int_spin(ai.get("inference_timeout_ms", 40), 1, 5000, 5, "ms"),
                  "Hard budget per classifier before fallback.")
        self._add(runtime, "Candidate Model File", "ai.candidate_model_path", ("ai", "candidate_model_path"), self._line(ai.get("candidate_model_path", ""), "models/candidate_classifier/best.onnx (empty = heuristic)"))
        self._add(runtime, "Identity Model File", "ai.identity_model_path", ("ai", "identity_model_path"), self._line(ai.get("identity_model_path", ""), "models/identity_classifier/best.onnx (empty = heuristic voter)"))

        ident = self._group(
            body_layout,
            "9 · Identity Decision",
            "A track becomes PRIMARY only after holding above threshold for N consecutive frames.",
        )
        self._add(ident, "Primary Confidence Threshold", "ai.thresholds.primary_threshold", ("ai", "thresholds", "primary_threshold"), self._float_spin(thresholds.get("primary_threshold", 0.85), 0.5, 0.999, 0.01, 3),
                  "Identity score needed to start confirmation (default 0.85).")
        self._add(ident, "Decoy Rejection Threshold", "ai.thresholds.decoy_threshold", ("ai", "thresholds", "decoy_threshold"), self._float_spin(thresholds.get("decoy_threshold", 0.85), 0.5, 0.999, 0.01, 3),
                  "Decoy score that rejects a track (default 0.85).")
        self._add(ident, "Confirmation Frames", "ai.thresholds.confirmation_frames", ("ai", "thresholds", "confirmation_frames"), self._int_spin(thresholds.get("confirmation_frames", 5), 1, 30, 1, "frames"),
                  "Consecutive frames above threshold before PRIMARY_CONFIRMED. Higher = fewer false locks, slower acquisition.")
        self._add(ident, "Unknown Band — Low", "ai.thresholds.unknown_low", ("ai", "thresholds", "unknown_low"), self._float_spin(thresholds.get("unknown_low", 0.45), 0, 1, 0.01, 3),
                  "Below this with no strong class = UNKNOWN.")
        self._add(ident, "Unknown Band — High", "ai.thresholds.unknown_high", ("ai", "thresholds", "unknown_high"), self._float_spin(thresholds.get("unknown_high", 0.85), 0, 1, 0.01, 3))
        self._add(ident, "Detection Confidence Cutoff", "ai.detection_threshold", ("ai", "detection_threshold"), self._float_spin(ai.get("detection_threshold", 0.45), 0, 1, 0.01, 3),
                  "Stage-1 scores below this are treated as noise.")
        self._add(ident, "AI Search Ranking", "ai.search_ranking", ("ai", "search_ranking"), self._check(ai.get("search_ranking", True), "Rank search regions by prediction, velocity, decoy memory and disturbances"))

        sig = self._group(
            body_layout,
            "10 · Optical Signature",
            "The unique observable identity. Brightness alone never confirms a target.",
        )
        self._add(sig, "Signature Check Enabled", "ai.signatures.enabled", ("ai", "signatures", "enabled"), self._check(signatures.get("enabled", True), "Master switch for coded identity"))
        self._add(sig, "Blink Code", "ai.signatures.blink_pattern", ("ai", "signatures", "blink_pattern"), self._line(signatures.get("blink_pattern", "10110010"), "10110010"),
                  "Primary on/off code per frame; decoys use a different code.")
        self._add(sig, "Modulation Frequency", "ai.signatures.modulation_freq_hz", ("ai", "signatures", "modulation_freq_hz"), self._float_spin(signatures.get("modulation_freq_hz", 12), 0.1, 240, 0.1, 2, "Hz"))
        self._add(sig, "Frequency Tolerance", "ai.signatures.freq_tolerance", ("ai", "signatures", "freq_tolerance"), self._float_spin(signatures.get("freq_tolerance", 0.05), 0.001, 1, 0.005, 4, "±"),
                  "Allowed fractional error around the modulation frequency.")
        self._add(sig, "Expected Size — Min", "ai.signatures.size_range_px.0", ("ai", "signatures", "size_range_px", 0), self._int_spin((signatures.get("size_range_px") or [5, 20])[0], 1, 100, 1, "px"))
        self._add(sig, "Expected Size — Max", "ai.signatures.size_range_px.1", ("ai", "signatures", "size_range_px", 1), self._int_spin((signatures.get("size_range_px") or [5, 20])[1], 1, 100, 1, "px"))
        self._add(sig, "Persistence Required", "ai.signatures.persistence_frames", ("ai", "signatures", "persistence_frames"), self._int_spin(signatures.get("persistence_frames", 5), 1, 100, 1, "frames"),
                  "Frames a candidate must remain visible to count as stable.")

        weights_form = self._group(
            body_layout,
            "11 · Identity Evidence Weights",
            "How the five evidence streams combine. Must sum to 1.00.",
        )
        self._add(weights_form, "Appearance Weight", "ai.weights.appearance", ("ai", "weights", "appearance"), self._float_spin(weights.get("appearance", 0.2), 0, 1, 0.01, 3))
        self._add(weights_form, "Motion Weight", "ai.weights.motion", ("ai", "weights", "motion"), self._float_spin(weights.get("motion", 0.2), 0, 1, 0.01, 3))
        self._add(weights_form, "Temporal Weight", "ai.weights.temporal", ("ai", "weights", "temporal"), self._float_spin(weights.get("temporal", 0.2), 0, 1, 0.01, 3))
        self._add(weights_form, "Signature Weight", "ai.weights.signature", ("ai", "weights", "signature"), self._float_spin(weights.get("signature", 0.25), 0, 1, 0.01, 3))
        self._add(weights_form, "Estimator Weight", "ai.weights.estimator", ("ai", "weights", "estimator"), self._float_spin(weights.get("estimator", 0.15), 0, 1, 0.01, 3))

        primary_form = self._group(
            body_layout,
            "12 · Decoys",
            "Decoy candidates the AI must reject (wrong blink code / frequency).",
        )
        self._add(primary_form, "Render Decoys", "decoys.enabled", ("decoys", "enabled"), self._check(decoys.get("enabled", True), "Show decoy candidates in the scene"))
        self._add(primary_form, "Decoy Count", "decoys.count", ("decoys", "count"), self._int_spin(decoys.get("count", 2), 0, 8),
                  "Number of simultaneous decoys.")

    # ------------------------------------------------------------------
    # Config <-> widgets
    # ------------------------------------------------------------------
    @staticmethod
    def _widget_value(widget: QWidget) -> Any:
        if isinstance(widget, (_IntSlider, _FloatSlider)):
            return widget.value()
        if isinstance(widget, QCheckBox):
            return widget.isChecked()
        if isinstance(widget, QComboBox):
            return widget.currentText()
        if isinstance(widget, QSpinBox):
            return int(widget.value())
        if isinstance(widget, QDoubleSpinBox):
            return float(widget.value())
        if isinstance(widget, QPlainTextEdit):
            return widget.toPlainText()
        if isinstance(widget, QLineEdit):
            return widget.text()
        return None

    def _on_conditional_changed(self) -> None:
        """Enable only controls that are meaningful for the current choices."""
        def set_enabled(name: str, enabled: bool) -> None:
            entry = self.controls.get(name)
            if entry is not None:
                entry[1].setEnabled(bool(enabled))

        def checked(name: str, default: bool = False) -> bool:
            entry = self.controls.get(name)
            if entry is None:
                return default
            widget = entry[1]
            return bool(widget.isChecked()) if isinstance(widget, QCheckBox) else default

        def current(name: str, default: str = "") -> str:
            entry = self.controls.get(name)
            if entry is None:
                return default
            widget = entry[1]
            return widget.currentText() if isinstance(widget, QComboBox) else default

        input_mode = current("experiment.input_mode", "SYNTHETIC")
        video_mode = input_mode.upper() == "VIDEO"
        set_enabled("experiment.video_path", video_mode)
        set_enabled("experiment.bypass_virtual_ptz", video_mode)
        set_enabled("camera.video_centre_offset_x", video_mode)
        set_enabled("camera.video_centre_offset_y", video_mode)

        shape = current("target.shape", "square")
        trajectory = current("target.trajectory", "circular")
        initial_mode = current("target.initial_mode", "random")
        set_enabled("target.custom_polygon", shape == "user-defined")
        set_enabled("target.custom_trajectory_file", trajectory == "user-defined")
        set_enabled("target.initial_x", initial_mode not in {"random", "centre", "center"})
        set_enabled("target.initial_y", initial_mode not in {"random", "centre", "center"})
        set_enabled("target.angle_deg", trajectory in {"straight", "user-defined"})
        set_enabled("target.radius", trajectory in {"circular", "figure_eight"})

        gaussian_on = checked("noise.gaussian_enabled")
        salt_pepper_on = checked("noise.salt_pepper_enabled")
        set_enabled("noise.gaussian_std", gaussian_on)
        set_enabled("noise.salt_pepper_prob", salt_pepper_on)

        gradient_on = checked("environment.gradient_enabled")
        for name in (
            "environment.gradient_type",
            "environment.gradient_top",
            "environment.gradient_bottom",
            "environment.gradient_angle",
        ):
            set_enabled(name, gradient_on)

        stars_on = checked("environment.stars_enabled")
        for name in (
            "environment.stars_density",
            "environment.stars_brightness",
            "environment.stars_min_mag",
            "environment.stars_max_mag",
            "environment.stars_twinkle",
            "environment.stars_seed",
        ):
            set_enabled(name, stars_on)

        vignette_on = checked("environment.vignetting_enabled")
        for name in (
            "environment.vignetting_strength",
            "environment.vignetting_radius",
            "environment.vignetting_falloff",
            "environment.vignetting_center_x",
            "environment.vignetting_center_y",
        ):
            set_enabled(name, vignette_on)

        if self.is_ai_panel:
            ai_on = checked("ai.enabled", True)
            signature_on = ai_on and checked("ai.signatures.enabled", True)
            for name in (
                "ai.fallback_on_failure",
                "ai.sequence_length",
                "ai.inference_timeout_ms",
                "ai.candidate_model_path",
                "ai.identity_model_path",
                "ai.thresholds.primary_threshold",
                "ai.thresholds.decoy_threshold",
                "ai.thresholds.confirmation_frames",
                "ai.thresholds.unknown_low",
                "ai.thresholds.unknown_high",
                "ai.detection_threshold",
                "ai.search_ranking",
                "ai.signatures.enabled",
                "ai.weights.appearance",
                "ai.weights.motion",
                "ai.weights.temporal",
                "ai.weights.signature",
                "ai.weights.estimator",
                "decoys.enabled",
                "decoys.count",
            ):
                set_enabled(name, ai_on)
            for name in (
                "ai.signatures.blink_pattern",
                "ai.signatures.modulation_freq_hz",
                "ai.signatures.freq_tolerance",
                "ai.signatures.size_range_px.0",
                "ai.signatures.size_range_px.1",
                "ai.signatures.persistence_frames",
            ):
                set_enabled(name, signature_on)

    def set_config(self, config: Dict[str, Any]) -> None:
        self.cfg = copy.deepcopy(config)
        for _name, (path, widget) in self.controls.items():
            if path == ("__preset__",):
                continue
            value = _get_path(self.cfg, path, None)
            if isinstance(widget, (_IntSlider, _FloatSlider)):
                if value is not None:
                    widget.setValue(value)
            elif isinstance(widget, QComboBox):
                if value is not None:
                    text = str(value)
                    if widget.findText(text) < 0:
                        widget.addItem(text)
                    widget.setCurrentText(text)
            elif isinstance(widget, QCheckBox):
                widget.setChecked(bool(value))
            elif isinstance(widget, QSpinBox):
                widget.setValue(int(round(float(value if value is not None else 0))))
            elif isinstance(widget, QDoubleSpinBox):
                widget.setValue(float(value if value is not None else 0.0))
            elif isinstance(widget, QPlainTextEdit):
                widget.setPlainText(_json_text(value))
            elif isinstance(widget, QLineEdit):
                widget.setText(str(value if value is not None else ""))
        self._on_conditional_changed()

    def collect_config(self) -> Dict[str, Any]:
        result = copy.deepcopy(self.cfg)
        for name, (path, widget) in self.controls.items():
            if path == ("__preset__",):
                continue
            value = self._widget_value(widget)
            if isinstance(widget, QPlainTextEdit):
                value = _parse_json(value, name)
            elif isinstance(widget, QLineEdit) and value == "" and name in {
                "target.custom_trajectory_file",
                "experiment.video_path",
                "ai.candidate_model_path",
                "ai.identity_model_path",
            }:
                value = None
            _set_path(result, path, value)

        mode = _get_path(result, ("target", "initial_mode"), "random")
        if mode in {"random"}:
            _set_path(result, ("target", "initial_pos"), None)
        elif mode in {"centre", "center"}:
            _set_path(
                result,
                ("target", "initial_pos"),
                [int(result["world"]["width"] // 2), int(result["world"]["height"] // 2)],
            )
        else:
            _set_path(
                result,
                ("target", "initial_pos"),
                [int(_get_path(result, ("target", "initial_pos", 0), 0)), int(_get_path(result, ("target", "initial_pos", 1), 0))],
            )

        if self.is_ai_panel:
            ai_enabled = bool(_get_path(result, ("ai", "enabled"), False))
            _set_path(result, ("ai", "enabled"), ai_enabled)
            ai_sig = _get_path(result, ("ai", "signatures"), {}) or {}
            _set_path(result, ("primary_target", "optical_signature"), copy.deepcopy(ai_sig))
            decoy_count = int(_get_path(result, ("decoys", "count"), 0) or 0)
            _set_path(result, ("decoys", "enabled"), decoy_count > 0 and bool(_get_path(result, ("decoys", "enabled"), True)))
        else:
            _set_path(result, ("ai", "enabled"), False)

        from ..config.schema import validate_config
        return validate_config(result)

    def set_preset(self, info: Optional[PresetInfo]) -> None:
        self._current_preset = info
        if info is None:
            self.preset_combo.setCurrentText("Custom")
        else:
            self.preset_combo.setCurrentText(info.display_name)

    def _on_preset_changed(self, name: str) -> None:
        info = self.preset_infos.get(name)
        if info is None:
            self.preset_desc.setText("Custom: edit this mode independently, then use Save As.")
            self.preset_expected.hide()
            return
        mode = "AI ON" if info.is_ai_preset else "AI OFF"
        self.preset_desc.setText(f"{mode} · {info.purpose}")
        if info.expected:
            self.preset_expected.setText(
                "Expected: " + ", ".join(f"{key}: {value}" for key, value in info.expected.items())
            )
            self.preset_expected.show()
        else:
            self.preset_expected.hide()

    def _request_load(self) -> None:
        info = self.preset_infos.get(self.preset_combo.currentText())
        if info is not None:
            self.presetLoadRequested.emit(info)

    def load_preset(self, info: PresetInfo) -> Dict[str, Any]:
        from ..config.loader import load_config
        loaded = load_config(str(info.path))
        loaded = copy.deepcopy(loaded)
        if self.is_ai_panel:
            loaded.setdefault("ai", {})["enabled"] = True
        else:
            loaded.setdefault("ai", {})["enabled"] = False
            loaded.setdefault("decoys", {})["enabled"] = False
        self.set_config(loaded)
        self.set_preset(info)
        self.cfg = copy.deepcopy(loaded)
        return loaded

    def current_preset(self) -> Optional[PresetInfo]:
        return self._current_preset

    def set_ai_enabled(self, enabled: bool) -> None:
        if self.is_ai_panel:
            widget = self.ai_enabled_check
            if isinstance(widget, (_IntSlider, _FloatSlider)):
                return
            if isinstance(widget, QCheckBox):
                widget.setChecked(bool(enabled))


__all__ = ["SystemControlPanel"]
