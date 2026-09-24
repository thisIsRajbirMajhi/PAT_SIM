from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget, QLabel, QComboBox, QDoubleSpinBox, QSpinBox,
                             QSlider, QCheckBox, QPushButton, QFormLayout, QGroupBox, QLineEdit, QFileDialog, QMessageBox)
from PyQt5.QtCore import Qt, pyqtSignal
from ..config.loader import load_config

class ControlDeck(QDialog):
    configApplied = pyqtSignal(dict)

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Control Deck  —  FSOC Tracker")
        self.resize(620, 780)
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
        # Discover presets from configs/*.yaml — P01..P12 from Preset Plan.md
        import os, glob, yaml
        preset_files = sorted(glob.glob(os.path.join("configs", "*.yaml")))
        self._preset_map = {}
        self._preset_meta_map = {}
        display_names = []
        for pf in preset_files:
            base = os.path.splitext(os.path.basename(pf))[0]
            # Pretty: P01_clean_baseline -> P01 - Clean Baseline
            if base.startswith("P") and "_" in base:
                # Split Pxx prefix
                prefix = base[:3]  # P01
                rest = base[4:] if len(base) > 4 else base[3:]
                pretty = f"{prefix} - {rest.replace('_',' ').title()}"
            else:
                pretty = base.replace("_", " ").title()
            self._preset_map[pretty] = pf
            display_names.append(pretty)
            # Try to read preset_meta for description
            try:
                with open(pf) as fh:
                    data = yaml.safe_load(fh) or {}
                self._preset_meta_map[pretty] = data.get("preset_meta", {})
            except:
                self._preset_meta_map[pretty] = {}
        # Ensure built-ins are present even if files missing (legacy)
        for builtin in ["Clean Baseline","High Noise","Platform Jitter","Low Light / Fog","Stars Vignetting","Multi Target","Benchmark Video"]:
            if builtin not in display_names:
                display_names.append(builtin)
        if "Custom" not in display_names:
            display_names.append("Custom")
        self.preset_combo = QComboBox()
        self.preset_combo.addItems(display_names)
        # Default to P01 Clean Baseline if available
        try:
            for cand in ["P01 - Clean Baseline", "P01 — Clean Baseline", "Clean Baseline"]:
                if cand in display_names:
                    self.preset_combo.setCurrentIndex(display_names.index(cand))
                    break
        except:
            pass
        self.preset_desc = QLabel("Preset loads full Sr.1-15 + disturbances + environment. Click Load then Apply.")
        self.preset_desc.setWordWrap(True)
        self.preset_desc.setStyleSheet("color:#64748b; font-size:10px;")
        self.preset_expected = QLabel("")
        self.preset_expected.setWordWrap(True)
        self.preset_expected.setStyleSheet("color:#0f172a; font-size:10px; background:#f1f5f9; padding:4px; border-radius:4px;")
        self.preset_expected.hide()
        self.seed_spin = QSpinBox(); self.seed_spin.setRange(0,999999); self.seed_spin.setValue(self.cfg["experiment"]["seed"])
        self.duration_spin = QDoubleSpinBox(); self.duration_spin.setRange(5,600); self.duration_spin.setValue(self.cfg["experiment"]["duration_s"])
        self.btn_load_preset = QPushButton("Load Preset")
        self.btn_save_preset = QPushButton("Save As…")
        self.btn_save_preset.setToolTip("Save current Control Deck values to a new YAML in configs/")
        h = QHBoxLayout(); h.addWidget(self.btn_load_preset); h.addWidget(self.btn_save_preset)
        f.addRow("Preset", self.preset_combo)
        f.addRow("", self.preset_desc)
        f.addRow("", self.preset_expected)
        f.addRow("", h)
        f.addRow("Random Seed", self.seed_spin)
        f.addRow("Duration (s)", self.duration_spin)
        self.preset_info = QLabel("Includes: World, Camera (Type/Res/FOV/FPS/Init/Pan-Tilt), Target (Count/Shape/Size/Init/Motion), Disturbances (Noise/Jitter/Atmosphere/Platform), Environment (Gradient/Stars/Vignetting/Brightness)")
        self.preset_info.setWordWrap(True)
        self.preset_info.setStyleSheet("color:#64748b; font-size:9px; font-style:italic;")
        f.addRow(self.preset_info)
        # Quick-run row: run order hint
        self.preset_order = QLabel("Order: P01 baseline first, then P02–P04 motion, P05–P07 detection, P08–P09 disturbances, P10–P11 acquisition, P12 video.")
        self.preset_order.setWordWrap(True)
        self.preset_order.setStyleSheet("color:#64748b; font-size:9px;")
        f.addRow(self.preset_order)
        self.btn_load_preset.clicked.connect(self._load_preset)
        self.btn_save_preset.clicked.connect(self._save_preset)
        self.preset_combo.currentTextChanged.connect(self._on_preset_selected)
        self._on_preset_selected(self.preset_combo.currentText())
        return w

    def _on_preset_selected(self, name):
        import os, yaml
        pf = self._preset_map.get(name, None)
        meta = getattr(self, "_preset_meta_map", {}).get(name, {})
        if pf and os.path.exists(pf):
            purpose = meta.get("purpose", "")
            expected = meta.get("expected", {})
            exp_str = ", ".join([f"{k} {v}" for k,v in expected.items()]) if expected else ""
            try:
                self.preset_desc.setText(f"File: {pf}" + (f" — {purpose}" if purpose else " — loads on 'Load Preset'."))
            except:
                self.preset_desc.setText(f"File: {pf}")
            if exp_str:
                self.preset_expected.setText(f"Expected: {exp_str}")
                self.preset_expected.show()
            else:
                # Try read header comments for purpose if no meta
                try:
                    with open(pf) as f:
                        lines = [next(f) for _ in range(5)]
                    hdr = " ".join([l.strip("# ").strip() for l in lines if l.startswith("#")])
                    if hdr and len(hdr) > 10:
                        self.preset_expected.setText(hdr[:220])
                        self.preset_expected.show()
                    else:
                        self.preset_expected.hide()
                except:
                    self.preset_expected.hide()
        elif name == "Custom":
            self.preset_desc.setText("Custom: current deck values. Save As to create new preset.")
            self.preset_expected.hide()
        else:
            self.preset_desc.setText(f"Built-in preset: {name} — staged, click Load.")
            self.preset_expected.hide()

    def _load_preset(self):
        name = self.preset_combo.currentText()
        import os, copy
        pf = self._preset_map.get(name)
        try:
            if pf and os.path.exists(pf):
                from ..config.loader import load_config
                new_cfg = load_config(pf)
                self.cfg = new_cfg
                self._refresh_all_fields()
                meta = getattr(self, "_preset_meta_map", {}).get(name, {})
                exp = meta.get("expected", {})
                exp_str = ", ".join([f"{k} {v}" for k,v in exp.items()]) if exp else ""
                msg = f"Loaded {pf}\nAll 7 tabs updated. Click Apply to commit to simulator."
                if exp_str:
                    msg += f"\n\nExpected: {exp_str}"
                # Also show purpose header if available
                try:
                    with open(pf) as fh:
                        first = fh.readline().strip()
                    if first.startswith("#"):
                        msg = first.strip("# ").strip() + "\n\n" + msg
                except:
                    pass
                QMessageBox.information(self,"Preset Loaded", msg)
                return
            # Fallback built-ins (for backward compat if file missing)
            if name=="Clean Baseline":
                self._set_fields(atmo="clear", gauss=0, spp=0, jitter=0, platform="none")
            elif name=="High Noise":
                self._set_fields(atmo="clear", gauss=12, spp=0.02, jitter=6, platform="linear")
            elif name=="Platform Jitter":
                self._set_fields(atmo="clear", gauss=4, spp=0, jitter=14, platform="linear")
            elif name=="Low Light / Fog":
                self._set_fields(atmo="fog", gauss=5, spp=0, jitter=4, platform="none")
            elif name=="Stars Vignetting":
                # Toggle stars/vignetting via cfg then refresh
                self.cfg["environment"]["stars_enabled"] = True
                self.cfg["environment"]["vignetting_enabled"] = True
                self.cfg["environment"]["gradient_enabled"] = True
                self._refresh_all_fields()
            elif name=="Multi Target":
                self.cfg["target"]["count"] = 3
                self._refresh_all_fields()
            elif name=="Benchmark Video":
                self.cfg["experiment"]["input_mode"] = "VIDEO"
                self.cfg["experiment"]["video_path"] = "data/input_videos/test_beacon.mp4"
                self._refresh_all_fields()
            QMessageBox.information(self,"Preset","Preset fields staged. Click Apply to commit.")
        except Exception as e:
            QMessageBox.warning(self,"Preset Load Failed", str(e))

    def _refresh_all_fields(self):
        """Re-populate every widget from self.cfg (called after loading a preset). Called before Apply so user sees values."""
        try:
            # Experiment
            self.seed_spin.setValue(int(self.cfg["experiment"].get("seed",42)))
            self.duration_spin.setValue(float(self.cfg["experiment"].get("duration_s",30)))
            # Target
            self.tgt_type_combo.setCurrentText(self.cfg["target"].get("type","beacon_spot"))
            self.tgt_count_spin.setValue(int(self.cfg["target"].get("count",1)))
            self.tgt_shape_combo.setCurrentText(self.cfg["target"].get("shape","square"))
            self.size_spin.setValue(int(self.cfg["target"].get("size",10)))
            self.tgt_init_mode_combo.setCurrentText(self.cfg["target"].get("initial_mode","random"))
            ip = self.cfg["target"].get("initial_pos")
            if ip and len(ip)==2:
                self.tgt_init_x_spin.setValue(int(ip[0])); self.tgt_init_y_spin.setValue(int(ip[1]))
            self.traj_combo.setCurrentText(self.cfg["target"].get("trajectory","circular"))
            self.custom_traj_edit.setText(self.cfg["target"].get("custom_trajectory_file","") or "")
            # Custom polygon
            poly = self.cfg["target"].get("custom_polygon")
            if poly:
                self.custom_polygon_edit.setText("; ".join([f"{x},{y}" for x,y in poly]))
            else:
                self.custom_polygon_edit.clear()
            self.speed_spin.setValue(float(self.cfg["target"].get("speed_px_per_frame",2.8)))
            self.angle_spin.setValue(float(self.cfg["target"].get("angle_deg",30)))
            self.radius_spin.setValue(float(self.cfg["target"].get("radius",180)))
            # Camera
            self.cam_type_combo.setCurrentText(self.cfg["camera"].get("type","monochrome"))
            self.res_w_spin.setValue(int(self.cfg["camera"]["resolution"][0]))
            self.res_h_spin.setValue(int(self.cfg["camera"]["resolution"][1]))
            self.fov_h_spin.setValue(float(self.cfg["camera"]["fov_deg"][0]))
            self.fov_v_spin.setValue(float(self.cfg["camera"]["fov_deg"][1]))
            self.fps_spin.setValue(int(self.cfg["camera"].get("fps",30)))
            self.cam_init_combo.setCurrentText(self.cfg["camera"].get("initial_position","centre"))
            self.cam_init_pan_spin.setValue(float(self.cfg["camera"].get("initial_pan",0)))
            self.cam_init_tilt_spin.setValue(float(self.cfg["camera"].get("initial_tilt",0)))
            self.max_pan_spin.setValue(float(self.cfg["camera"].get("max_pan_speed",5)))
            self.max_tilt_spin.setValue(float(self.cfg["camera"].get("max_tilt_speed",5)))
            self.update_hz_spin.setValue(int(self.cfg["camera"].get("update_interval_hz",30)))
            self.jitter_spin.setValue(float(self.cfg["camera"].get("jitter_px",0)))
            # Environment
            self.world_w_spin.setValue(int(self.cfg["world"]["width"]))
            self.world_h_spin.setValue(int(self.cfg["world"]["height"]))
            self.world_bg_spin.setValue(int(self.cfg["world"].get("background",18)))
            self.platform_combo.setCurrentText(self.cfg["platform"].get("type","none"))
            self.platform_speed_spin.setValue(float(self.cfg["platform"].get("speed_px_per_frame",0)))
            env = self.cfg.get("environment",{})
            self.grad_enabled.setChecked(bool(env.get("gradient_enabled",False)))
            self.grad_type_combo.setCurrentText(env.get("gradient_type","linear"))
            self.grad_top_spin.setValue(int(env.get("gradient_top",22)))
            self.grad_bottom_spin.setValue(int(env.get("gradient_bottom",38)))
            self.grad_angle_spin.setValue(int(env.get("gradient_angle",90)))
            self.stars_enabled.setChecked(bool(env.get("stars_enabled",False)))
            self.stars_density_spin.setValue(float(env.get("stars_density",0.0007)))
            self.stars_brightness_spin.setValue(int(env.get("stars_brightness",185)))
            self.stars_minmag_spin.setValue(int(env.get("stars_min_mag",90)))
            self.stars_maxmag_spin.setValue(int(env.get("stars_max_mag",255)))
            self.stars_twinkle_check.setChecked(bool(env.get("stars_twinkle",False)))
            self.stars_seed_spin.setValue(int(env.get("stars_seed",1337)))
            self.vig_enabled.setChecked(bool(env.get("vignetting_enabled",False)))
            self.vig_strength_spin.setValue(float(env.get("vignetting_strength",0.42)))
            self.vig_radius_spin.setValue(float(env.get("vignetting_radius",0.72)))
            self.vig_falloff_spin.setValue(float(env.get("vignetting_falloff",2.0)))
            self.vig_cx_spin.setValue(float(env.get("vignetting_center_x",0.5)))
            self.vig_cy_spin.setValue(float(env.get("vignetting_center_y",0.5)))
            self.bright_gain_spin.setValue(float(env.get("brightness_gain",1.0)))
            self.bright_offset_spin.setValue(int(env.get("brightness_offset",0)))
            # Disturbances
            self.atmo_combo.setCurrentText(self.cfg["atmosphere"].get("type","clear"))
            self.atmo_strength.setValue(float(self.cfg["atmosphere"].get("strength",0)))
            self.gauss_check.setChecked(bool(self.cfg["noise"].get("gaussian_enabled",False)))
            self.gauss_spin.setValue(float(self.cfg["noise"].get("gaussian_std",0)))
            self.spp_check.setChecked(bool(self.cfg["noise"].get("salt_pepper_enabled",False)))
            self.spp_spin.setValue(float(self.cfg["noise"].get("salt_pepper_prob",0)))
            self.poisson_check.setChecked(bool(self.cfg["noise"].get("poisson",False)))
            # Input
            self.input_combo.setCurrentText(self.cfg["experiment"].get("input_mode","SYNTHETIC"))
            self.video_path_edit.setText(self.cfg["experiment"].get("video_path",""))
            self.vid_centre_x_spin.setValue(float(self.cfg["camera"].get("video_centre_offset_x",0)))
            self.vid_centre_y_spin.setValue(float(self.cfg["camera"].get("video_centre_offset_y",0)))
        except Exception as e:
            print(f"[ControlDeck] _refresh_all_fields failed: {e}")

    def _save_preset(self):
        path,_ = QFileDialog.getSaveFileName(self, "Save Preset YAML", "configs/my_preset.yaml", "YAML (*.yaml *.yml)")
        if not path:
            return
        try:
            # Build cfg from current UI (without emitting) then save
            # Temporarily build a copy
            import copy, yaml, os
            # Force _apply logic but not emit
            tmp_cfg = copy.deepcopy(self.cfg)
            # Re-use _apply code path to fill tmp_cfg from widgets (duplicate logic)
            # Instead, just save current self.cfg as is (which was last loaded) — user should Apply first for latest UI
            # So we first sync UI to tmp_cfg
            self._apply_to_cfg(tmp_cfg)
            with open(path, "w") as f:
                yaml.safe_dump(tmp_cfg, f, sort_keys=False)
            QMessageBox.information(self,"Saved", f"Preset saved to {path}\nIt will appear in the Preset combo on next open.")
        except Exception as e:
            QMessageBox.warning(self,"Save Failed", str(e))

    def _apply_to_cfg(self, c):
        # Helper to sync current UI widgets into a cfg dict (used by Save As)
        try:
            c["target"]["type"] = self.tgt_type_combo.currentText()
            c["target"]["count"] = int(self.tgt_count_spin.value())
            c["target"]["shape"] = self.tgt_shape_combo.currentText()
            c["target"]["size"] = int(self.size_spin.value())
            mode = self.tgt_init_mode_combo.currentText()
            c["target"]["initial_mode"] = mode
            if mode == "random":
                c["target"]["initial_pos"] = None
            elif mode == "centre":
                c["target"]["initial_pos"] = [int(c["world"]["width"]//2), int(c["world"]["height"]//2)]
            else:
                c["target"]["initial_pos"] = [int(self.tgt_init_x_spin.value()), int(self.tgt_init_y_spin.value())]
            c["target"]["trajectory"] = self.traj_combo.currentText()
            c["target"]["speed_px_per_frame"] = float(self.speed_spin.value())
            c["target"]["angle_deg"] = float(self.angle_spin.value())
            c["target"]["radius"] = float(self.radius_spin.value())
            if c["target"]["shape"] == "user-defined":
                txt = self.custom_polygon_edit.text().strip()
                if txt:
                    pts = []
                    for part in txt.split(";"):
                        part=part.strip()
                        if not part: continue
                        x_str,y_str = part.split(",")
                        pts.append([int(float(x_str.strip())), int(float(y_str.strip()))])
                    c["target"]["custom_polygon"] = pts if len(pts)>=3 else None
                else:
                    c["target"]["custom_polygon"] = None
            else:
                c["target"]["custom_polygon"] = None
            if c["target"]["trajectory"] == "user-defined":
                c["target"]["custom_trajectory_file"] = self.custom_traj_edit.text().strip() or None
            else:
                c["target"]["custom_trajectory_file"] = None
        except Exception:
            pass

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
        # Target Type
        self.tgt_type_combo = QComboBox(); self.tgt_type_combo.addItems(["beacon_spot"]); self.tgt_type_combo.setCurrentText(self.cfg["target"].get("type","beacon_spot"))
        # Number of Targets 1 mandatory, 1-5 optional multiple (independent trajectories)
        self.tgt_count_spin = QSpinBox(); self.tgt_count_spin.setRange(1,5); self.tgt_count_spin.setValue(int(self.cfg["target"].get("count",1)))
        # Shape user-defined default Square + custom polygon support
        self.tgt_shape_combo = QComboBox(); self.tgt_shape_combo.addItems(["square","circle","gaussian","cross","user-defined"]); self.tgt_shape_combo.setCurrentText(self.cfg["target"].get("shape","square"))
        self.custom_polygon_edit = QLineEdit(); self.custom_polygon_edit.setPlaceholderText("e.g., -5,-5; 5,-5; 5,5; -5,5  or leave empty for 5-point star")
        # Load existing custom polygon if any
        existing_poly = self.cfg["target"].get("custom_polygon")
        if existing_poly and isinstance(existing_poly, list):
            self.custom_polygon_edit.setText("; ".join([f"{x},{y}" for x,y in existing_poly]))
        self.btn_polygon_file = QPushButton("Load Polygon File…")
        poly_hbox = QHBoxLayout(); poly_hbox.addWidget(self.custom_polygon_edit); poly_hbox.addWidget(self.btn_polygon_file)
        # Size 5-20 default 10
        self.size_spin = QSpinBox(); self.size_spin.setRange(5,20); self.size_spin.setValue(int(self.cfg["target"]["size"]))
        # Initial Location user-defined default Random
        self.tgt_init_mode_combo = QComboBox(); self.tgt_init_mode_combo.addItems(["random","centre","user-defined"]); self.tgt_init_mode_combo.setCurrentText(self.cfg["target"].get("initial_mode","random"))
        init_pos = self.cfg["target"].get("initial_pos")
        init_x = init_pos[0] if (init_pos and len(init_pos)==2) else 1000
        init_y = init_pos[1] if (init_pos and len(init_pos)==2) else 1000
        self.tgt_init_x_spin = QSpinBox(); self.tgt_init_x_spin.setRange(0,4000); self.tgt_init_x_spin.setValue(int(init_x))
        self.tgt_init_y_spin = QSpinBox(); self.tgt_init_y_spin.setRange(0,4000); self.tgt_init_y_spin.setValue(int(init_y))
        # Motion at least 4: straight, circular, figure_eight, random + optional spiral, sinusoidal, user-defined (CSV)
        self.traj_combo = QComboBox(); self.traj_combo.addItems(["straight","circular","figure_eight","random","spiral","sinusoidal","user-defined"])
        self.traj_combo.setCurrentText(self.cfg["target"]["trajectory"])
        self.custom_traj_edit = QLineEdit(); self.custom_traj_edit.setPlaceholderText("CSV path: x,y per row  or  t,x,y")
        self.custom_traj_edit.setText(self.cfg["target"].get("custom_trajectory_file", ""))
        self.btn_traj_file = QPushButton("Browse…")
        traj_hbox = QHBoxLayout(); traj_hbox.addWidget(self.custom_traj_edit); traj_hbox.addWidget(self.btn_traj_file)
        self.speed_spin = QDoubleSpinBox(); self.speed_spin.setRange(0,20); self.speed_spin.setSingleStep(0.5); self.speed_spin.setValue(float(self.cfg["target"]["speed_px_per_frame"]))
        self.angle_spin = QDoubleSpinBox(); self.angle_spin.setRange(0,360); self.angle_spin.setValue(float(self.cfg["target"].get("angle_deg",30)))
        self.radius_spin = QDoubleSpinBox(); self.radius_spin.setRange(50,800); self.radius_spin.setValue(float(self.cfg["target"].get("radius",400)))
        f.addRow("Target Type", self.tgt_type_combo)
        f.addRow("Target Count", self.tgt_count_spin)
        f.addRow("Target Shape", self.tgt_shape_combo)
        f.addRow("Custom Polygon", poly_hbox)
        f.addRow("Target Size", self.size_spin)
        f.addRow("Initial Position Mode", self.tgt_init_mode_combo)
        f.addRow("  Init X", self.tgt_init_x_spin); f.addRow("  Init Y", self.tgt_init_y_spin)
        f.addRow("Motion Trajectory", self.traj_combo)
        f.addRow("Custom Trajectory CSV", traj_hbox)
        f.addRow("Speed (px/frame)", self.speed_spin)
        f.addRow("Angle (straight)", self.angle_spin)
        f.addRow("Radius (circular/8)", self.radius_spin)
        # Show/hide custom rows based on selection
        def _update_target_custom_rows():
            is_user_shape = self.tgt_shape_combo.currentText() == "user-defined"
            self.custom_polygon_edit.setVisible(is_user_shape)
            self.btn_polygon_file.setVisible(is_user_shape)
            is_user_traj = self.traj_combo.currentText() == "user-defined"
            self.custom_traj_edit.setVisible(is_user_traj)
            self.btn_traj_file.setVisible(is_user_traj)
        self.tgt_shape_combo.currentTextChanged.connect(lambda _: _update_target_custom_rows())
        self.traj_combo.currentTextChanged.connect(lambda _: _update_target_custom_rows())
        self.btn_polygon_file.clicked.connect(self._browse_polygon)
        self.btn_traj_file.clicked.connect(self._browse_traj)
        _update_target_custom_rows()
        return w

    def _browse_polygon(self):
        p,_ = QFileDialog.getOpenFileName(self, "Load custom polygon (JSON or CSV: x,y per row)", "", "JSON (*.json);;CSV (*.csv);;All (*.*)")
        if p:
            try:
                import json, csv, os
                if p.lower().endswith(".json"):
                    with open(p) as f:
                        data = json.load(f)
                        # expect list of [x,y]
                        if isinstance(data, list) and len(data) > 0:
                            self.custom_polygon_edit.setText("; ".join([f"{x},{y}" for x,y in data]))
                else:
                    # CSV: x,y per row
                    pts = []
                    with open(p, newline='') as f:
                        reader = csv.reader(f)
                        for row in reader:
                            if not row or row[0].strip().startswith('#'):
                                continue
                            vals = [v.strip() for v in row if v.strip()!='']
                            if len(vals) >= 2:
                                pts.append(f"{vals[0]},{vals[1]}")
                    self.custom_polygon_edit.setText("; ".join(pts))
            except Exception as e:
                QMessageBox.warning(self, "Polygon load failed", str(e))

    def _browse_traj(self):
        p,_ = QFileDialog.getOpenFileName(self, "Load custom trajectory CSV (x,y or t,x,y per row)", "", "CSV (*.csv);;All (*.*)")
        if p:
            self.custom_traj_edit.setText(p)

    def _camera_tab(self):
        w = QWidget(); f = QFormLayout(w)
        # Camera Type
        self.cam_type_combo = QComboBox(); self.cam_type_combo.addItems(["monochrome","colour"]); self.cam_type_combo.setCurrentText(self.cfg["camera"].get("type","monochrome"))
        # Resolution 640x480 default, 320-1920 user-defined
        self.res_w_spin = QSpinBox(); self.res_w_spin.setRange(320,1920); self.res_w_spin.setValue(int(self.cfg["camera"]["resolution"][0]))
        self.res_h_spin = QSpinBox(); self.res_h_spin.setRange(240,1080); self.res_h_spin.setValue(int(self.cfg["camera"]["resolution"][1]))
        # FOV user-defined default 4x3, range 1-12° — with live preview of footprint
        self.fov_h_spin = QDoubleSpinBox(); self.fov_h_spin.setRange(1,12); self.fov_h_spin.setValue(float(self.cfg["camera"]["fov_deg"][0]))
        self.fov_v_spin = QDoubleSpinBox(); self.fov_v_spin.setRange(1,12); self.fov_v_spin.setValue(float(self.cfg["camera"]["fov_deg"][1]))
        # Camera update Rate 30 Hz min, range 20-60
        self.fps_spin = QSpinBox(); self.fps_spin.setRange(30,60); self.fps_spin.setValue(int(self.cfg["camera"].get("fps",30)))
        # Initial Camera Position Centre (default) / user-defined
        self.cam_init_combo = QComboBox(); self.cam_init_combo.addItems(["centre","user-defined"]); self.cam_init_combo.setCurrentText(self.cfg["camera"].get("initial_position","centre"))
        self.cam_init_pan_spin = QDoubleSpinBox(); self.cam_init_pan_spin.setRange(-10,10); self.cam_init_pan_spin.setValue(float(self.cfg["camera"].get("initial_pan",0.0)))
        self.cam_init_tilt_spin = QDoubleSpinBox(); self.cam_init_tilt_spin.setRange(-10,10); self.cam_init_tilt_spin.setValue(float(self.cfg["camera"].get("initial_tilt",0.0)))
        # /14 Max Pan/Tilt 5-10 °/s default 5
        self.max_pan_spin = QDoubleSpinBox(); self.max_pan_spin.setRange(5,10); self.max_pan_spin.setSingleStep(0.5); self.max_pan_spin.setValue(float(self.cfg["camera"]["max_pan_speed"]))
        self.max_tilt_spin = QDoubleSpinBox(); self.max_tilt_spin.setRange(5,10); self.max_tilt_spin.setSingleStep(0.5); self.max_tilt_spin.setValue(float(self.cfg["camera"]["max_tilt_speed"]))
        # Update Interval ≥20 Hz
        self.update_hz_spin = QSpinBox(); self.update_hz_spin.setRange(20,60); self.update_hz_spin.setValue(int(self.cfg["camera"].get("update_interval_hz", self.cfg["camera"].get("fps",30))))
        self.jitter_spin = QDoubleSpinBox(); self.jitter_spin.setRange(0,20); self.jitter_spin.setValue(float(self.cfg["camera"]["jitter_px"]))
        f.addRow("Camera Type", self.cam_type_combo)
        f.addRow("Resolution Width", self.res_w_spin); f.addRow("Resolution Height", self.res_h_spin)
        f.addRow("Horizontal FOV", self.fov_h_spin); f.addRow("Vertical FOV", self.fov_v_spin)
        f.addRow("Frame Rate", self.fps_spin); f.addRow("Update Rate", self.update_hz_spin)
        f.addRow("Initial Camera Position", self.cam_init_combo); f.addRow("Initial Pan Angle", self.cam_init_pan_spin); f.addRow("Initial Tilt Angle", self.cam_init_tilt_spin)
        f.addRow("Maximum Pan Speed", self.max_pan_spin); f.addRow("Maximum Tilt Speed", self.max_tilt_spin)
        f.addRow("Jitter ±20 px/frame", self.jitter_spin)
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
        # Scrollable Environment tab with Gradient / Stars / Vignetting / Brightness
        from PyQt5.QtWidgets import QScrollArea, QGroupBox
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        outer = QWidget(); outer_lay = QVBoxLayout(outer); outer_lay.setContentsMargins(6,6,6,6); outer_lay.setSpacing(10)
        env = self.cfg.get("environment", {})

        # --- World & Platform ---
        grp_world = QGroupBox("World & Platform")
        f = QFormLayout(grp_world)
        self.world_w_spin = QSpinBox(); self.world_w_spin.setRange(2000,4000); self.world_w_spin.setValue(int(self.cfg["world"]["width"]))
        self.world_h_spin = QSpinBox(); self.world_h_spin.setRange(2000,4000); self.world_h_spin.setValue(int(self.cfg["world"]["height"]))
        self.world_bg_spin = QSpinBox(); self.world_bg_spin.setRange(0,60); self.world_bg_spin.setValue(int(self.cfg["world"].get("background",18)))
        self.platform_combo = QComboBox(); self.platform_combo.addItems(["none","linear","circular","random","spiral","figure_of_8"])
        self.platform_combo.setCurrentText(self.cfg["platform"]["type"])
        self.platform_speed_spin = QDoubleSpinBox(); self.platform_speed_spin.setRange(0,20); self.platform_speed_spin.setSingleStep(0.5); self.platform_speed_spin.setValue(float(self.cfg["platform"]["speed_px_per_frame"]))
        f.addRow("World Width", self.world_w_spin); f.addRow("World Height", self.world_h_spin); f.addRow("Background Intensity", self.world_bg_spin)
        f.addRow("Platform Type", self.platform_combo); f.addRow("Platform Speed", self.platform_speed_spin)
        outer_lay.addWidget(grp_world)

        # --- Gradient ---
        grp_grad = QGroupBox("Background Gradient")
        grp_grad.setCheckable(True)
        grp_grad.setChecked(bool(env.get("gradient_enabled", False)))
        self.grad_enabled = grp_grad
        fg = QFormLayout(grp_grad)
        self.grad_type_combo = QComboBox(); self.grad_type_combo.addItems(["linear","radial","diagonal"])
        self.grad_type_combo.setCurrentText(env.get("gradient_type","linear"))
        self.grad_top_spin = QSpinBox(); self.grad_top_spin.setRange(0,80); self.grad_top_spin.setValue(int(env.get("gradient_top",22)))
        self.grad_bottom_spin = QSpinBox(); self.grad_bottom_spin.setRange(0,80); self.grad_bottom_spin.setValue(int(env.get("gradient_bottom",38)))
        self.grad_angle_spin = QSpinBox(); self.grad_angle_spin.setRange(0,360); self.grad_angle_spin.setValue(int(env.get("gradient_angle",90)))
        fg.addRow("Type", self.grad_type_combo); fg.addRow("Top intensity", self.grad_top_spin); fg.addRow("Bottom intensity", self.grad_bottom_spin); fg.addRow("Angle °", self.grad_angle_spin)
        outer_lay.addWidget(grp_grad)

        # --- Stars ---
        grp_stars = QGroupBox("Stars Clutter")
        grp_stars.setCheckable(True)
        grp_stars.setChecked(bool(env.get("stars_enabled", False)))
        self.stars_enabled = grp_stars
        fs = QFormLayout(grp_stars)
        self.stars_density_spin = QDoubleSpinBox(); self.stars_density_spin.setRange(0.0,0.006); self.stars_density_spin.setSingleStep(0.0001); self.stars_density_spin.setDecimals(4); self.stars_density_spin.setValue(float(env.get("stars_density",0.0007)))
        self.stars_brightness_spin = QSpinBox(); self.stars_brightness_spin.setRange(60,255); self.stars_brightness_spin.setValue(int(env.get("stars_brightness",185)))
        self.stars_minmag_spin = QSpinBox(); self.stars_minmag_spin.setRange(40,200); self.stars_minmag_spin.setValue(int(env.get("stars_min_mag",90)))
        self.stars_maxmag_spin = QSpinBox(); self.stars_maxmag_spin.setRange(100,255); self.stars_maxmag_spin.setValue(int(env.get("stars_max_mag",255)))
        self.stars_twinkle_check = QCheckBox("Twinkle (per-frame ±6)")
        self.stars_twinkle_check.setChecked(bool(env.get("stars_twinkle", False)))
        self.stars_seed_spin = QSpinBox(); self.stars_seed_spin.setRange(0,999999); self.stars_seed_spin.setValue(int(env.get("stars_seed",1337)))
        fs.addRow("Density (stars/px)", self.stars_density_spin); fs.addRow("Overall brightness", self.stars_brightness_spin)
        fs.addRow("Min mag", self.stars_minmag_spin); fs.addRow("Max mag", self.stars_maxmag_spin)
        fs.addRow(self.stars_twinkle_check); fs.addRow("Stars seed", self.stars_seed_spin)
        outer_lay.addWidget(grp_stars)

        # --- Vignetting ---
        grp_vig = QGroupBox("Vignetting (lens falloff)")
        grp_vig.setCheckable(True)
        grp_vig.setChecked(bool(env.get("vignetting_enabled", False)))
        self.vig_enabled = grp_vig
        fv = QFormLayout(grp_vig)
        self.vig_strength_spin = QDoubleSpinBox(); self.vig_strength_spin.setRange(0.0,0.95); self.vig_strength_spin.setSingleStep(0.05); self.vig_strength_spin.setValue(float(env.get("vignetting_strength",0.42)))
        self.vig_radius_spin = QDoubleSpinBox(); self.vig_radius_spin.setRange(0.05,1.0); self.vig_radius_spin.setSingleStep(0.05); self.vig_radius_spin.setValue(float(env.get("vignetting_radius",0.72)))
        self.vig_falloff_spin = QDoubleSpinBox(); self.vig_falloff_spin.setRange(0.3,6.0); self.vig_falloff_spin.setSingleStep(0.2); self.vig_falloff_spin.setValue(float(env.get("vignetting_falloff",2.0)))
        self.vig_cx_spin = QDoubleSpinBox(); self.vig_cx_spin.setRange(0.0,1.0); self.vig_cx_spin.setSingleStep(0.05); self.vig_cx_spin.setValue(float(env.get("vignetting_center_x",0.5)))
        self.vig_cy_spin = QDoubleSpinBox(); self.vig_cy_spin.setRange(0.0,1.0); self.vig_cy_spin.setSingleStep(0.05); self.vig_cy_spin.setValue(float(env.get("vignetting_center_y",0.5)))
        fv.addRow("Strength", self.vig_strength_spin); fv.addRow("Radius", self.vig_radius_spin); fv.addRow("Falloff", self.vig_falloff_spin)
        fv.addRow("Center X", self.vig_cx_spin); fv.addRow("Center Y", self.vig_cy_spin)
        outer_lay.addWidget(grp_vig)

        # --- Brightness ---
        grp_bright = QGroupBox("Global Brightness")
        fb = QFormLayout(grp_bright)
        self.bright_gain_spin = QDoubleSpinBox(); self.bright_gain_spin.setRange(0.5,1.8); self.bright_gain_spin.setSingleStep(0.05); self.bright_gain_spin.setValue(float(env.get("brightness_gain",1.0)))
        self.bright_offset_spin = QSpinBox(); self.bright_offset_spin.setRange(-40,40); self.bright_offset_spin.setValue(int(env.get("brightness_offset",0)))
        fb.addRow("Gain (×)", self.bright_gain_spin); fb.addRow("Offset (+)", self.bright_offset_spin)
        outer_lay.addWidget(grp_bright)

        outer_lay.addStretch()
        scroll.setWidget(outer)
        return scroll

    def _disturb_tab(self):
        w = QWidget(); f = QFormLayout(w)
        # Image Noise: 1.Salt&Pepper (~10% =0.10), 2.Gaussian, 3.Poisson — selectable one or more
        self.atmo_combo = QComboBox(); self.atmo_combo.addItems(["clear","haze","fog","rain","low_light"])
        self.atmo_combo.setCurrentText(self.cfg["atmosphere"]["type"])
        self.atmo_strength = QDoubleSpinBox(); self.atmo_strength.setRange(0,1); self.atmo_strength.setSingleStep(0.1); self.atmo_strength.setValue(float(self.cfg["atmosphere"]["strength"]))
        # Max Standard Deviation 20 pixels (Gaussian σ)
        self.gauss_spin = QDoubleSpinBox(); self.gauss_spin.setRange(0,20); self.gauss_spin.setSingleStep(1); self.gauss_spin.setValue(float(self.cfg["noise"].get("gaussian_std",0)))
        self.gauss_check = QCheckBox("Enable Gaussian (σ)"); self.gauss_check.setChecked(bool(self.cfg["noise"].get("gaussian_enabled", False)))
        # S&P ~10% of image → 0.10, range 0-0.15
        self.spp_spin = QDoubleSpinBox(); self.spp_spin.setRange(0,0.15); self.spp_spin.setSingleStep(0.01); self.spp_spin.setValue(float(self.cfg["noise"].get("salt_pepper_prob",0)))
        self.spp_check = QCheckBox("Enable Salt & Pepper (~10%)"); self.spp_check.setChecked(bool(self.cfg["noise"].get("salt_pepper_enabled", False)))
        self.poisson_check = QCheckBox("Enable Poisson (3rd)"); self.poisson_check.setChecked(bool(self.cfg["noise"].get("poisson", False)))
        # Max Camera Jitter ±20 is in Camera tab (jitter_px 0-20), reference here
        # Atmospheric already above, Platform in Environment tab (linear default, optional circular/random/spiral/figure_of_8, ±20)
        f.addRow("Image Noise", QLabel("Salt & Pepper, Gaussian, Poisson"))
        f.addRow(self.gauss_check, self.gauss_spin)
        f.addRow("Gaussian Std Deviation", QLabel("Max 20 px"))
        f.addRow(self.spp_check, self.spp_spin)
        f.addRow(self.poisson_check)
        f.addRow("Atmospheric Condition", self.atmo_combo); f.addRow("Atmospheric Strength", self.atmo_strength)
        f.addRow(QLabel("Max Jitter ±20 px/frame → Camera tab")); f.addRow(QLabel("Platform ±20 px/f → Environment tab (Linear def, +Circular/Random/Spiral/Figure-8)"))
        return w

    def _input_tab(self):
        w = QWidget(); f = QFormLayout(w)
        self.input_combo = QComboBox(); self.input_combo.addItems(["SYNTHETIC","VIDEO"]); self.input_combo.setCurrentText(self.cfg["experiment"]["input_mode"])
        self.video_path_edit = QLineEdit(self.cfg["experiment"].get("video_path",""))
        self.btn_browse = QPushButton("Browse…")
        h = QHBoxLayout(); h.addWidget(self.video_path_edit); h.addWidget(self.btn_browse)
        f.addRow("Input mode", self.input_combo)
        f.addRow("Video path", h)
        # Video centre calibration (for external mp4 where image centre may be offset)
        self.vid_centre_x_spin = QDoubleSpinBox(); self.vid_centre_x_spin.setRange(-100,100); self.vid_centre_x_spin.setSingleStep(1); self.vid_centre_x_spin.setValue(float(self.cfg["camera"].get("video_centre_offset_x",0)))
        self.vid_centre_y_spin = QDoubleSpinBox(); self.vid_centre_y_spin.setRange(-100,100); self.vid_centre_y_spin.setSingleStep(1); self.vid_centre_y_spin.setValue(float(self.cfg["camera"].get("video_centre_offset_y",0)))
        f.addRow("Video centre offset X (px)", self.vid_centre_x_spin)
        f.addRow("Video centre offset Y (px)", self.vid_centre_y_spin)
        f.addRow(QLabel("Calibrates image centre for mp4 input (0,0 = frame centre)"))
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
        # target — c["target"]["type"] = self.tgt_type_combo.currentText()
        c["target"]["count"] = int(self.tgt_count_spin.value())
        c["target"]["shape"] = self.tgt_shape_combo.currentText()
        c["target"]["size"] = int(self.size_spin.value())
        # initial location
        mode = self.tgt_init_mode_combo.currentText()
        c["target"]["initial_mode"] = mode
        if mode == "random":
            c["target"]["initial_pos"] = None
        elif mode == "centre":
            c["target"]["initial_pos"] = [int(c["world"]["width"]//2), int(c["world"]["height"]//2)]
        else: # user-defined
            c["target"]["initial_pos"] = [int(self.tgt_init_x_spin.value()), int(self.tgt_init_y_spin.value())]
        c["target"]["trajectory"] = self.traj_combo.currentText()
        c["target"]["speed_px_per_frame"] = float(self.speed_spin.value())
        c["target"]["angle_deg"] = float(self.angle_spin.value())
        c["target"]["radius"] = float(self.radius_spin.value())
        # User-defined shape: custom polygon
        if c["target"]["shape"] == "user-defined":
            txt = self.custom_polygon_edit.text().strip()
            if txt:
                try:
                    pts = []
                    for part in txt.split(";"):
                        part = part.strip()
                        if not part:
                            continue
                        x_str, y_str = part.split(",")
                        pts.append([int(float(x_str.strip())), int(float(y_str.strip()))])
                    c["target"]["custom_polygon"] = pts if len(pts) >= 3 else None
                except Exception:
                    c["target"]["custom_polygon"] = None
            else:
                c["target"]["custom_polygon"] = None  # default 5-point star in World
        else:
            c["target"]["custom_polygon"] = None
        # User-defined trajectory: custom CSV file
        if c["target"]["trajectory"] == "user-defined":
            c["target"]["custom_trajectory_file"] = self.custom_traj_edit.text().strip() or None
            c["target"]["custom_trajectory_path"] = c["target"]["custom_trajectory_file"]
        else:
            c["target"]["custom_trajectory_file"] = None
            c["target"]["custom_trajectory_path"] = None
        # camera — ,13-15
        c["camera"]["type"] = self.cam_type_combo.currentText()
        c["camera"]["resolution"] = [int(self.res_w_spin.value()), int(self.res_h_spin.value())]
        c["camera"]["fov_deg"] = [float(self.fov_h_spin.value()), float(self.fov_v_spin.value())]
        c["camera"]["fps"] = int(self.fps_spin.value())
        c["camera"]["initial_position"] = self.cam_init_combo.currentText()
        c["camera"]["initial_pan"] = float(self.cam_init_pan_spin.value())
        c["camera"]["initial_tilt"] = float(self.cam_init_tilt_spin.value())
        c["camera"]["max_pan_speed"] = float(self.max_pan_spin.value())
        c["camera"]["max_tilt_speed"] = float(self.max_tilt_spin.value())
        c["camera"]["update_interval_hz"] = int(self.update_hz_spin.value())
        c["camera"]["jitter_px"] = float(self.jitter_spin.value())
        # controller
        c["controller"]["kp_pan"] = float(self.kp_pan_spin.value())
        c["controller"]["kp_tilt"] = float(self.kp_tilt_spin.value())
        c["controller"]["ki"] = float(self.ki_spin.value())
        c["controller"]["kd"] = float(self.kd_spin.value())
        c["controller"]["deadzone_px"] = float(self.dead_spin.value())
        c["tracker"]["process_noise"] = float(self.proc_spin.value())
        c["tracker"]["meas_noise"] = float(self.meas_spin.value())
        # env — world + platform + stars/gradient/vignetting/brightness
        c["world"]["width"] = int(self.world_w_spin.value())
        c["world"]["height"] = int(self.world_h_spin.value())
        c["world"]["background"] = int(self.world_bg_spin.value())
        c["platform"]["type"] = self.platform_combo.currentText()
        c["platform"]["speed_px_per_frame"] = float(self.platform_speed_spin.value())
        if "environment" not in c:
            c["environment"] = {}
        env = c["environment"]
        env["gradient_enabled"] = bool(self.grad_enabled.isChecked())
        env["gradient_type"] = self.grad_type_combo.currentText()
        env["gradient_top"] = int(self.grad_top_spin.value())
        env["gradient_bottom"] = int(self.grad_bottom_spin.value())
        env["gradient_angle"] = int(self.grad_angle_spin.value())
        env["stars_enabled"] = bool(self.stars_enabled.isChecked())
        env["stars_density"] = float(self.stars_density_spin.value())
        env["stars_brightness"] = int(self.stars_brightness_spin.value())
        env["stars_min_mag"] = int(self.stars_minmag_spin.value())
        env["stars_max_mag"] = int(self.stars_maxmag_spin.value())
        env["stars_twinkle"] = bool(self.stars_twinkle_check.isChecked())
        env["stars_seed"] = int(self.stars_seed_spin.value())
        env["vignetting_enabled"] = bool(self.vig_enabled.isChecked())
        env["vignetting_strength"] = float(self.vig_strength_spin.value())
        env["vignetting_radius"] = float(self.vig_radius_spin.value())
        env["vignetting_falloff"] = float(self.vig_falloff_spin.value())
        env["vignetting_center_x"] = float(self.vig_cx_spin.value())
        env["vignetting_center_y"] = float(self.vig_cy_spin.value())
        env["brightness_gain"] = float(self.bright_gain_spin.value())
        env["brightness_offset"] = int(self.bright_offset_spin.value())
        # disturb
        c["atmosphere"]["type"] = self.atmo_combo.currentText()
        c["atmosphere"]["strength"] = float(self.atmo_strength.value())
        c["noise"]["gaussian_std"] = float(self.gauss_spin.value())
        c["noise"]["salt_pepper_prob"] = float(self.spp_spin.value())
        c["noise"]["gaussian_enabled"] = bool(self.gauss_check.isChecked())
        c["noise"]["salt_pepper_enabled"] = bool(self.spp_check.isChecked())
        c["noise"]["poisson"] = bool(self.poisson_check.isChecked())
        # input/exp + video centre calibration (for mp4 where image centre may be offset)
        c["experiment"]["seed"] = int(self.seed_spin.value())
        c["experiment"]["duration_s"] = float(self.duration_spin.value())
        c["experiment"]["input_mode"] = self.input_combo.currentText()
        c["experiment"]["video_path"] = self.video_path_edit.text().strip()
        c["camera"]["video_centre_offset_x"] = float(self.vid_centre_x_spin.value())
        c["camera"]["video_centre_offset_y"] = float(self.vid_centre_y_spin.value())
        self.configApplied.emit(c)
        self.accept()
