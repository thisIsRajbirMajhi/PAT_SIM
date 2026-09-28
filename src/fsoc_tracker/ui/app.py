import time
import os
import datetime
import numpy as np
import cv2
from PyQt5.QtWidgets import (QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
                             QLabel, QPushButton, QFrame, QMessageBox, QFileDialog)
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QFont
from .viewport import CameraView, WorldView
from ..pipeline.track.display import DisplayTracker
from .control_deck import ControlDeck
from .benchmark_dialog import BenchmarkResultDialog
from .live_dashboard_window import LiveDashboardWindow
from ..config.loader import load_config
from ..input.synthetic_source import SyntheticSource
from ..input.video_source import VideoSource
from ..pipeline import BeaconDetector, Tracker
from ..camera import CameraController
from ..evaluation.metrics import MetricsCollector
from ..evaluation.report import export_run
from ..evaluation.auto_logger import RobustPerfLogger

BAR = "#595959"
PILL = "#D9D9D9"
VALUE_PILL = "#E8E8E8"


def _pill_button(text, color):
    b = QPushButton(text)
    b.setCursor(Qt.PointingHandCursor)
    b.setFixedSize(130, 42)
    b.setStyleSheet(f"""
        QPushButton {{
            background: {PILL}; color: {color};
            border: none; border-radius: 20px;
            font-size: 17px; font-weight: 800; letter-spacing: 0.5px;
        }}
        QPushButton:hover {{ background: #CFCFCF; }}
        QPushButton:disabled {{ color: #888888; background: #CFCFCF; }}
    """)
    return b


class MainWindow(QMainWindow):
    """Main window — exact layout from New GUI Design / Main Window.pdf."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("FSOC & PAT SIM")
        self.resize(1500, 950)
        self.setMinimumSize(1100, 700)
        self.setStyleSheet("QMainWindow { background: white; }")
        self.cfg = load_config()
        self.dashboard_window = None
        self._build_ui()
        self._init_pipeline()

    # ---------------- UI ----------------
    def _build_ui(self):
        central = QWidget()
        central.setStyleSheet("background: white;")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setSpacing(8)
        root.setContentsMargins(0, 0, 0, 0)

        # Top bar — dark
        top = QFrame()
        top.setStyleSheet(f"QFrame {{ background: {BAR}; border: none; }}")
        top.setFixedHeight(72)
        top_lay = QHBoxLayout(top)
        top_lay.setContentsMargins(22, 10, 22, 10)
        top_lay.setSpacing(10)
        title = QLabel("FSOC & PAT SIM")
        title.setStyleSheet("color: white; font-size: 24px; font-weight: 800; letter-spacing: 0.5px; background: transparent;")
        top_lay.addWidget(title)
        self.lbl_live = QLabel("Live")
        self.lbl_live.setStyleSheet("color: #4ADE80; font-size: 13px; font-weight: 700; background: transparent;")
        top_lay.addWidget(self.lbl_live)
        top_lay.addStretch()
        self.btn_start = _pill_button("START", "#16A34A")
        self.btn_pause = _pill_button("PAUSE", "#111111")
        self.btn_reset = _pill_button("RESET", "#DC2626")
        self.btn_config = _pill_button("CONFIG", "#1D4ED8")
        self.btn_dashboard = _pill_button("DASHBOARD", "#0EA5E9")
        for b in (self.btn_start, self.btn_pause, self.btn_reset, self.btn_config,
                  self.btn_dashboard):
            top_lay.addWidget(b)
        root.addWidget(top)

        # Middle — two FOVs take ALL free space (dashboard lives in its own window)
        mid = QWidget()
        mid.setStyleSheet("background: white;")
        mid_lay = QHBoxLayout(mid)
        mid_lay.setContentsMargins(12, 8, 12, 12)
        mid_lay.setSpacing(12)

        left_col = QVBoxLayout()
        left_col.setSpacing(4)
        left_col.setContentsMargins(0, 0, 0, 0)
        lbl_cam = QLabel("Camera FOV")
        lbl_cam.setStyleSheet("color: #777777; font-size: 17px; font-weight: 700; background: transparent;")
        left_col.addWidget(lbl_cam)
        self.cam_view = CameraView("Camera FOV")
        self.cam_view.setSizePolicy(self.cam_view.sizePolicy().Expanding,
                                    self.cam_view.sizePolicy().Expanding)
        left_col.addWidget(self.cam_view, 1)

        right_col = QVBoxLayout()
        right_col.setSpacing(4)
        right_col.setContentsMargins(0, 0, 0, 0)
        lbl_world = QLabel("World FOV")
        lbl_world.setStyleSheet("color: #777777; font-size: 17px; font-weight: 700; background: transparent;")
        right_col.addWidget(lbl_world)
        self.world_view = WorldView(world_size=(self.cfg["world"]["width"], self.cfg["world"]["height"]))
        self.world_view.setSizePolicy(self.world_view.sizePolicy().Expanding,
                                      self.world_view.sizePolicy().Expanding)
        right_col.addWidget(self.world_view, 1)

        mid_lay.addLayout(left_col, 1)
        mid_lay.addLayout(right_col, 1)
        root.addWidget(mid, 1)

        # Hidden compat labels — the dashboard now lives in its own window,
        # but headless tests / external callers still read _values/_tele_vals.
        self._values = {}
        self._tele_vals = {}
        for _k in ("state", "valid", "conf", "raw", "fused", "fps",
                   "lat_avg", "lat_max", "trk_err", "ang_err",
                   "mean_max", "rmse_p95", "lock", "loss", "acq", "reacq"):
            _hidden = QLabel("—")
            self._values[_k] = _hidden
        for _k in ("track_id", "det_conf", "age", "last", "fov"):
            _hidden = QLabel("—")
            self._tele_vals[_k] = _hidden

        # signals
        self.btn_start.clicked.connect(self.start_run)
        self.btn_pause.clicked.connect(self.toggle_pause)
        self.btn_reset.clicked.connect(self.reset_run)
        self.btn_config.clicked.connect(self.open_control_deck)
        self.btn_dashboard.clicked.connect(self.open_dashboard)
        self.btn_pause.setEnabled(False)

    def open_dashboard(self):
        """Show the live dashboard in its own window (non-modal)."""
        try:
            if self.dashboard_window is None:
                self.dashboard_window = LiveDashboardWindow(self)
            self.dashboard_window.show()
            self.dashboard_window.raise_()
            self.dashboard_window.activateWindow()
        except Exception:
            pass

    # ---------------- pipeline (unchanged logic) ----------------
    def _init_pipeline(self):
        self.source = None
        self.detector = BeaconDetector(self.cfg)
        self.tracker = Tracker(self.cfg)
        self.controller = CameraController(self.cfg)
        self.metrics = MetricsCollector()
        self.auto_logger = RobustPerfLogger(base_dir="outputs/runs", metrics_collector=self.metrics)
        self.display = DisplayTracker(self.cfg)
        self.timer = QTimer()
        self.timer.timeout.connect(self._tick)
        self.running = False
        self.paused = False
        self.last_tick_time = time.perf_counter()
        self.fps_smooth = 30.0
        self.last_frame = None
        self.last_detection = None
        self.last_estimate = None
        self.last_gt = None
        self._overlays_enabled = True
        self._create_source()

    def _create_source(self):
        if self.source:
            try:
                self.source.release()
            except Exception:
                pass
        mode = self.cfg["experiment"]["input_mode"]
        if mode == "VIDEO" and self.cfg["experiment"].get("video_path"):
            try:
                cx_off = float(self.cfg["camera"].get("video_centre_offset_x", 0))
                cy_off = float(self.cfg["camera"].get("video_centre_offset_y", 0))
                self.source = VideoSource(self.cfg["experiment"]["video_path"],
                                          centre_offset_x=cx_off, centre_offset_y=cy_off)
                self.cfg["camera"]["resolution"] = list(self.source.resolution)
            except Exception as e:
                QMessageBox.warning(self, "Video error", str(e))
                self.cfg["experiment"]["input_mode"] = "SYNTHETIC"
                self.source = SyntheticSource(self.cfg, seed=self.cfg["experiment"]["seed"])
        else:
            self.source = SyntheticSource(self.cfg, seed=self.cfg["experiment"]["seed"])
        self.world_view.world_w = self.cfg["world"]["width"]
        self.world_view.world_h = self.cfg["world"]["height"]
        self.detector.update_config(self.cfg)
        self.tracker.update_config(self.cfg)
        self.controller.update_config(self.cfg)

    def open_control_deck(self):
        dlg = ControlDeck(self.cfg, self)
        dlg.configApplied.connect(self._on_config_applied)
        dlg.exec_()

    def _on_config_applied(self, cfg):
        self.cfg = cfg
        self.display = DisplayTracker(self.cfg)
        self._create_source()
        self.reset_run()

    def start_run(self):
        if self.running and not self.paused:
            return
        if not self.running:
            self.metrics.start_run()
            self.metrics.input_fps = float(self.cfg["camera"]["fps"])
            self.auto_logger.begin_run(self.cfg)
            self.tracker.reset()
            self.controller.reset()
            if hasattr(self.source, "reset"):
                self.source.reset()
            # coarse cue: target starts rendered in Camera FOV, loop centers it
            if isinstance(self.source, SyntheticSource) and hasattr(self.source, "cue_camera_to_target"):
                self.source.cue_camera_to_target()
            self.display.reset()
            self.world_view.clear()
            self.cam_view.clear()
            self.last_tick_time = time.perf_counter()
        self.running = True
        self.paused = False
        self.btn_start.setEnabled(False)
        self.btn_pause.setEnabled(True)
        self.btn_pause.setText("PAUSE")
        fps = max(1, int(self.cfg["camera"]["fps"]))
        self.timer.start(int(1000 / fps))

    def toggle_pause(self):
        if not self.running:
            return
        if self.paused:
            self.paused = False
            self.timer.start(int(1000 / max(1, int(self.cfg["camera"]["fps"]))))
            self.btn_pause.setText("PAUSE")
        else:
            self.paused = True
            self.timer.stop()
            self.btn_pause.setText("PAUSE")

    def reset_run(self):
        if self.metrics.frames:
            try:
                self.auto_logger.abort_run() if self.running else self.auto_logger.end_run()
            except Exception:
                pass
        self.timer.stop()
        self.running = False
        self.paused = False
        self.btn_start.setEnabled(True)
        self.btn_pause.setEnabled(False)
        self.metrics.reset()
        self.metrics.input_fps = float(self.cfg["camera"]["fps"])
        self.tracker.reset()
        self.controller.reset()
        if self.source and hasattr(self.source, "reset"):
            self.source.reset()
        self.display.reset()
        self.world_view.clear()
        self.cam_view.clear()
        for k, v in self._values.items():
            v.setText("—")
        try:
            for v in self._tele_vals.values():
                v.setText("—")
        except Exception:
            pass
        try:
            if self.dashboard_window is not None:
                self.dashboard_window.dashboard.reset()
        except Exception:
            pass

    def _set(self, key, text):
        if key in self._values:
            self._values[key].setText(text)

    def _tick(self):
        t0 = time.perf_counter()
        frame, gt = self.source.read()
        if frame is None:
            self.timer.stop()
            self.running = False
            self.btn_start.setEnabled(True)
            self.btn_pause.setEnabled(False)
            try:
                self.auto_logger.end_run()
            except Exception:
                pass
            try:
                self._show_benchmark_dialog()
            except Exception:
                pass
            return

        pred = self.tracker.get_predicted_pixel() if hasattr(self.tracker, "get_predicted_pixel") else None
        detection = self.detector.detect(frame.image, predicted_pos=pred)
        estimate = self.tracker.step(detection, frame)

        dt = 1.0 / max(float(self.cfg["camera"]["fps"]), 1)
        cmd = self.controller.step(estimate, dt=dt)
        # FOV geometry for this exact frame (pre-move camera matches frame_img)
        _in_fov = None
        try:
            if isinstance(self.source, SyntheticSource) and gt is not None \
                    and getattr(gt, "world_pos", None) not in (None, (0, 0)):
                _in_fov = self.source.camera.world_to_image(gt.world_pos) is not None
            elif isinstance(self.source, VideoSource):
                _in_fov = True if detection.valid else None
        except Exception:
            _in_fov = None
        is_ptz = getattr(self.source, "is_ptz_enabled", isinstance(self.source, SyntheticSource))
        if is_ptz:
            self.source.apply_camera_command(cmd.pan_rate, cmd.tilt_rate, dt)

        proc_ms = (time.perf_counter() - t0) * 1000
        now = time.perf_counter()
        inst_fps = 1.0 / max(now - self.last_tick_time, 1e-6)
        self.last_tick_time = now
        self.fps_smooth = 0.85 * self.fps_smooth + 0.15 * inst_fps

        if hasattr(self.source, "fps") and isinstance(self.source, VideoSource):
            input_fps = float(self.source.fps)
        else:
            input_fps = float(self.cfg["camera"]["fps"])
        self.metrics.input_fps = input_fps
        self.auto_logger.log_frame(
            frame.frame_id, frame.timestamp, detection.valid, estimate, gt,
            proc_ms, self.fps_smooth,
            cmd.pan_rate if is_ptz else 0, cmd.tilt_rate if is_ptz else 0,
            detection_confidence=detection.confidence,
            saturated=cmd.saturated if is_ptz else False, input_fps=input_fps)

        centre_offset = None
        if isinstance(self.source, VideoSource):
            centre_offset = (self.source.centre_offset_x, self.source.centre_offset_y)
        # central display state: system status + per-target telemetry from real
        # backend conditions (DisplayTracker is the single source of truth)
        try:
            _sm = getattr(self.tracker, "sm", None)
            _dstate, _tele = self.display.update(
                getattr(frame, "frame_id", 0), float(frame.timestamp),
                bool(detection.valid), float(detection.confidence or 0.0),
                getattr(getattr(estimate, "tracking_state", None), "value", ""),
                int(getattr(_sm, "candidate_frames", 0)),
                int(getattr(_sm, "locked_frames", 0)),
                float(getattr(estimate, "innovation", 0.0) or 0.0),
                _in_fov,
                est_pos=getattr(estimate, "pos_px", None))
        except Exception:
            from ..pipeline.track.display import DisplayState, TrackTelemetry, DisplayStatus
            _dstate = DisplayState(status=DisplayStatus.SCANNING, show_no_target=True)
            _tele = TrackTelemetry()
        # live boresight offset for this frame's detection (real pixel geometry)
        try:
            if detection.valid and detection.centroid_px is not None:
                if isinstance(self.source, VideoSource):
                    _ccx, _ccy = self.source.get_calibrated_centre()
                else:
                    _ccx, _ccy = self.cfg["camera"]["resolution"][0] / 2.0, \
                        self.cfg["camera"]["resolution"][1] / 2.0
                _tele.offset_px = float(np.hypot(
                    detection.centroid_px[0] - _ccx, detection.centroid_px[1] - _ccy))
            else:
                _tele.offset_px = None
        except Exception:
            _tele.offset_px = None
        self.cam_view.set_frame(frame.image, detection=detection, estimate=estimate,
                                show_overlays=True, meta={}, centre_offset=centre_offset,
                                display=_dstate, telemetry=_tele)

        world_pos = gt.world_pos if gt and gt.world_pos != (0, 0) else None
        cam_for_world = self.source.camera if isinstance(self.source, SyntheticSource) else None
        if cam_for_world:
            self.world_view.update_state(cam_for_world, world_pos)
            # full scene: environment + ALL beacons, not just the primary target
            try:
                self.world_view.set_world_image(
                    getattr(self.source, "last_world_img", None),
                    getattr(self.source, "last_all_world_pos", None))
            except Exception:
                pass
        elif world_pos is not None:
            # video mode: no PTZ camera, keep footprint idle — still update trail dot only
            pass

        # ---- metrics: compat labels + push to separate dashboard window ----
        summ = self.metrics.summary()
        raw = detection.centroid_px if detection.valid else None
        fused = estimate.pos_px
        cur_ang = float(np.hypot(estimate.pos_angle[0], estimate.pos_angle[1])) if getattr(estimate, "pos_angle", None) else None

        self._set("state", _dstate.label)
        self._set("valid", f"{summ['valid_detections']}")
        avg_c = summ.get("avg_confidence", 0)
        self._set("conf", f"{avg_c * 100:.1f}%" if avg_c else "—")
        self._set("raw", f"{raw[0]:.1f}, {raw[1]:.1f}" if raw is not None else "—")
        try:
            self._set("fused", f"{fused[0]:.1f}, {fused[1]:.1f}" if fused is not None else "—")
        except Exception:
            self._set("fused", "—")
        self._set("fps", f"{self.fps_smooth:.1f}")
        self._set("lat_avg", f"{summ['avg_processing_ms']:.1f} ms")
        self._set("lat_max", f"{summ['max_processing_ms']:.1f} ms")
        self._set("trk_err", f"{summ['mean_error_px']:.2f} px")
        self._set("ang_err", f"{cur_ang:.2f}°" if cur_ang is not None else "—")
        self._set("mean_max", f"{summ['mean_error_px']:.1f} / {summ['max_error_px']:.1f} px")
        self._set("rmse_p95", f"{summ['rmse_px']:.1f} / {summ['p95_error_px']:.1f} px")
        self._set("lock", f"{summ['lock_retention_pct']:.1f}%")
        self._set("loss", f"{summ['target_loss_pct']:.1f}% ({summ['loss_count']})")
        acq = summ.get("acquisition_time_s")
        self._set("acq", f"{acq:.2f}s ({summ.get('acquisition_count', 0)})" if acq is not None else f"— ({summ.get('acquisition_count', 0)})")
        reacq_m = summ.get("reacquisition_mean_s")
        self._set("reacq", f"{reacq_m:.2f}s ({summ.get('reacquisition_count', 0)})" if reacq_m is not None else f"— ({summ.get('reacquisition_count', 0)})")
        # live track telemetry — real values only, "—" when unavailable
        try:
            self._tele_vals["track_id"].setText(_tele.track_label)
            self._tele_vals["det_conf"].setText(
                f"{_tele.det_conf * 100:.0f}%" if _tele.det_conf is not None else "—")
            self._tele_vals["age"].setText(
                f"{_tele.track_age_s:.2f} s" if _tele.track_age_s is not None else "—")
            self._tele_vals["last"].setText(
                f"{_tele.last_detect_age_s:.2f} s" if _tele.last_detect_age_s is not None else "—")
            self._tele_vals["fov"].setText(_tele.fov if _tele.fov is not None else "—")
        except Exception:
            pass
        # push everything to the separate dashboard window (if open)
        try:
            self._push_to_dashboard(summ, detection, estimate, cmd,
                                    _dstate, _tele, raw, fused, cur_ang, proc_ms)
        except Exception:
            pass

        self.last_frame = frame
        self.last_detection = detection
        self.last_estimate = estimate
        self.last_gt = gt
        if frame.timestamp >= float(self.cfg["experiment"]["duration_s"]):
            self.timer.stop()
            self.running = False
            self.btn_start.setEnabled(True)
            self.btn_pause.setEnabled(False)
            try:
                self.auto_logger.end_run()
            except Exception:
                pass
            try:
                self._show_benchmark_dialog()
            except Exception:
                pass

    def _push_to_dashboard(self, summ, detection, estimate, cmd,
                             _dstate, _tele, raw, fused, cur_ang, proc_ms):
        """Forward the live frame state to the separate dashboard window."""
        if self.dashboard_window is None:
            return
        try:
            dash = self.dashboard_window.dashboard
        except Exception:
            return
        cfg = self.cfg
        cam = cfg.get("camera", {})
        tgt = cfg.get("target", {})
        env = cfg.get("environment", {})
        noise = cfg.get("noise", {})
        atmo_cfg = cfg.get("atmosphere", {})
        plat = cfg.get("platform", {})
        world = cfg.get("world", {})

        # current-frame error vs ground truth (last logged entry)
        err_px = None
        try:
            if self.metrics.frames:
                err_px = self.metrics.frames[-1].get("error_px")
        except Exception:
            pass
        err_ang = cur_ang

        try:
            model_probs = list(getattr(estimate, "model_probs", (0.33, 0.33, 0.34)))
            if len(model_probs) != 3:
                model_probs = [0.33, 0.33, 0.34]
        except Exception:
            model_probs = [0.33, 0.33, 0.34]
        try:
            innov = float(getattr(estimate, "innovation", 0.0) or 0.0)
        except Exception:
            innov = 0.0

        try:
            pan_angle = float(self.source.camera.pan) if hasattr(getattr(self.source, "camera", None), "pan") else None
        except Exception:
            pan_angle = None
        try:
            tilt_angle = float(self.source.camera.tilt) if hasattr(getattr(self.source, "camera", None), "tilt") else None
        except Exception:
            tilt_angle = None

        res = cam.get("resolution", [640, 480])
        fov = cam.get("fov_deg", [4.0, 3.0])
        try:
            conf_cur = float(getattr(detection, "confidence", 0.0) or 0.0) if getattr(detection, "valid", False) else 0.0
        except Exception:
            conf_cur = 0.0

        noise_parts = []
        try:
            if noise.get("gaussian_enabled"):
                noise_parts.append("gauss")
            if noise.get("salt_pepper_enabled"):
                noise_parts.append("s&p")
            if noise.get("poisson"):
                noise_parts.append("poisson")
        except Exception:
            pass
        noise_str = "+".join(noise_parts) if noise_parts else "clean"

        dash.update_metrics(
            _dstate.label, conf_cur,
            tuple(raw) if raw is not None else None,
            tuple(fused) if fused is not None else None,
            err_px, err_ang,
            summ.get("mean_error_px", 0.0), summ.get("rmse_px", 0.0),
            summ.get("max_error_px", 0.0), summ.get("p95_error_px", 0.0),
            float(summ.get("input_fps", cam.get("fps", 30))),
            float(self.fps_smooth), float(summ.get("e2e_fps", self.fps_smooth)),
            int(summ.get("total_frames", 0)), int(summ.get("dropped_frames", 0)),
            float(summ.get("duration_s", 0.0)),
            float(proc_ms), float(summ.get("avg_processing_ms", 0.0)),
            float(summ.get("max_processing_ms", 0.0)),
            summ.get("acquisition_time_s"), summ.get("reacquisition_last_s"),
            summ.get("reacquisition_mean_s"), summ.get("reacquisition_max_s"),
            int(summ.get("reacquisition_count", 0)),
            int(summ.get("acquisition_count", 0)), int(summ.get("loss_count", 0)),
            float(summ.get("lock_retention_pct", 0.0)),
            float(summ.get("target_loss_pct", 0.0)),
            int(summ.get("valid_detections", 0)),
            float(summ.get("valid_detection_pct", 0.0)),
            float(summ.get("avg_confidence", 0.0)),
            model_probs, innov,
            float(getattr(cmd, "pan_rate", 0.0) or 0.0),
            float(getattr(cmd, "tilt_rate", 0.0) or 0.0),
            pan_angle, tilt_angle,
            bool(getattr(cmd, "saturated", False)),
            int(getattr(self.metrics, "saturation_count", 0)),
            str(atmo_cfg.get("type", "clear")), noise_str,
            float(cam.get("jitter_px", 0.0)), str(plat.get("type", "none")),
            int(cfg.get("experiment", {}).get("seed", 0)),
            (int(world.get("width", 2000)), int(world.get("height", 2000))),
            str(tgt.get("trajectory", "circular")),
            float(tgt.get("speed_px_per_frame", 0.0)),
            int(tgt.get("size", 10)),
            gradient_enabled=bool(env.get("gradient_enabled", False)),
            gradient_type=str(env.get("gradient_type", "linear")),
            stars_enabled=bool(env.get("stars_enabled", False)),
            stars_density=float(env.get("stars_density", 0.0)),
            stars_brightness=int(env.get("stars_brightness", 0)),
            vignetting_enabled=bool(env.get("vignetting_enabled", False)),
            vignetting_strength=float(env.get("vignetting_strength", 0.0)),
            brightness_gain=float(env.get("brightness_gain", 1.0)),
            brightness_offset=int(env.get("brightness_offset", 0)),
            vid_centre_x=float(cam.get("video_centre_offset_x", 0.0)),
            vid_centre_y=float(cam.get("video_centre_offset_y", 0.0)),
            cam_type=str(cam.get("type", "monochrome")),
            cam_res=f"{res[0]}×{res[1]}",
            cam_fov=f"{fov[0]:.1f}×{fov[1]:.1f}",
            cam_fps=int(cam.get("fps", 30)),
            cam_init=str(cam.get("initial_position", "centre")),
            tgt_type=str(tgt.get("type", "beacon_spot")),
            tgt_count=int(tgt.get("count", 1)),
            tgt_shape=str(tgt.get("shape", "square")),
            tgt_init=str(tgt.get("initial_mode", "random")),
            max_pan=float(cam.get("max_pan_speed", 5.0)),
            max_tilt=float(cam.get("max_tilt_speed", 5.0)),
            update_hz=int(cam.get("update_interval_hz", cam.get("fps", 30))),
            atmo_strength=float(atmo_cfg.get("strength", 0.0)),
            gauss_std=float(noise.get("gaussian_std", 0.0)),
            spp_prob=float(noise.get("salt_pepper_prob", 0.0)),
            poisson_enabled=bool(noise.get("poisson", False)),
            platform_speed=float(plat.get("speed_px_per_frame", 0.0)),
            track_label=getattr(_tele, "track_label", None),
            det_conf=getattr(_tele, "det_conf", None),
            track_age_s=getattr(_tele, "track_age_s", None),
            last_detect_age_s=getattr(_tele, "last_detect_age_s", None),
            fov=getattr(_tele, "fov", None),
        )

    def _show_benchmark_dialog(self):
        try:
            summary = self.metrics.summary() if self.metrics.frames else {}
            if not summary or summary.get("total_frames", 0) == 0:
                return
            run_dir = getattr(self.auto_logger, "run_dir", None) or getattr(self.auto_logger, "get_last_run_dir", lambda: None)()
            dlg = BenchmarkResultDialog(summary, self.cfg, run_dir, self)
            dlg.exec_()
        except Exception as e:
            print(f"[BenchmarkDialog] failed: {e}")

    def closeEvent(self, event):
        try:
            if hasattr(self, "metrics") and self.metrics.frames:
                self.auto_logger.abort_run()
        except Exception:
            pass
        try:
            if self.dashboard_window is not None:
                self.dashboard_window.hide()
        except Exception:
            pass
        event.accept()
