import time
import os
import datetime
import numpy as np
import cv2
from PyQt5.QtWidgets import (QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
                             QLabel, QPushButton, QFrame, QMessageBox, QFileDialog,
                             QGridLayout)
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QFont
from .viewport import CameraView, WorldView
from ..pipeline.track.display import DisplayTracker
from .control_deck import ControlDeck
from .benchmark_dialog import BenchmarkResultDialog
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
        self.resize(1240, 900)
        self.setStyleSheet("QMainWindow { background: white; }")
        self.cfg = load_config()
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
        for b in (self.btn_start, self.btn_pause, self.btn_reset, self.btn_config):
            top_lay.addWidget(b)
        root.addWidget(top)

        # Middle — two FOVs
        mid = QWidget()
        mid.setStyleSheet("background: white;")
        mid_lay = QHBoxLayout(mid)
        mid_lay.setContentsMargins(28, 6, 28, 6)
        mid_lay.setSpacing(24)

        left_col = QVBoxLayout()
        left_col.setSpacing(4)
        lbl_cam = QLabel("Camera FOV")
        lbl_cam.setStyleSheet("color: #777777; font-size: 17px; font-weight: 700; background: transparent;")
        left_col.addWidget(lbl_cam)
        self.cam_view = CameraView("Camera FOV")
        left_col.addWidget(self.cam_view, 1)

        right_col = QVBoxLayout()
        right_col.setSpacing(4)
        lbl_world = QLabel("World FOV")
        lbl_world.setStyleSheet("color: #777777; font-size: 17px; font-weight: 700; background: transparent;")
        right_col.addWidget(lbl_world)
        self.world_view = WorldView(world_size=(self.cfg["world"]["width"], self.cfg["world"]["height"]))
        right_col.addWidget(self.world_view, 1)

        mid_lay.addLayout(left_col, 1)
        mid_lay.addLayout(right_col, 1)
        root.addWidget(mid, 1)

        # Bottom metrics panel — dark
        bottom = QFrame()
        bottom.setStyleSheet(f"QFrame {{ background: {BAR}; border: none; }}")
        root.addWidget(bottom)
        bottom_outer = QVBoxLayout(bottom)
        bottom_outer.setContentsMargins(0, 0, 0, 0)
        bottom_outer.setSpacing(0)
        grid_wrap = QWidget()
        grid_wrap.setStyleSheet("background: transparent;")
        bottom_outer.addWidget(grid_wrap)
        grid = QGridLayout(grid_wrap)
        grid.setContentsMargins(60, 28, 60, 14)
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(12)
        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 0)
        grid.setColumnStretch(3, 1)

        self._values = {}

        def add_row(r, c_label, label_text, key):
            lab = QLabel(label_text)
            lab.setStyleSheet("color: white; font-size: 15px; font-weight: 700; background: transparent;")
            val = QLabel("—")
            val.setAlignment(Qt.AlignCenter)
            val.setMinimumWidth(190)
            val.setFixedHeight(30)
            val.setStyleSheet(f"""
                QLabel {{
                    background: {VALUE_PILL}; color: #111111;
                    border-radius: 15px; font-size: 13px; font-weight: 600;
                }}
            """)
            grid.addWidget(lab, r, c_label * 2)
            grid.addWidget(val, r, c_label * 2 + 1)
            self._values[key] = val

        # top group
        add_row(0, 0, "State", "state")
        add_row(1, 0, "Valid Detections", "valid")
        add_row(2, 0, "Average Confidence", "conf")
        add_row(3, 0, "Raw Centroid (x, y)", "raw")
        add_row(4, 0, "Fused Centroid (x, y)", "fused")
        add_row(0, 1, "F P S", "fps")
        add_row(1, 1, "Average Latency", "lat_avg")
        add_row(2, 1, "Maximum Latency", "lat_max")
        # spacer row
        grid.setRowMinimumHeight(5, 18)
        # bottom group
        add_row(6, 0, "Avg Tracking Error", "trk_err")
        add_row(7, 0, "Avg Angular Error", "ang_err")
        add_row(8, 0, "Mean & Max Error", "mean_max")
        add_row(9, 0, "RMSE & P95 Error", "rmse_p95")
        add_row(6, 1, "Lock Retention", "lock")
        add_row(7, 1, "Target Loss & Count", "loss")
        add_row(8, 1, "Acquisition Time & Count", "acq")
        add_row(9, 1, "Reacquisition Time & Count", "reacq")

        # live track telemetry strip — only real measurements, same pill style
        strip = QFrame()
        strip.setStyleSheet("QFrame { background: transparent; border: none; border-top: 1px solid #6B7280; }")
        strip_lay = QHBoxLayout(strip)
        strip_lay.setContentsMargins(60, 10, 60, 22)
        strip_lay.setSpacing(18)
        self._tele_vals = {}
        for _tkey, _caption in (("track_id", "TRACK ID"), ("det_conf", "DET CONF"),
                                ("age", "TRACK AGE"), ("last", "LAST DETECT"),
                                ("fov", "FOV STATUS")):
            _box = QVBoxLayout()
            _box.setSpacing(4)
            _cap = QLabel(_caption)
            _cap.setStyleSheet("color: #CBD5E1; font-size: 10px; font-weight: 800; letter-spacing: 0.6px; background: transparent;")
            _val = QLabel("—")
            _val.setAlignment(Qt.AlignCenter)
            _val.setMinimumWidth(150)
            _val.setFixedHeight(30)
            _val.setStyleSheet(f"QLabel {{ background: {VALUE_PILL}; color: #111111; border-radius: 15px; font-size: 13px; font-weight: 600; }}")
            _box.addWidget(_cap)
            _box.addWidget(_val)
            _wrap = QWidget()
            _wrap.setStyleSheet("background: transparent;")
            _wrap.setLayout(_box)
            strip_lay.addWidget(_wrap)
            self._tele_vals[_tkey] = _val
        strip_lay.addStretch()
        bottom_outer.addWidget(strip)

        # signals
        self.btn_start.clicked.connect(self.start_run)
        self.btn_pause.clicked.connect(self.toggle_pause)
        self.btn_reset.clicked.connect(self.reset_run)
        self.btn_config.clicked.connect(self.open_control_deck)
        self.btn_pause.setEnabled(False)

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

        # ---- bottom panel (16 fields, exact design labels) ----
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
        # live track telemetry strip — real values only, "—" when unavailable
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
        event.accept()
