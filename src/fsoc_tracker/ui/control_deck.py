from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget, QLabel, QComboBox, QDoubleSpinBox, QSpinBox,
                             QSlider, QCheckBox, QPushButton, QFormLayout, QGroupBox, QLineEdit, QFileDialog, QMessageBox)
from PyQt5.QtCore import Qt, pyqtSignal
from ..config.loader import load_config

class ControlDeck(QDialog):
    configApplied = pyqtSignal(dict)

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Control Deck  —  FSOC Tracker")
        self.resize(580, 640)
        self.cfg = cfg
        from .theme import STYLESHEET
        self.setStyleSheet(STYLESHEET)
        lay = QVBoxLayout(self)
        self.tabs = QTabWidget()
        lay.addWidget(self.tabs)

        self.tabs.addTab(self._presets_tab(), "Presets & Run")
        self.tabs.addTab(self._target_tab(), "Target")
        self.tabs.addTab(self._camera_tab(), "Camera")
        self.tabs.addTab(self._estimator_tab(), "Estimator & Controller")
        self.tabs.addTab(self._env_tab(), "Environment")
        self.tabs.addTab(self._disturb_tab(), "Disturbances")
        self.tabs.addTab(self._input_tab(), "Input/Logging")

        btns = QHBoxLayout()
        self.btn_apply = QPushButton("Apply"); self.btn_apply.setObjectName("Primary")
        self.btn_cancel = QPushButton("Cancel")
        self.btn_reset = QPushButton("Restore Defaults")
        btns.addWidget(self.btn_reset); btns.addStretch(); btns.addWidget(self.btn_cancel); btns.addWidget(self.btn_apply)
        lay.addLayout(btns)
        self.btn_apply.clicked.connect(self._apply)
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_reset.clicked.connect(self._restore_defaults)

    def _presets_tab(self):
        w = QWidget(); f = QFormLayout(w)
        self.preset_combo = QComboBox()
        self.preset_combo.addItems(["Clean Baseline","High Noise","Platform Jitter","Low Light / Fog","Custom"])
        self.seed_spin = QSpinBox(); self.seed_spin.setRange(0,999999); self.seed_spin.setValue(self.cfg["experiment"]["seed"])
        self.duration_spin = QDoubleSpinBox(); self.duration_spin.setRange(5,600); self.duration_spin.setValue(self.cfg["experiment"]["duration_s"])
        self.btn_load_preset = QPushButton("Load Preset")
        f.addRow("Preset", self.preset_combo)
        f.addRow("", self.btn_load_preset)
        f.addRow("Random Seed", self.seed_spin)
        f.addRow("Duration (s)", self.duration_spin)
        self.btn_load_preset.clicked.connect(self._load_preset)
        return w

    def _load_preset(self):
        name = self.preset_combo.currentText()
        if name=="Clean Baseline":
            self._set_fields(atmo="clear", gauss=0, spp=0, jitter=0, platform="none")
        elif name=="High Noise":
            self._set_fields(atmo="clear", gauss=12, spp=0.02, jitter=6, platform="linear")
        elif name=="Platform Jitter":
            self._set_fields(atmo="clear", gauss=4, spp=0, jitter=14, platform="linear")
        elif name=="Low Light / Fog":
            self._set_fields(atmo="fog", gauss=5, spp=0, jitter=4, platform="none")
        QMessageBox.information(self,"Preset","Preset fields staged. Click Apply to commit.")

    def _set_fields(self, atmo, gauss, spp, jitter, platform):
        # update widgets if they exist
        try:
            self.atmo_combo.setCurrentText(atmo)
            self.gauss_spin.setValue(gauss)
            self.spp_spin.setValue(spp)
            self.jitter_spin.setValue(jitter)
            self.platform_combo.setCurrentText(platform)
        except: pass

    def _target_tab(self):
        w = QWidget(); f = QFormLayout(w)
        self.traj_combo = QComboBox(); self.traj_combo.addItems(["straight","circular","figure_eight","random","spiral","sinusoidal"])
        self.traj_combo.setCurrentText(self.cfg["target"]["trajectory"])
        self.speed_spin = QDoubleSpinBox(); self.speed_spin.setRange(0,20); self.speed_spin.setSingleStep(0.5); self.speed_spin.setValue(float(self.cfg["target"]["speed_px_per_frame"]))
        self.size_spin = QSpinBox(); self.size_spin.setRange(5,20); self.size_spin.setValue(int(self.cfg["target"]["size"]))
        self.angle_spin = QDoubleSpinBox(); self.angle_spin.setRange(0,360); self.angle_spin.setValue(float(self.cfg["target"].get("angle_deg",30)))
        self.radius_spin = QDoubleSpinBox(); self.radius_spin.setRange(50,800); self.radius_spin.setValue(float(self.cfg["target"].get("radius",400)))
        f.addRow("Trajectory", self.traj_combo)
        f.addRow("Speed (px/frame)", self.speed_spin)
        f.addRow("Target size (px)", self.size_spin)
        f.addRow("Angle (straight)", self.angle_spin)
        f.addRow("Radius (circular/8)", self.radius_spin)
        return w

    def _camera_tab(self):
        w = QWidget(); f = QFormLayout(w)
        self.res_w_spin = QSpinBox(); self.res_w_spin.setRange(320,1280); self.res_w_spin.setValue(int(self.cfg["camera"]["resolution"][0]))
        self.res_h_spin = QSpinBox(); self.res_h_spin.setRange(240,960); self.res_h_spin.setValue(int(self.cfg["camera"]["resolution"][1]))
        self.fov_h_spin = QDoubleSpinBox(); self.fov_h_spin.setRange(1,10); self.fov_h_spin.setValue(float(self.cfg["camera"]["fov_deg"][0]))
        self.fov_v_spin = QDoubleSpinBox(); self.fov_v_spin.setRange(1,10); self.fov_v_spin.setValue(float(self.cfg["camera"]["fov_deg"][1]))
        self.max_pan_spin = QDoubleSpinBox(); self.max_pan_spin.setRange(1,15); self.max_pan_spin.setValue(float(self.cfg["camera"]["max_pan_speed"]))
        self.max_tilt_spin = QDoubleSpinBox(); self.max_tilt_spin.setRange(1,15); self.max_tilt_spin.setValue(float(self.cfg["camera"]["max_tilt_speed"]))
        self.jitter_spin = QDoubleSpinBox(); self.jitter_spin.setRange(0,20); self.jitter_spin.setValue(float(self.cfg["camera"]["jitter_px"]))
        f.addRow("Res W", self.res_w_spin); f.addRow("Res H", self.res_h_spin)
        f.addRow("HFOV (deg)", self.fov_h_spin); f.addRow("VFOV (deg)", self.fov_v_spin)
        f.addRow("Max pan °/s", self.max_pan_spin); f.addRow("Max tilt °/s", self.max_tilt_spin)
        f.addRow("Camera jitter px", self.jitter_spin)
        return w

    def _estimator_tab(self):
        w = QWidget(); f = QFormLayout(w)
        self.kp_pan_spin = QDoubleSpinBox(); self.kp_pan_spin.setRange(0,5); self.kp_pan_spin.setSingleStep(0.1); self.kp_pan_spin.setValue(float(self.cfg["controller"]["kp_pan"]))
        self.kp_tilt_spin = QDoubleSpinBox(); self.kp_tilt_spin.setRange(0,5); self.kp_tilt_spin.setSingleStep(0.1); self.kp_tilt_spin.setValue(float(self.cfg["controller"]["kp_tilt"]))
        self.ki_spin = QDoubleSpinBox(); self.ki_spin.setRange(0,1); self.ki_spin.setSingleStep(0.01); self.ki_spin.setValue(float(self.cfg["controller"]["ki"]))
        self.kd_spin = QDoubleSpinBox(); self.kd_spin.setRange(0,1); self.kd_spin.setSingleStep(0.02); self.kd_spin.setValue(float(self.cfg["controller"]["kd"]))
        self.dead_spin = QDoubleSpinBox(); self.dead_spin.setRange(0,10); self.dead_spin.setValue(float(self.cfg["controller"]["deadzone_px"]))
        self.proc_spin = QDoubleSpinBox(); self.proc_spin.setRange(0.1,5); self.proc_spin.setValue(float(self.cfg["tracker"]["process_noise"]))
        self.meas_spin = QDoubleSpinBox(); self.meas_spin.setRange(0.5,10); self.meas_spin.setValue(float(self.cfg["tracker"]["meas_noise"]))
        f.addRow("Kp pan", self.kp_pan_spin); f.addRow("Kp tilt", self.kp_tilt_spin)
        f.addRow("Ki", self.ki_spin); f.addRow("Kd", self.kd_spin)
        f.addRow("Deadzone px", self.dead_spin)
        f.addRow("Process noise", self.proc_spin); f.addRow("Meas noise", self.meas_spin)
        return w

    def _env_tab(self):
        w = QWidget(); f = QFormLayout(w)
        self.world_w_spin = QSpinBox(); self.world_w_spin.setRange(1000,4000); self.world_w_spin.setValue(int(self.cfg["world"]["width"]))
        self.world_h_spin = QSpinBox(); self.world_h_spin.setRange(1000,4000); self.world_h_spin.setValue(int(self.cfg["world"]["height"]))
        self.platform_combo = QComboBox(); self.platform_combo.addItems(["none","linear","circular","random"])
        self.platform_combo.setCurrentText(self.cfg["platform"]["type"])
        self.platform_speed_spin = QDoubleSpinBox(); self.platform_speed_spin.setRange(0,20); self.platform_speed_spin.setValue(float(self.cfg["platform"]["speed_px_per_frame"]))
        f.addRow("World W", self.world_w_spin); f.addRow("World H", self.world_h_spin)
        f.addRow("Platform type", self.platform_combo); f.addRow("Platform speed", self.platform_speed_spin)
        return w

    def _disturb_tab(self):
        w = QWidget(); f = QFormLayout(w)
        self.atmo_combo = QComboBox(); self.atmo_combo.addItems(["clear","haze","fog","rain","low_light"])
        self.atmo_combo.setCurrentText(self.cfg["atmosphere"]["type"])
        self.atmo_strength = QDoubleSpinBox(); self.atmo_strength.setRange(0,1); self.atmo_strength.setSingleStep(0.1); self.atmo_strength.setValue(float(self.cfg["atmosphere"]["strength"]))
        self.gauss_spin = QDoubleSpinBox(); self.gauss_spin.setRange(0,25); self.gauss_spin.setValue(float(self.cfg["noise"].get("gaussian_std",0)))
        self.gauss_check = QCheckBox("Enable Gaussian"); self.gauss_check.setChecked(bool(self.cfg["noise"].get("gaussian_enabled", False)))
        self.spp_spin = QDoubleSpinBox(); self.spp_spin.setRange(0,0.2); self.spp_spin.setSingleStep(0.01); self.spp_spin.setValue(float(self.cfg["noise"].get("salt_pepper_prob",0)))
        self.spp_check = QCheckBox("Enable Salt&Pepper"); self.spp_check.setChecked(bool(self.cfg["noise"].get("salt_pepper_enabled", False)))
        self.poisson_check = QCheckBox("Enable Poisson"); self.poisson_check.setChecked(bool(self.cfg["noise"].get("poisson", False)))
        f.addRow("Atmosphere", self.atmo_combo); f.addRow("Atmosphere strength", self.atmo_strength)
        f.addRow(self.gauss_check, self.gauss_spin)
        f.addRow(self.spp_check, self.spp_spin)
        f.addRow(self.poisson_check)
        return w

    def _input_tab(self):
        w = QWidget(); f = QFormLayout(w)
        self.input_combo = QComboBox(); self.input_combo.addItems(["SYNTHETIC","VIDEO"]); self.input_combo.setCurrentText(self.cfg["experiment"]["input_mode"])
        self.video_path_edit = QLineEdit(self.cfg["experiment"].get("video_path",""))
        self.btn_browse = QPushButton("Browse…")
        h = QHBoxLayout(); h.addWidget(self.video_path_edit); h.addWidget(self.btn_browse)
        f.addRow("Input mode", self.input_combo)
        f.addRow("Video path", h)
        self.btn_browse.clicked.connect(self._browse)
        return w

    def _browse(self):
        p,_ = QFileDialog.getOpenFileName(self, "Select video", "", "Video (*.mp4 *.avi *.mov)")
        if p: self.video_path_edit.setText(p)

    def _restore_defaults(self):
        from ..config.defaults import DEFAULT_CONFIG
        import copy
        self.cfg = copy.deepcopy(DEFAULT_CONFIG)
        self.reject()
        QMessageBox.information(self.parent(), "Defaults","Defaults restored. Reopen Control Deck.")

    def _apply(self):
        c = self.cfg
        # target
        c["target"]["trajectory"] = self.traj_combo.currentText()
        c["target"]["speed_px_per_frame"] = float(self.speed_spin.value())
        c["target"]["size"] = int(self.size_spin.value())
        c["target"]["angle_deg"] = float(self.angle_spin.value())
        c["target"]["radius"] = float(self.radius_spin.value())
        # camera
        c["camera"]["resolution"] = [int(self.res_w_spin.value()), int(self.res_h_spin.value())]
        c["camera"]["fov_deg"] = [float(self.fov_h_spin.value()), float(self.fov_v_spin.value())]
        c["camera"]["max_pan_speed"] = float(self.max_pan_spin.value())
        c["camera"]["max_tilt_speed"] = float(self.max_tilt_spin.value())
        c["camera"]["jitter_px"] = float(self.jitter_spin.value())
        # controller
        c["controller"]["kp_pan"] = float(self.kp_pan_spin.value())
        c["controller"]["kp_tilt"] = float(self.kp_tilt_spin.value())
        c["controller"]["ki"] = float(self.ki_spin.value())
        c["controller"]["kd"] = float(self.kd_spin.value())
        c["controller"]["deadzone_px"] = float(self.dead_spin.value())
        c["tracker"]["process_noise"] = float(self.proc_spin.value())
        c["tracker"]["meas_noise"] = float(self.meas_spin.value())
        # env
        c["world"]["width"] = int(self.world_w_spin.value())
        c["world"]["height"] = int(self.world_h_spin.value())
        c["platform"]["type"] = self.platform_combo.currentText()
        c["platform"]["speed_px_per_frame"] = float(self.platform_speed_spin.value())
        # disturb
        c["atmosphere"]["type"] = self.atmo_combo.currentText()
        c["atmosphere"]["strength"] = float(self.atmo_strength.value())
        c["noise"]["gaussian_std"] = float(self.gauss_spin.value())
        c["noise"]["salt_pepper_prob"] = float(self.spp_spin.value())
        c["noise"]["gaussian_enabled"] = bool(self.gauss_check.isChecked())
        c["noise"]["salt_pepper_enabled"] = bool(self.spp_check.isChecked())
        c["noise"]["poisson"] = bool(self.poisson_check.isChecked())
        # input/exp
        c["experiment"]["seed"] = int(self.seed_spin.value())
        c["experiment"]["duration_s"] = float(self.duration_spin.value())
        c["experiment"]["input_mode"] = self.input_combo.currentText()
        c["experiment"]["video_path"] = self.video_path_edit.text().strip()
        self.configApplied.emit(c)
        self.accept()
