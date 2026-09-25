"""Independent parameter panels for the two Control Deck systems.

The simulator has two intentionally different control surfaces:

* ``ai`` controls the identity/candidate/decoy pipeline and its own staged
  copy of the scene parameters;
* ``deterministic`` controls the original detector -> EKF-IMM -> PID path.

Each :class:`SystemControlPanel` owns a complete configuration copy and its
widgets.  Switching portions therefore never copies values from one system
into the other; only the panel that is active when Apply is pressed is sent
to the simulator.
"""
from __future__ import annotations

import copy
import json
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence, Tuple

from PyQt5.QtCore import pyqtSignal
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
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..config.presets import PresetInfo


PathLike = Tuple[str, ...]


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
    # Generic widget helpers
    # ------------------------------------------------------------------
    def _group(self, body_layout: QVBoxLayout, title: str, description: str = "") -> QFormLayout:
        box = QGroupBox(title)
        form = QFormLayout(box)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        if description:
            label = QLabel(description)
            label.setWordWrap(True)
            label.setStyleSheet("color:#64748b; font-size:10px;")
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
    ) -> QWidget:
        self.controls[name] = (path, widget)
        form.addRow(label, widget)
        return widget

    def _combo(self, values: Iterable[str], value: Any) -> QComboBox:
        widget = QComboBox()
        items = [str(item) for item in values]
        current = str(value if value is not None else "")
        if current and current not in items:
            items.append(current)
        widget.addItems(items)
        if current:
            widget.setCurrentText(current)
        return widget

    def _int_spin(self, value: Any, minimum: int, maximum: int, step: int = 1) -> QSpinBox:
        widget = QSpinBox()
        widget.setRange(minimum, maximum)
        widget.setSingleStep(step)
        widget.setValue(int(round(float(value if value is not None else 0))))
        return widget

    def _float_spin(
        self,
        value: Any,
        minimum: float,
        maximum: float,
        step: float = 0.1,
        decimals: int = 3,
    ) -> QDoubleSpinBox:
        widget = QDoubleSpinBox()
        widget.setRange(minimum, maximum)
        widget.setSingleStep(step)
        widget.setDecimals(decimals)
        widget.setValue(float(value if value is not None else 0.0))
        return widget

    def _check(self, value: Any, text: str) -> QCheckBox:
        widget = QCheckBox(text)
        widget.setChecked(bool(value))
        return widget

    def _line(self, value: Any, placeholder: str = "") -> QLineEdit:
        widget = QLineEdit(str(value if value is not None else ""))
        widget.setPlaceholderText(placeholder)
        return widget

    def _json_editor(self, value: Any, placeholder: str = "") -> QPlainTextEdit:
        widget = QPlainTextEdit()
        widget.setMaximumHeight(110)
        widget.setPlaceholderText(placeholder)
        widget.setPlainText(_json_text(value))
        return widget

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        title = "AI SYSTEM — identity, candidates, decoys, and AI runtime"
        subtitle = (
            "AI-only controls live here. Changes are staged independently "
            "from the deterministic/classical portion."
        )
        if not self.is_ai_panel:
            title = "DETERMINISTIC SYSTEM — classical detector → EKF-IMM → PID"
            subtitle = (
                "The existing deterministic path has its own complete copy of "
                "the run, scene, detector, tracker, and environment parameters."
            )
        heading = QLabel(title)
        heading.setWordWrap(True)
        heading.setStyleSheet(
            "font-size:13px; font-weight:800; color:#1e3a8a;"
            if self.is_ai_panel
            else "font-size:13px; font-weight:800; color:#334155;"
        )
        root.addWidget(heading)
        detail = QLabel(subtitle)
        detail.setWordWrap(True)
        detail.setStyleSheet("color:#64748b; font-size:10px;")
        root.addWidget(detail)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(4, 4, 4, 4)
        body_layout.setSpacing(9)
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
            "Presets & Run",
            "Only presets owned by this system appear here. Benchmark P01–P12 files remain outside the GUI.",
        )
        self.preset_combo = QComboBox()
        self.preset_combo.addItems([info.display_name for info in self.presets] + ["Custom"])
        self._add(presets_form, "Preset", "preset", ("__preset__",), self.preset_combo)
        self.preset_desc = QLabel("Select a preset and load it into this portion.")
        self.preset_desc.setWordWrap(True)
        self.preset_desc.setStyleSheet("color:#64748b; font-size:10px;")
        presets_form.addRow("", self.preset_desc)
        self.preset_expected = QLabel("")
        self.preset_expected.setWordWrap(True)
        self.preset_expected.setStyleSheet(
            "color:#0f172a; font-size:10px; background:#f1f5f9; padding:5px; border-radius:4px;"
        )
        self.preset_expected.hide()
        presets_form.addRow("", self.preset_expected)
        buttons = QHBoxLayout()
        self.btn_load_preset = QPushButton("Load Preset")
        self.btn_save_preset = QPushButton("Save As…")
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
        )
        self._add(
            presets_form,
            "Duration (s)",
            "experiment.duration_s",
            ("experiment", "duration_s"),
            self._float_spin(experiment.get("duration_s", 30), 1, 600, 1, 1),
        )
        self.btn_load_preset.clicked.connect(self._request_load)
        self.btn_save_preset.clicked.connect(self.presetSaveRequested.emit)
        self.preset_combo.currentTextChanged.connect(self._on_preset_changed)

        # ----- Target and scene -------------------------------------
        target_form = self._group(
            body_layout,
            "Target & Scene",
            "This is a private staged copy; it is not shared with the other system portion.",
        )
        self._add(target_form, "Target Type", "target.type", ("target", "type"), self._combo(["beacon_spot", "beacon", "spot"], target.get("type", "beacon_spot")))
        self._add(target_form, "Rendered Target Count", "target.count", ("target", "count"), self._int_spin(target.get("count", 1), 1, 5))
        self._add(target_form, "Shape", "target.shape", ("target", "shape"), self._combo(["square", "circle", "gaussian", "cross", "user-defined"], target.get("shape", "square")))
        self._add(target_form, "Custom Polygon (JSON)", "target.custom_polygon", ("target", "custom_polygon"), self._json_editor(target.get("custom_polygon"), "[[-5,-5],[5,-5],[0,5]]"))
        self._add(target_form, "Size (px)", "target.size", ("target", "size"), self._int_spin(target.get("size", 10), 5, 20))
        self._add(target_form, "Intensity", "target.intensity", ("target", "intensity"), self._int_spin(target.get("intensity", 255), 0, 255))
        self._add(target_form, "Initial Position Mode", "target.initial_mode", ("target", "initial_mode"), self._combo(["random", "centre", "center", "user-defined"], target.get("initial_mode", "random")))
        self._add(target_form, "Initial X", "target.initial_x", ("target", "initial_pos", 0), self._int_spin((target.get("initial_pos") or [1000, 1000])[0], 0, 4000))
        self._add(target_form, "Initial Y", "target.initial_y", ("target", "initial_pos", 1), self._int_spin((target.get("initial_pos") or [1000, 1000])[1], 0, 4000))
        self._add(target_form, "Trajectory", "target.trajectory", ("target", "trajectory"), self._combo(["straight", "circular", "figure_eight", "random", "spiral", "sinusoidal", "user-defined"], target.get("trajectory", "circular")))
        self._add(target_form, "Custom Trajectory (CSV path)", "target.custom_trajectory_file", ("target", "custom_trajectory_file"), self._line(target.get("custom_trajectory_file", ""), "Optional CSV path"))
        self._add(target_form, "Speed (px/frame)", "target.speed_px_per_frame", ("target", "speed_px_per_frame"), self._float_spin(target.get("speed_px_per_frame", 2.8), 0, 20, 0.1, 3))
        self._add(target_form, "Angle (straight)", "target.angle_deg", ("target", "angle_deg"), self._float_spin(target.get("angle_deg", 30), 0, 360, 1, 1))
        self._add(target_form, "Radius (circular/8)", "target.radius", ("target", "radius"), self._float_spin(target.get("radius", 180), 50, 800, 5, 1))

        # ----- Camera ------------------------------------------------
        camera_form = self._group(body_layout, "Camera", "Camera geometry and motion limits for this system profile.")
        self._add(camera_form, "Camera Type", "camera.type", ("camera", "type"), self._combo(["monochrome", "colour", "color"], camera.get("type", "monochrome")))
        self._add(camera_form, "Resolution Width", "camera.resolution.0", ("camera", "resolution", 0), self._int_spin((camera.get("resolution") or [640, 480])[0], 320, 1920))
        self._add(camera_form, "Resolution Height", "camera.resolution.1", ("camera", "resolution", 1), self._int_spin((camera.get("resolution") or [640, 480])[1], 240, 1080))
        self._add(camera_form, "Horizontal FOV (°)", "camera.fov_deg.0", ("camera", "fov_deg", 0), self._float_spin((camera.get("fov_deg") or [4, 3])[0], 1, 12, 0.1, 2))
        self._add(camera_form, "Vertical FOV (°)", "camera.fov_deg.1", ("camera", "fov_deg", 1), self._float_spin((camera.get("fov_deg") or [4, 3])[1], 1, 12, 0.1, 2))
        self._add(camera_form, "Frame Rate (Hz)", "camera.fps", ("camera", "fps"), self._int_spin(camera.get("fps", 30), 30, 60))
        self._add(camera_form, "Initial Position", "camera.initial_position", ("camera", "initial_position"), self._combo(["centre", "center", "user-defined"], camera.get("initial_position", "centre")))
        self._add(camera_form, "Initial Pan (°)", "camera.initial_pan", ("camera", "initial_pan"), self._float_spin(camera.get("initial_pan", 0), -180, 180, 1, 2))
        self._add(camera_form, "Initial Tilt (°)", "camera.initial_tilt", ("camera", "initial_tilt"), self._float_spin(camera.get("initial_tilt", 0), -90, 90, 1, 2))
        self._add(camera_form, "Max Pan Speed (°/s)", "camera.max_pan_speed", ("camera", "max_pan_speed"), self._float_spin(camera.get("max_pan_speed", 5), 1, 15, 0.5, 2))
        self._add(camera_form, "Max Tilt Speed (°/s)", "camera.max_tilt_speed", ("camera", "max_tilt_speed"), self._float_spin(camera.get("max_tilt_speed", 5), 1, 15, 0.5, 2))
        self._add(camera_form, "Update Rate (Hz)", "camera.update_interval_hz", ("camera", "update_interval_hz"), self._int_spin(camera.get("update_interval_hz", 30), 20, 60))
        self._add(camera_form, "Jitter ±px/frame", "camera.jitter_px", ("camera", "jitter_px"), self._float_spin(camera.get("jitter_px", 0), 0, 20, 0.5, 2))

        # ----- Detection ---------------------------------------------
        detection_form = self._group(body_layout, "Detection", "Classical detector parameters; AI candidate settings are in the AI-only group below.")
        self._add(detection_form, "Threshold k", "detector.threshold_k", ("detector", "threshold_k"), self._float_spin(detector.get("threshold_k", 3), 1.5, 8, 0.1, 2))
        self._add(detection_form, "Minimum Area", "detector.min_area", ("detector", "min_area"), self._int_spin(detector.get("min_area", 8), 2, 200))
        self._add(detection_form, "Maximum Area", "detector.max_area", ("detector", "max_area"), self._int_spin(detector.get("max_area", 900), 20, 5000))
        self._add(detection_form, "Blur Kernel", "detector.blur_ksize", ("detector", "blur_ksize"), self._int_spin(detector.get("blur_ksize", 3), 1, 15, 2))
        self._add(detection_form, "Adaptive Block", "detector.adaptive_block", ("detector", "adaptive_block"), self._int_spin(detector.get("adaptive_block", 51), 3, 301, 2))
        self._add(detection_form, "Adaptive C", "detector.adaptive_C", ("detector", "adaptive_C"), self._int_spin(detector.get("adaptive_C", -5), -50, 50))

        # ----- Search and tracker ------------------------------------
        search_form = self._group(body_layout, "Search & Tracker", "Deterministic recovery and IMM/EKF parameters for this system profile.")
        self._add(search_form, "Search Mode", "search.mode", ("search", "mode"), self._combo(["spiral", "raster", "hybrid"], search.get("mode", "spiral")))
        self._add(search_form, "ROI Size (px)", "search.roi_size", ("search", "roi_size"), self._int_spin(search.get("roi_size", 160), 40, 800))
        self._add(search_form, "Local Loss Timeout (frames)", "tracker.lost_timeout_frames", ("tracker", "lost_timeout_frames"), self._int_spin(tracker.get("lost_timeout_frames", 15), 1, 100))
        self._add(search_form, "Re-acquisition Timeout (frames)", "tracker.reacq_timeout_frames", ("tracker", "reacq_timeout_frames"), self._int_spin(tracker.get("reacq_timeout_frames", 30), 1, 300))
        self._add(search_form, "Process Noise", "tracker.process_noise", ("tracker", "process_noise"), self._float_spin(tracker.get("process_noise", 0.8), 0, 20, 0.1, 3))
        self._add(search_form, "Measurement Noise", "tracker.meas_noise", ("tracker", "meas_noise"), self._float_spin(tracker.get("meas_noise", 4), 0.1, 50, 0.1, 3))
        self._add(search_form, "Association Gate σ", "tracker.gate_sigma", ("tracker", "gate_sigma"), self._float_spin(tracker.get("gate_sigma", 5), 0.5, 30, 0.5, 2))

        # ----- Estimator and controller ------------------------------
        control_form = self._group(body_layout, "Estimator & Controller", "PID and EKF-IMM parameters for the selected system profile.")
        self._add(control_form, "Kp Pan", "controller.kp_pan", ("controller", "kp_pan"), self._float_spin(controller.get("kp_pan", 1.2), 0, 20, 0.1, 3))
        self._add(control_form, "Kp Tilt", "controller.kp_tilt", ("controller", "kp_tilt"), self._float_spin(controller.get("kp_tilt", 1.2), 0, 20, 0.1, 3))
        self._add(control_form, "Ki", "controller.ki", ("controller", "ki"), self._float_spin(controller.get("ki", 0.05), 0, 10, 0.01, 3))
        self._add(control_form, "Kd", "controller.kd", ("controller", "kd"), self._float_spin(controller.get("kd", 0.15), 0, 10, 0.01, 3))
        self._add(control_form, "Deadzone (px)", "controller.deadzone_px", ("controller", "deadzone_px"), self._float_spin(controller.get("deadzone_px", 2), 0, 50, 0.5, 2))
        self._add(control_form, "Integral Limit", "controller.integral_limit", ("controller", "integral_limit"), self._float_spin(controller.get("integral_limit", 8), 0, 100, 0.5, 2))
        self._add(control_form, "Feedforward Gain", "controller.feedforward_gain", ("controller", "feedforward_gain"), self._float_spin(controller.get("feedforward_gain", 0), 0, 20, 0.1, 3))

        # ----- Environment and disturbances --------------------------
        env_form = self._group(body_layout, "World & Environment", "World, platform, background, stars, vignetting, and brightness settings.")
        self._add(env_form, "World Width", "world.width", ("world", "width"), self._int_spin(world.get("width", 2000), 2000, 4000))
        self._add(env_form, "World Height", "world.height", ("world", "height"), self._int_spin(world.get("height", 2000), 2000, 4000))
        self._add(env_form, "Background Intensity", "world.background", ("world", "background"), self._int_spin(world.get("background", 18), 0, 79))
        self._add(env_form, "Platform Type", "platform.type", ("platform", "type"), self._combo(["none", "linear", "circular", "random", "spiral", "figure_of_8"], platform.get("type", "none")))
        self._add(env_form, "Platform Speed", "platform.speed_px_per_frame", ("platform", "speed_px_per_frame"), self._float_spin(platform.get("speed_px_per_frame", 0), 0, 20, 0.5, 2))
        self._add(env_form, "Platform Amplitude", "platform.amplitude", ("platform", "amplitude"), self._float_spin(platform.get("amplitude", 0), 0, 200, 1, 2))
        self._add(env_form, "Gradient Enabled", "environment.gradient_enabled", ("environment", "gradient_enabled"), self._check(environment.get("gradient_enabled", False), "Enable background gradient"))
        self._add(env_form, "Gradient Type", "environment.gradient_type", ("environment", "gradient_type"), self._combo(["linear", "radial", "diagonal"], environment.get("gradient_type", "linear")))
        self._add(env_form, "Gradient Top", "environment.gradient_top", ("environment", "gradient_top"), self._int_spin(environment.get("gradient_top", 22), 0, 255))
        self._add(env_form, "Gradient Bottom", "environment.gradient_bottom", ("environment", "gradient_bottom"), self._int_spin(environment.get("gradient_bottom", 38), 0, 255))
        self._add(env_form, "Gradient Angle", "environment.gradient_angle", ("environment", "gradient_angle"), self._int_spin(environment.get("gradient_angle", 90), 0, 360))
        self._add(env_form, "Stars Enabled", "environment.stars_enabled", ("environment", "stars_enabled"), self._check(environment.get("stars_enabled", False), "Enable stars clutter"))
        self._add(env_form, "Stars Density", "environment.stars_density", ("environment", "stars_density"), self._float_spin(environment.get("stars_density", 0.0007), 0, 0.1, 0.0001, 6))
        self._add(env_form, "Stars Brightness", "environment.stars_brightness", ("environment", "stars_brightness"), self._int_spin(environment.get("stars_brightness", 185), 0, 255))
        self._add(env_form, "Stars Min Magnitude", "environment.stars_min_mag", ("environment", "stars_min_mag"), self._int_spin(environment.get("stars_min_mag", 90), 0, 255))
        self._add(env_form, "Stars Max Magnitude", "environment.stars_max_mag", ("environment", "stars_max_mag"), self._int_spin(environment.get("stars_max_mag", 255), 0, 255))
        self._add(env_form, "Stars Twinkle", "environment.stars_twinkle", ("environment", "stars_twinkle"), self._check(environment.get("stars_twinkle", False), "Enable per-frame twinkle"))
        self._add(env_form, "Stars Seed", "environment.stars_seed", ("environment", "stars_seed"), self._int_spin(environment.get("stars_seed", 1337), 0, 999999))
        self._add(env_form, "Vignetting Enabled", "environment.vignetting_enabled", ("environment", "vignetting_enabled"), self._check(environment.get("vignetting_enabled", False), "Enable lens falloff"))
        self._add(env_form, "Vignetting Strength", "environment.vignetting_strength", ("environment", "vignetting_strength"), self._float_spin(environment.get("vignetting_strength", 0.42), 0, 1, 0.05, 3))
        self._add(env_form, "Vignetting Radius", "environment.vignetting_radius", ("environment", "vignetting_radius"), self._float_spin(environment.get("vignetting_radius", 0.72), 0, 1, 0.05, 3))
        self._add(env_form, "Vignetting Falloff", "environment.vignetting_falloff", ("environment", "vignetting_falloff"), self._float_spin(environment.get("vignetting_falloff", 2), 0, 20, 0.1, 3))
        self._add(env_form, "Vignetting Center X", "environment.vignetting_center_x", ("environment", "vignetting_center_x"), self._float_spin(environment.get("vignetting_center_x", 0.5), 0, 1, 0.05, 3))
        self._add(env_form, "Vignetting Center Y", "environment.vignetting_center_y", ("environment", "vignetting_center_y"), self._float_spin(environment.get("vignetting_center_y", 0.5), 0, 1, 0.05, 3))
        self._add(env_form, "Brightness Gain", "environment.brightness_gain", ("environment", "brightness_gain"), self._float_spin(environment.get("brightness_gain", 1), 0, 5, 0.05, 3))
        self._add(env_form, "Brightness Offset", "environment.brightness_offset", ("environment", "brightness_offset"), self._int_spin(environment.get("brightness_offset", 0), -255, 255))

        disturb_form = self._group(body_layout, "Disturbances", "Image noise and atmospheric parameters for this system profile.")
        self._add(disturb_form, "Gaussian Enabled", "noise.gaussian_enabled", ("noise", "gaussian_enabled"), self._check(noise.get("gaussian_enabled", False), "Enable Gaussian noise"))
        self._add(disturb_form, "Gaussian σ", "noise.gaussian_std", ("noise", "gaussian_std"), self._float_spin(noise.get("gaussian_std", 0), 0, 100, 0.5, 2))
        self._add(disturb_form, "Salt & Pepper Enabled", "noise.salt_pepper_enabled", ("noise", "salt_pepper_enabled"), self._check(noise.get("salt_pepper_enabled", False), "Enable salt & pepper noise"))
        self._add(disturb_form, "Salt & Pepper Probability", "noise.salt_pepper_prob", ("noise", "salt_pepper_prob"), self._float_spin(noise.get("salt_pepper_prob", 0), 0, 0.5, 0.005, 4))
        self._add(disturb_form, "Poisson Enabled", "noise.poisson", ("noise", "poisson"), self._check(noise.get("poisson", False), "Enable Poisson noise"))
        self._add(disturb_form, "Atmosphere", "atmosphere.type", ("atmosphere", "type"), self._combo(["clear", "haze", "fog", "rain", "low_light"], atmosphere.get("type", "clear")))
        self._add(disturb_form, "Atmosphere Strength", "atmosphere.strength", ("atmosphere", "strength"), self._float_spin(atmosphere.get("strength", 0), 0, 1, 0.05, 3))

        # ----- Input and video ---------------------------------------
        input_form = self._group(body_layout, "Input / Video", "Synthetic and external-video input settings for this system profile.")
        self._add(input_form, "Input Mode", "experiment.input_mode", ("experiment", "input_mode"), self._combo(["SYNTHETIC", "VIDEO"], experiment.get("input_mode", "SYNTHETIC")))
        self._add(input_form, "Video Path", "experiment.video_path", ("experiment", "video_path"), self._line(experiment.get("video_path", ""), "data/input_videos/benchmark.mp4"))
        self._add(input_form, "Video Centre Offset X", "camera.video_centre_offset_x", ("camera", "video_centre_offset_x"), self._float_spin(camera.get("video_centre_offset_x", 0), -1000, 1000, 1, 2))
        self._add(input_form, "Video Centre Offset Y", "camera.video_centre_offset_y", ("camera", "video_centre_offset_y"), self._float_spin(camera.get("video_centre_offset_y", 0), -1000, 1000, 1, 2))
        self._add(input_form, "Preserve Native FPS", "experiment.preserve_native_fps", ("experiment", "preserve_native_fps"), self._check(experiment.get("preserve_native_fps", False), "Preserve source FPS"))
        self._add(input_form, "Expected FPS", "experiment.expected_fps", ("experiment", "expected_fps"), self._float_spin(experiment.get("expected_fps", 30), 1, 240, 1, 2))
        self._add(input_form, "Bypass Virtual PTZ", "experiment.bypass_virtual_ptz", ("experiment", "bypass_virtual_ptz"), self._check(experiment.get("bypass_virtual_ptz", False), "Bypass virtual pan/tilt"))
        self._add(input_form, "Resize Mode", "experiment.resize_mode", ("experiment", "resize_mode"), self._line(experiment.get("resize_mode", "preserve_reference_scale"), "preserve_reference_scale"))

        # ----- AI-only controls --------------------------------------
        if self.is_ai_panel:
            self._build_ai_controls(body_layout, ai, primary, decoys, search)

        # Direct names retained for integrations and tests.
        self.seed_spin = self.controls["experiment.seed"][1]
        self.duration_spin = self.controls["experiment.duration_s"][1]
        self.tgt_count_spin = self.controls["target.count"][1]
        self.tgt_shape_combo = self.controls["target.shape"][1]
        self.size_spin = self.controls["target.size"][1]
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
        self.tgt_type_combo = self.controls["target.type"][1]
        self.tgt_init_mode_combo = self.controls["target.initial_mode"][1]
        self.tgt_init_x_spin = self.controls["target.initial_x"][1]
        self.tgt_init_y_spin = self.controls["target.initial_y"][1]
        self.custom_polygon_edit = self.controls["target.custom_polygon"][1]
        self.custom_traj_edit = self.controls["target.custom_trajectory_file"][1]
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

        form = self._group(
            body_layout,
            "AI / Identity Controls",
            "These controls exist only in the AI portion. They are not applied while the deterministic portion is active.",
        )
        self._add(form, "AI System Enabled", "ai.enabled", ("ai", "enabled"), self._check(ai.get("enabled", True), "Enable AI identification"))
        self._add(form, "Fallback on Failure", "ai.fallback_on_failure", ("ai", "fallback_on_failure"), self._check(ai.get("fallback_on_failure", True), "Use deterministic heuristic fallback"))
        self._add(form, "Patch Size", "ai.patch_size", ("ai", "patch_size"), self._int_spin(ai.get("patch_size", 64), 32, 128))
        self._add(form, "Sequence Length", "ai.sequence_length", ("ai", "sequence_length"), self._int_spin(ai.get("sequence_length", 25), 10, 100))
        self._add(form, "GRU Hidden Size", "ai.gru_hidden", ("ai", "gru_hidden"), self._int_spin(ai.get("gru_hidden", 64), 8, 512))
        self._add(form, "Inference Timeout (ms)", "ai.inference_timeout_ms", ("ai", "inference_timeout_ms"), self._int_spin(ai.get("inference_timeout_ms", 40), 1, 5000))
        self._add(form, "Primary Threshold", "ai.thresholds.primary_threshold", ("ai", "thresholds", "primary_threshold"), self._float_spin(thresholds.get("primary_threshold", 0.85), 0.5, 0.999, 0.01, 3))
        self._add(form, "Decoy Threshold", "ai.thresholds.decoy_threshold", ("ai", "thresholds", "decoy_threshold"), self._float_spin(thresholds.get("decoy_threshold", 0.85), 0.5, 0.999, 0.01, 3))
        self._add(form, "Confirmation Frames", "ai.thresholds.confirmation_frames", ("ai", "thresholds", "confirmation_frames"), self._int_spin(thresholds.get("confirmation_frames", 5), 1, 30))
        self._add(form, "Unknown Low", "ai.thresholds.unknown_low", ("ai", "thresholds", "unknown_low"), self._float_spin(thresholds.get("unknown_low", 0.45), 0, 1, 0.01, 3))
        self._add(form, "Unknown High", "ai.thresholds.unknown_high", ("ai", "thresholds", "unknown_high"), self._float_spin(thresholds.get("unknown_high", 0.85), 0, 1, 0.01, 3))
        self._add(form, "Signature Enabled", "ai.signatures.enabled", ("ai", "signatures", "enabled"), self._check(signatures.get("enabled", True), "Enable coded optical signature"))
        self._add(form, "Blink Pattern", "ai.signatures.blink_pattern", ("ai", "signatures", "blink_pattern"), self._line(signatures.get("blink_pattern", "10110010"), "10110010"))
        self._add(form, "Modulation Frequency (Hz)", "ai.signatures.modulation_freq_hz", ("ai", "signatures", "modulation_freq_hz"), self._float_spin(signatures.get("modulation_freq_hz", 12), 0.1, 240, 0.1, 3))
        self._add(form, "Frequency Tolerance", "ai.signatures.freq_tolerance", ("ai", "signatures", "freq_tolerance"), self._float_spin(signatures.get("freq_tolerance", 0.05), 0.001, 1, 0.005, 4))
        self._add(form, "Expected Shape", "ai.signatures.expected_shape", ("ai", "signatures", "expected_shape"), self._line(signatures.get("expected_shape", "square"), "square"))
        self._add(form, "Signature Min Size", "ai.signatures.size_range_px.0", ("ai", "signatures", "size_range_px", 0), self._int_spin((signatures.get("size_range_px") or [5, 20])[0], 1, 100))
        self._add(form, "Signature Max Size", "ai.signatures.size_range_px.1", ("ai", "signatures", "size_range_px", 1), self._int_spin((signatures.get("size_range_px") or [5, 20])[1], 1, 100))
        self._add(form, "Persistence Frames", "ai.signatures.persistence_frames", ("ai", "signatures", "persistence_frames"), self._int_spin(signatures.get("persistence_frames", 5), 1, 100))
        self._add(form, "AI Detection Confidence", "ai.detection_threshold", ("ai", "detection_threshold"), self._float_spin(ai.get("detection_threshold", 0.45), 0, 1, 0.01, 3))
        self._add(form, "AI Search Ranking", "ai.search_ranking", ("ai", "search_ranking"), self._check(ai.get("search_ranking", True), "Use predicted position, velocity, decoy memory, and disturbance-aware ranking"))
        self._add(form, "Appearance Weight", "ai.weights.appearance", ("ai", "weights", "appearance"), self._float_spin(weights.get("appearance", 0.2), 0, 1, 0.01, 3))
        self._add(form, "Motion Weight", "ai.weights.motion", ("ai", "weights", "motion"), self._float_spin(weights.get("motion", 0.2), 0, 1, 0.01, 3))
        self._add(form, "Temporal Weight", "ai.weights.temporal", ("ai", "weights", "temporal"), self._float_spin(weights.get("temporal", 0.2), 0, 1, 0.01, 3))
        self._add(form, "Signature Weight", "ai.weights.signature", ("ai", "weights", "signature"), self._float_spin(weights.get("signature", 0.25), 0, 1, 0.01, 3))
        self._add(form, "Estimator Weight", "ai.weights.estimator", ("ai", "weights", "estimator"), self._float_spin(weights.get("estimator", 0.15), 0, 1, 0.01, 3))
        self._add(form, "Candidate Model", "ai.candidate_model_path", ("ai", "candidate_model_path"), self._line(ai.get("candidate_model_path", ""), "models/candidate_classifier/best.onnx (empty = heuristic)"))
        self._add(form, "Identity Model", "ai.identity_model_path", ("ai", "identity_model_path"), self._line(ai.get("identity_model_path", ""), "models/identity_classifier/best.onnx (empty = heuristic voter)"))

        primary_form = self._group(
            body_layout,
            "AI Primary Profile",
            "Evaluator-facing optical and geometric identity evidence. These fields are private to the AI profile.",
        )
        self._add(primary_form, "Primary Shape", "primary_target.shape", ("primary_target", "shape"), self._combo(["square", "circle", "gaussian", "cross"], primary.get("shape", "square")))
        self._add(primary_form, "Primary Size (px)", "primary_target.size_px", ("primary_target", "size_px"), self._int_spin(primary.get("size_px", 10), 1, 100))
        self._add(primary_form, "Brightness Min", "primary_target.brightness_range.0", ("primary_target", "brightness_range", 0), self._int_spin((primary.get("brightness_range") or [180, 255])[0], 0, 255))
        self._add(primary_form, "Brightness Max", "primary_target.brightness_range.1", ("primary_target", "brightness_range", 1), self._int_spin((primary.get("brightness_range") or [180, 255])[1], 0, 255))
        self._add(primary_form, "Allowed Motion (JSON)", "primary_target.allowed_motion", ("primary_target", "allowed_motion"), self._json_editor(primary.get("allowed_motion", ["straight", "circular", "figure_eight", "random"]), '["straight","circular"]'))
        self._add(primary_form, "Max Speed (px/frame)", "primary_target.max_speed_px_per_frame", ("primary_target", "max_speed_px_per_frame"), self._float_spin(primary.get("max_speed_px_per_frame", 20), 0, 100, 0.5, 2))
        self._add(primary_form, "Primary Optical Signature (JSON)", "primary_target.optical_signature", ("primary_target", "optical_signature"), self._json_editor(optical, '{"blink_pattern":"10110010"}'))
        self._add(primary_form, "Decoys Enabled", "decoys.enabled", ("decoys", "enabled"), self._check(decoys.get("enabled", True), "Render decoy candidates"))
        self._add(primary_form, "Decoy Count", "decoys.count", ("decoys", "count"), self._int_spin(decoys.get("count", 2), 0, 8))
        self._add(primary_form, "Decoy Initial Positions (JSON)", "decoys.initial_positions", ("decoys", "initial_positions"), self._json_editor(decoys.get("initial_positions", []), "[[960,980],[1040,1020]]"))
        self._add(primary_form, "Decoy Profiles (JSON)", "decoys.profiles", ("decoys", "profiles"), self._json_editor(profiles, '[{"type":"reflection","blink_pattern":"11100011"}]'))

    # ------------------------------------------------------------------
    # Config <-> widgets
    # ------------------------------------------------------------------
    @staticmethod
    def _widget_value(widget: QWidget) -> Any:
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
        # The JSON editors are always visible; the explanatory text makes the
        # mode explicit without hiding parameters that may be needed later.
        return

    def set_config(self, config: Dict[str, Any]) -> None:
        self.cfg = copy.deepcopy(config)
        for _name, (path, widget) in self.controls.items():
            if path == ("__preset__",):
                continue
            value = _get_path(self.cfg, path, None)
            if isinstance(widget, QComboBox):
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

        # Reconcile the two target position fields with the three-state UI.
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

        # Keep both AI signature representations in sync for the World and
        # the identity scorer, but only the AI panel owns these values.
        if self.is_ai_panel:
            ai_enabled = bool(_get_path(result, ("ai", "enabled"), False))
            _set_path(result, ("ai", "enabled"), ai_enabled)
            ai_sig = _get_path(result, ("ai", "signatures"), {}) or {}
            _set_path(result, ("primary_target", "optical_signature"), copy.deepcopy(ai_sig))
            decoy_count = int(_get_path(result, ("decoys", "count"), 0) or 0)
            _set_path(result, ("decoys", "enabled"), decoy_count > 0 and bool(_get_path(result, ("decoys", "enabled"), True)))
        else:
            _set_path(result, ("ai", "enabled"), False)

        # Validate before the wrapper emits it to the live application.
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
            self.preset_desc.setText("Custom: edit this system portion independently, then use Save As.")
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
            self.ai_enabled_check.setChecked(bool(enabled))


__all__ = ["SystemControlPanel"]
