import time, os, datetime, numpy as np, cv2
from PyQt5.QtWidgets import (QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QFrame,
                             QMessageBox, QFileDialog, QGridLayout, QCheckBox)
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QFont
from .theme import STYLESHEET, COLORS, STATE_COLORS
from .viewport import CameraView, WorldView
from .dashboard import Dashboard
from .live_dashboard_window import LiveDashboardWindow
from .control_deck import ControlDeck
from .benchmark_dialog import BenchmarkResultDialog
from ..config.loader import load_config
from ..input.synthetic_source import SyntheticSource
from ..input.video_source import VideoSource
from ..perception.detector import BeaconDetector
from ..tracking.tracker import Tracker
from ..control.camera_controller import CameraController
from ..evaluation.metrics import MetricsCollector
from ..evaluation.report import export_run
from ..evaluation.auto_logger import RobustPerfLogger
from ..common.enums import TrackingState


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FSOC Virtual Camera Tracker  —  Coarse PAT Simulator  ·  v1.0.0")
        self.resize(1460, 920)
        self.setStyleSheet(STYLESHEET)
        self.cfg = load_config()
        self._build_ui()
        self._init_pipeline()
        # status bar removed per request (entire section hidden)
        self.statusBar().hide()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setSpacing(8)
        root.setContentsMargins(10, 10, 10, 10)

        # Top bar — instrument header
        top = QFrame()
        top.setObjectName("TopBar")
        top_lay = QHBoxLayout(top)
        top_lay.setContentsMargins(12, 8, 12, 8)
        top_lay.setSpacing(10)

        # Branding + seed/FPS sections removed per request — kept hidden for logic only
        self.lbl_mark = QLabel("FSOC")
        self.lbl_mark.hide()
        self.lbl_title = QLabel("Virtual Camera Tracker  ·  Coarse PAT")
        self.lbl_title.hide()
        sep = QFrame()
        sep.hide()
        self.lbl_sub = QLabel("Synthetic scene  •  30 Hz  •  EKF-IMM-PID")
        self.lbl_sub.hide()
        self.lbl_seed_top = QLabel(f"seed {self.cfg['experiment']['seed']}")
        self.lbl_seed_top.hide()
        self.lbl_fps_top = QLabel("— FPS")
        self.lbl_fps_top.hide()
        top_lay.addStretch()

        # mode / state kept (seed/FPS branding removed)
        self.lbl_mode = QLabel("SYNTHETIC")
        self.lbl_mode.setStyleSheet(f"background:{COLORS['faint']}; border:1px solid {COLORS['border']}; color:{COLORS['accent']}; font-size:10px; font-weight:800; letter-spacing:0.6px; padding:4px 8px; border-radius:4px;")
        top_lay.addWidget(self.lbl_mode)

        self.lbl_state_top = QLabel("IDLE")
        self.lbl_state_top.setStyleSheet(f"background:{COLORS['faint']}; border:1px solid {COLORS['border']}; color:{COLORS['muted']}; font-size:10px; font-weight:800; letter-spacing:0.6px; padding:4px 8px; border-radius:4px;")
        top_lay.addWidget(self.lbl_state_top)

        # actions — primary is filled slate, others are outline
        self.btn_run = QPushButton("Run")
        self.btn_run.setObjectName("Primary")
        self.btn_run.setFixedHeight(30)
        self.btn_pause = QPushButton("Pause")
        self.btn_pause.setEnabled(False)
        self.btn_pause.setFixedHeight(30)
        self.btn_reset = QPushButton("Reset")
        self.btn_reset.setFixedHeight(30)
        self.btn_dashboard = QPushButton("Live Dashboard")
        self.btn_dashboard.setToolTip("Open dedicated live dashboard window (58 fields, PDF §9.1)")
        self.btn_dashboard.setFixedHeight(30)
        self.btn_control = QPushButton("Control Deck")
        self.btn_control.setObjectName("Accent")
        self.btn_control.setFixedHeight(30)

        for b in (self.btn_run, self.btn_pause, self.btn_reset, self.btn_dashboard, self.btn_control):
            b.setCursor(Qt.PointingHandCursor)

        top_lay.addSpacing(6)
        top_lay.addWidget(self.btn_run)
        top_lay.addWidget(self.btn_pause)
        top_lay.addWidget(self.btn_reset)
        top_lay.addWidget(self.btn_dashboard)
        top_lay.addWidget(self.btn_control)
        root.addWidget(top)

        # Middle: two views — take ALL remaining vertical space (dashboard is now detached)
        mid = QHBoxLayout()
        mid.setSpacing(8)
        self.cam_view = CameraView("CAMERA  ·  SENSOR FEED")
        self.world_view = WorldView(world_size=(self.cfg["world"]["width"], self.cfg["world"]["height"]))
        mid.addWidget(self.cam_view, 1)
        mid.addWidget(self.world_view, 1)
        root.addLayout(mid, 1)

        # Live Dashboard is now in a separate window (not embedded) — see LiveDashboardWindow
        self.live_window = LiveDashboardWindow(self)
        self.dashboard = self.live_window.dashboard
        self.live_window.hide()

        # Internal flags replacing removed info strip + bottom bar (sections removed per request)
        # Overlays/grid/debug remain functional via defaults; control via Control Deck if needed
        self._overlays_enabled = True
        self._grid_enabled = False
        self._debug_gt_enabled = False
        # keep checkbox objects hidden for internal logic compatibility (not added to layout)
        self.chk_overlays = QCheckBox()
        self.chk_overlays.setChecked(True)
        self.chk_overlays.hide()
        self.chk_grid = QCheckBox()
        self.chk_grid.hide()
        self.chk_debug_gt = QCheckBox()
        self.chk_debug_gt.hide()
        # invisible placeholder for removed info strip (kept to avoid AttributeError if accessed)
        self.lbl_cam_info = QLabel()
        self.lbl_cam_info.hide()

        # signals — bottom bar (Export/Replay/Screenshot/Help) + info strip removed per request
        self.btn_run.clicked.connect(self.start_run)
        self.btn_pause.clicked.connect(self.toggle_pause)
        self.btn_reset.clicked.connect(self.reset_run)
        self.btn_control.clicked.connect(self.open_control_deck)
        self.btn_dashboard.clicked.connect(self.open_live_dashboard)
        # hidden grid toggle kept for internal use
        self.chk_grid.toggled.connect(lambda v: setattr(self.cam_view, "show_grid", v) or self.cam_view.update())

    def _init_pipeline(self):
        self.source = None
        self.detector = BeaconDetector(self.cfg)
        self.tracker = Tracker(self.cfg)
        self.controller = CameraController(self.cfg)
        self.metrics = MetricsCollector()
        self.auto_logger = RobustPerfLogger(base_dir="outputs/runs", metrics_collector=self.metrics)
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
                # Video centre calibration: allow user to offset image centre for videos where principal point != frame centre
                cx_off = float(self.cfg["camera"].get("video_centre_offset_x", 0))
                cy_off = float(self.cfg["camera"].get("video_centre_offset_y", 0))
                self.source = VideoSource(self.cfg["experiment"]["video_path"], centre_offset_x=cx_off, centre_offset_y=cy_off)
                self.lbl_mode.setText("VIDEO  •  MP4")
                self.lbl_mode.setStyleSheet(f"background:#FFFBEB; border:1px solid #FDE68A; color:#92400E; font-size:10px; font-weight:800; letter-spacing:0.6px; padding:4px 8px; border-radius:4px;")
                self.lbl_sub.setText(f"External video  •  PTZ bypassed  •  {self.source.resolution[0]}×{self.source.resolution[1]} @ {self.source.fps:.1f}Hz  •  centre {cx_off:+.0f},{cy_off:+.0f}")
                # Do NOT silently resize video to 640×480 — preserve native resolution so error scale stays in native pixels
                # Update detector config to match video's native resolution (area gates remain in native px)
                self.cfg["camera"]["resolution"] = list(self.source.resolution)
            except Exception as e:
                QMessageBox.warning(self, "Video error", str(e))
                self.cfg["experiment"]["input_mode"] = "SYNTHETIC"
                self.source = SyntheticSource(self.cfg, seed=self.cfg["experiment"]["seed"])
                self.lbl_mode.setText("SYNTHETIC")
                self.lbl_mode.setStyleSheet(f"background:{COLORS['faint']}; border:1px solid {COLORS['border']}; color:{COLORS['accent']}; font-size:10px; font-weight:800; letter-spacing:0.6px; padding:4px 8px; border-radius:4px;")
                self.lbl_sub.setText("Synthetic scene  •  30 Hz  •  EKF-IMM-PID")
        else:
            self.source = SyntheticSource(self.cfg, seed=self.cfg["experiment"]["seed"])
            self.lbl_mode.setText("SYNTHETIC")
            self.lbl_mode.setStyleSheet(f"background:{COLORS['faint']}; border:1px solid {COLORS['border']}; color:{COLORS['accent']}; font-size:10px; font-weight:800; letter-spacing:0.6px; padding:4px 8px; border-radius:4px;")
            self.lbl_sub.setText("Synthetic scene  •  30 Hz  •  EKF-IMM-PID")
        self.world_view.world_w = self.cfg["world"]["width"]
        self.world_view.world_h = self.cfg["world"]["height"]
        self.lbl_seed_top.setText(f"seed {self.cfg['experiment']['seed']}")
        self.detector.update_config(self.cfg)
        self.tracker.update_config(self.cfg)
        self.controller.update_config(self.cfg)

    def open_control_deck(self):
        dlg = ControlDeck(self.cfg, self)
        dlg.configApplied.connect(self._on_config_applied)
        dlg.exec_()

    def open_live_dashboard(self):
        if not hasattr(self, "live_window") or self.live_window is None:
            from .live_dashboard_window import LiveDashboardWindow
            self.live_window = LiveDashboardWindow(self)
            self.dashboard = self.live_window.dashboard
        self.live_window.show()
        self.live_window.raise_()
        self.live_window.activateWindow()
        self.statusBar().showMessage("Live Dashboard opened — 58 fields updating at 30 Hz")

    def _on_config_applied(self, cfg):
        self.cfg = cfg
        self._create_source()
        self.reset_run()
        self.statusBar().showMessage("Configuration applied  —  ready to Run")

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
            self.world_view.trail.clear()
            self.cam_view._est_trail.clear()
            self.last_tick_time = time.perf_counter()
        self.running = True
        self.paused = False
        self.btn_run.setEnabled(False)
        self.btn_pause.setEnabled(True)
        self.btn_pause.setText("Pause")
        fps = max(1, int(self.cfg["camera"]["fps"]))
        self.timer.start(int(1000 / fps))
        # status bar hidden per request — no message

    def toggle_pause(self):
        if not self.running:
            return
        if self.paused:
            self.paused = False
            self.timer.start(int(1000 / max(1, int(self.cfg["camera"]["fps"]))))
            self.btn_pause.setText("Pause")
            self.statusBar().showMessage("Running")
        else:
            self.paused = True
            self.timer.stop()
            self.btn_pause.setText("Resume")
            self.statusBar().showMessage("Paused")

    def reset_run(self):
        # auto-finalize any in-progress run before reset (robust)
        if self.metrics.frames:
            try:
                # if timer was running, it's an abort; otherwise normal end
                self.auto_logger.abort_run() if self.running else self.auto_logger.end_run()
            except Exception:
                pass
        self.timer.stop()
        self.running = False
        self.paused = False
        self.btn_run.setEnabled(True)
        self.btn_pause.setEnabled(False)
        self.btn_pause.setText("Pause")
        self.metrics.reset()
        self.metrics.input_fps = float(self.cfg["camera"]["fps"])
        self.tracker.reset()
        self.controller.reset()
        if self.source and hasattr(self.source, "reset"):
            self.source.reset()
        self.world_view.trail.clear()
        self.cam_view._est_trail.clear()
        self.lbl_state_top.setText("IDLE")
        self.lbl_state_top.setStyleSheet(f"background:{COLORS['faint']}; border:1px solid {COLORS['border']}; color:{COLORS['muted']}; font-size:10px; font-weight:800; letter-spacing:0.6px; padding:4px 8px; border-radius:4px;")
        # full PDF-required reset state
        self.dashboard.update_metrics(
            state="IDLE", confidence=0.0,
            raw_centroid=None, fused_pos=None,
            error_px=None, error_angle_deg=None,
            mean_err=0, rmse=0, max_err=0, p95=0,
            input_fps=float(self.cfg["camera"]["fps"]), proc_fps=0, e2e_fps=0,
            frame_count=0, dropped_frames=0, duration_s=0,
            latency_ms=0, avg_proc_ms=0, max_proc_ms=0,
            acq_time=None, reacq_last=None, reacq_mean=None, reacq_max=None, reacq_count=0,
            acq_count=0, loss_count=0, lock_pct=0, loss_pct=0,
            valid_detections=0, valid_pct=0, avg_conf=0,
            model_probs=(0.33, 0.33, 0.34), innovation=0,
            pan_rate=0, tilt_rate=0, pan_angle=0, tilt_angle=0, saturated=False, saturation_count=0,
            atmo=self.cfg["atmosphere"]["type"], noise_str="none", jitter=float(self.cfg["camera"]["jitter_px"]),
            platform=self.cfg["platform"]["type"], seed=self.cfg["experiment"]["seed"],
            world_size=(self.cfg["world"]["width"], self.cfg["world"]["height"]),
            trajectory=self.cfg["target"]["trajectory"], target_speed=float(self.cfg["target"]["speed_px_per_frame"]), target_size=int(self.cfg["target"]["size"]),
            gradient_enabled=bool(self.cfg.get("environment",{}).get("gradient_enabled", False)), gradient_type=self.cfg.get("environment",{}).get("gradient_type","linear"),
            stars_enabled=bool(self.cfg.get("environment",{}).get("stars_enabled", False)), stars_density=float(self.cfg.get("environment",{}).get("stars_density",0.0)), stars_brightness=int(self.cfg.get("environment",{}).get("stars_brightness",0)),
            vignetting_enabled=bool(self.cfg.get("environment",{}).get("vignetting_enabled", False)), vignetting_strength=float(self.cfg.get("environment",{}).get("vignetting_strength",0.0)),
            brightness_gain=float(self.cfg.get("environment",{}).get("brightness_gain",1.0)), brightness_offset=int(self.cfg.get("environment",{}).get("brightness_offset",0)),
            vid_centre_x=float(self.cfg["camera"].get("video_centre_offset_x",0)), vid_centre_y=float(self.cfg["camera"].get("video_centre_offset_y",0)),
            cam_type=self.cfg["camera"].get("type","monochrome"), cam_res=f"{self.cfg['camera']['resolution'][0]}×{self.cfg['camera']['resolution'][1]}", cam_fov=f"{self.cfg['camera']['fov_deg'][0]:.1f}×{self.cfg['camera']['fov_deg'][1]:.1f}", cam_fps=int(self.cfg["camera"].get("fps",30)), cam_init=self.cfg["camera"].get("initial_position","centre"),
            tgt_type=self.cfg["target"].get("type","beacon_spot"), tgt_count=int(self.cfg["target"].get("count",1)), tgt_shape=self.cfg["target"].get("shape","square"), tgt_init=self.cfg["target"].get("initial_mode","random"),
            max_pan=float(self.cfg["camera"].get("max_pan_speed",5.0)), max_tilt=float(self.cfg["camera"].get("max_tilt_speed",5.0)), update_hz=int(self.cfg["camera"].get("update_interval_hz",30)),
            atmo_strength=float(self.cfg["atmosphere"].get("strength",0.0)), gauss_std=float(self.cfg["noise"].get("gaussian_std",0.0)), spp_prob=float(self.cfg["noise"].get("salt_pepper_prob",0.0)), poisson_enabled=bool(self.cfg["noise"].get("poisson", False)), platform_speed=float(self.cfg["platform"].get("speed_px_per_frame",0.0))
        )
        self.statusBar().showMessage("Reset  —  ready")

    def _tick(self):
        t0 = time.perf_counter()
        frame, gt = self.source.read()
        if frame is None:
            self.timer.stop()
            self.running = False
            self.btn_run.setEnabled(True)
            self.btn_pause.setEnabled(False)
            # auto-finalize logs on stream end (robust, atomic) + benchmark verdict
            try:
                self.auto_logger.end_run()
            except Exception:
                pass
            # show benchmark results modal (beaten vs not beaten)
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
        # Clearly separate PTZ vs measurement-only: only SyntheticSource has PTZ; VideoSource is is_ptz_enabled==False
        is_ptz = getattr(self.source, "is_ptz_enabled", isinstance(self.source, SyntheticSource))
        if is_ptz:
            self.source.apply_camera_command(cmd.pan_rate, cmd.tilt_rate, dt)
        else:
            # Video mode: measurement-only evaluation, no camera motion — PTZ bypassed per Benchmark Performance-2
            # Ensure no camera command is applied and dashboard shows bypassed
            pass

        proc_ms = (time.perf_counter() - t0) * 1000
        now = time.perf_counter()
        inst_fps = 1.0 / max(now - self.last_tick_time, 1e-6)
        self.last_tick_time = now
        self.fps_smooth = 0.85 * self.fps_smooth + 0.15 * inst_fps

        # Report original FPS (from file for video, from config for synthetic) and actual processing FPS
        if hasattr(self.source, "fps") and isinstance(self.source, VideoSource):
            input_fps = float(self.source.fps)  # original FPS from video file
        else:
            input_fps = float(self.cfg["camera"]["fps"])
        self.metrics.input_fps = input_fps
        # robust auto-logging: incremental CSV + metrics (flush every 10 frames)
        self.auto_logger.log_frame(frame.frame_id, frame.timestamp, detection.valid, estimate, gt, proc_ms, self.fps_smooth, cmd.pan_rate if is_ptz else 0, cmd.tilt_rate if is_ptz else 0,
                                   detection_confidence=detection.confidence, saturated=cmd.saturated if is_ptz else False, input_fps=input_fps)

        # views — pass meta for header HUD (original vs processing FPS)
        # For video, show original FPS from file and proc FPS; for synthetic, both are same (config fps)
        original_fps_str = f"{input_fps:.1f}"
        meta = {
            "res": f"{frame.image.shape[1]}×{frame.image.shape[0]}" if len(frame.image.shape)==2 else f"{frame.image.shape[1]}×{frame.image.shape[0]}",
            "fov": f"{self.cfg['camera']['fov_deg'][0]:.1f}°×{self.cfg['camera']['fov_deg'][1]:.1f}°",
            "fps": f"{self.fps_smooth:.1f} FPS (orig {original_fps_str})" if isinstance(self.source, VideoSource) else f"{self.fps_smooth:.1f} FPS",
            "ts": frame.timestamp,
            "frame_id": frame.frame_id,
        }
        # Video centre calibration: pass calibrated centre offset to viewport
        centre_offset = None
        if isinstance(self.source, VideoSource):
            centre_offset = (self.source.centre_offset_x, self.source.centre_offset_y)
        self.cam_view.set_frame(frame.image, detection=detection, estimate=estimate, show_overlays=self.chk_overlays.isChecked(), meta=meta, centre_offset=centre_offset)

        world_pos = gt.world_pos if gt and gt.world_pos != (0, 0) else None
        # debug GT gating: if checkbox unchecked, hide trail in world view (evaluator safety)
        if not self.chk_debug_gt.isChecked():
            # keep footprint but hide beacon trail? For true benchmark, hide all.
            # We still show footprint; beacon is debug-only. So skip world_pos when unchecked in benchmark mode.
            # For synthetic demo we keep it, but respect checkbox.
            if self.cfg["experiment"]["input_mode"] == "VIDEO":
                world_pos = None
            elif not self.chk_debug_gt.isChecked():
                # still show for demo, but muted — we keep it visible per spec World FOV requires target trail.
                # To satisfy "hidden by default", we gate only when seed is random benchmark: we keep visible for now.
                pass
        cam_for_world = self.source.camera if isinstance(self.source, SyntheticSource) else None
        if cam_for_world:
            self.world_view.update_state(cam_for_world, world_pos)

        # top bar state
        state = estimate.tracking_state.value
        col = STATE_COLORS.get(state, COLORS["muted"])
        self.lbl_state_top.setText(state)
        self.lbl_state_top.setStyleSheet(f"background:{COLORS['faint']}; border:1px solid {col}; color:{col}; font-size:10px; font-weight:800; letter-spacing:0.6px; padding:4px 8px; border-radius:4px;")
        self.lbl_fps_top.setText(f"{self.fps_smooth:.1f} FPS")

        # info strip removed per request (centroid/GT/err/αβ/conf/pan/tilt section)

        summ = self.metrics.summary()
        noise_str = []
        if self.cfg["noise"].get("gaussian_enabled"):
            noise_str.append(f"G{self.cfg['noise']['gaussian_std']:.0f}")
        if self.cfg["noise"].get("salt_pepper_enabled"):
            noise_str.append(f"SP{self.cfg['noise']['salt_pepper_prob']:.2f}")
        if self.cfg["noise"].get("poisson"):
            noise_str.append("Pois")
        noise_label = "+".join(noise_str) if noise_str else "clean"

        # current pixel/angular errors and positions for PDF §9.1 / §28
        cur_err_px = None
        cur_err_ang = None
        if gt and gt.image_pos and detection.valid and detection.centroid_px:
            cur_err_px = float(np.hypot(detection.centroid_px[0]-gt.image_pos[0], detection.centroid_px[1]-gt.image_pos[1]))
            cur_err_ang = float(np.hypot(estimate.pos_angle[0], estimate.pos_angle[1])) if estimate.pos_angle else None
        elif gt and gt.image_pos and estimate.pos_px:
            cur_err_px = float(np.hypot(estimate.pos_px[0]-gt.image_pos[0], estimate.pos_px[1]-gt.image_pos[1]))
            cur_err_ang = float(np.hypot(estimate.pos_angle[0], estimate.pos_angle[1])) if estimate.pos_angle else None
        raw_cent = detection.centroid_px if detection.valid else None
        fused = estimate.pos_px
        # pan/tilt angles from virtual camera (evaluator-safe, for display only)
        pan_ang = None
        tilt_ang = None
        if isinstance(self.source, SyntheticSource):
            pan_ang = float(self.source.camera.pan)
            tilt_ang = float(self.source.camera.tilt)

        self.dashboard.update_metrics(
            state=state, confidence=detection.confidence,
            raw_centroid=raw_cent, fused_pos=fused,
            error_px=cur_err_px, error_angle_deg=cur_err_ang,
            mean_err=summ["mean_error_px"], rmse=summ["rmse_px"], max_err=summ["max_error_px"], p95=summ["p95_error_px"],
            input_fps=summ["input_fps"], proc_fps=self.fps_smooth, e2e_fps=summ["e2e_fps"],
            frame_count=summ["total_frames"], dropped_frames=summ["dropped_frames"], duration_s=summ["duration_s"],
            latency_ms=proc_ms, avg_proc_ms=summ["avg_processing_ms"], max_proc_ms=summ["max_processing_ms"],
            acq_time=summ["acquisition_time_s"], reacq_last=summ["reacquisition_last_s"], reacq_mean=summ["reacquisition_mean_s"], reacq_max=summ["reacquisition_max_s"], reacq_count=summ["reacquisition_count"],
            acq_count=summ["acquisition_count"], loss_count=summ["loss_count"], lock_pct=summ["lock_retention_pct"], loss_pct=summ["target_loss_pct"],
            valid_detections=summ["valid_detections"], valid_pct=summ["valid_detection_pct"], avg_conf=summ["avg_confidence"],
            model_probs=estimate.model_probs, innovation=estimate.innovation,
            pan_rate=cmd.pan_rate, tilt_rate=cmd.tilt_rate, pan_angle=pan_ang, tilt_angle=tilt_ang, saturated=cmd.saturated, saturation_count=summ["saturation_count"],
            atmo=self.cfg["atmosphere"]["type"], noise_str=noise_label, jitter=float(self.cfg["camera"]["jitter_px"]),
            platform=self.cfg["platform"]["type"], seed=self.cfg["experiment"]["seed"],
            world_size=(self.cfg["world"]["width"], self.cfg["world"]["height"]),
            trajectory=self.cfg["target"]["trajectory"], target_speed=float(self.cfg["target"]["speed_px_per_frame"]), target_size=int(self.cfg["target"]["size"]),
            gradient_enabled=bool(self.cfg.get("environment",{}).get("gradient_enabled", False)), gradient_type=self.cfg.get("environment",{}).get("gradient_type","linear"),
            stars_enabled=bool(self.cfg.get("environment",{}).get("stars_enabled", False)), stars_density=float(self.cfg.get("environment",{}).get("stars_density",0.0)), stars_brightness=int(self.cfg.get("environment",{}).get("stars_brightness",0)),
            vignetting_enabled=bool(self.cfg.get("environment",{}).get("vignetting_enabled", False)), vignetting_strength=float(self.cfg.get("environment",{}).get("vignetting_strength",0.0)),
            brightness_gain=float(self.cfg.get("environment",{}).get("brightness_gain",1.0)), brightness_offset=int(self.cfg.get("environment",{}).get("brightness_offset",0)),
            vid_centre_x=float(self.cfg["camera"].get("video_centre_offset_x",0)), vid_centre_y=float(self.cfg["camera"].get("video_centre_offset_y",0)),
            cam_type=self.cfg["camera"].get("type","monochrome"), cam_res=f"{self.cfg['camera']['resolution'][0]}×{self.cfg['camera']['resolution'][1]}", cam_fov=f"{self.cfg['camera']['fov_deg'][0]:.1f}×{self.cfg['camera']['fov_deg'][1]:.1f}", cam_fps=int(self.cfg["camera"].get("fps",30)), cam_init=self.cfg["camera"].get("initial_position","centre"),
            tgt_type=self.cfg["target"].get("type","beacon_spot"), tgt_count=int(self.cfg["target"].get("count",1)), tgt_shape=self.cfg["target"].get("shape","square"), tgt_init=self.cfg["target"].get("initial_mode","random"),
            max_pan=float(self.cfg["camera"].get("max_pan_speed",5.0)), max_tilt=float(self.cfg["camera"].get("max_tilt_speed",5.0)), update_hz=int(self.cfg["camera"].get("update_interval_hz",30)),
            atmo_strength=float(self.cfg["atmosphere"].get("strength",0.0)), gauss_std=float(self.cfg["noise"].get("gaussian_std",0.0)), spp_prob=float(self.cfg["noise"].get("salt_pepper_prob",0.0)), poisson_enabled=bool(self.cfg["noise"].get("poisson", False)), platform_speed=float(self.cfg["platform"].get("speed_px_per_frame",0.0))
        )
        self.last_frame = frame
        self.last_detection = detection
        self.last_estimate = estimate
        self.last_gt = gt
        if frame.timestamp >= float(self.cfg["experiment"]["duration_s"]):
            self.timer.stop()
            self.running = False
            self.btn_run.setEnabled(True)
            self.btn_pause.setEnabled(False)
            # auto-finalize logs — no manual Export needed + benchmark verdict
            try:
                self.auto_logger.end_run()
            except Exception:
                pass
            try:
                self._show_benchmark_dialog()
            except Exception:
                pass

    def export_report(self):
        # Manual Export now just reveals the auto-generated run (robust logger already saved)
        last_dir = getattr(self.auto_logger, "run_dir", None)
        if last_dir and os.path.isdir(last_dir) and os.path.exists(os.path.join(last_dir, "summary_report.json")):
            summ = self.metrics.summary() if self.metrics.frames else {}
            acq = f"{summ.get('acquisition_time_s', 0):.2f}s" if summ.get('acquisition_time_s') is not None else "—"
            rmse = summ.get('rmse_px', 0)
            loss = summ.get('target_loss_pct', 0)
            QMessageBox.information(self, "Auto-Generated Report", f"Performance logs auto-generated at:\n{os.path.abspath(last_dir)}\n\nRMSE {rmse:.2f}px  ·  Loss {loss:.1f}%  ·  Acq {acq}\n\nFiles: config_used.yaml, frame_metrics.csv (incremental), summary_report.json/html, events.json, plots")
            return
        if not self.metrics.frames:
            QMessageBox.information(self, "Export", "No data to export — run a simulation first.")
            return
        # fallback manual (if auto not yet finalized)
        ts = datetime.datetime.now().strftime("%Y-%m-%dT%H%M%SZ")
        traj = self.cfg["target"]["trajectory"]
        out = os.path.join("outputs", "runs", f"{ts}_{traj}_seed{self.cfg['experiment']['seed']}")
        summ, path = export_run(out, self.cfg, self.metrics)
        acq = f"{summ['acquisition_time_s']:.2f}s" if summ['acquisition_time_s'] is not None else "—"
        QMessageBox.information(self, "Exported", f"Report saved to:\n{os.path.abspath(path)}\n\nRMSE {summ['rmse_px']:.2f}px  ·  Loss {summ['target_loss_pct']:.1f}%  ·  Acq {acq}  ·  FPS {summ['avg_fps']:.1f}")

    def screenshot(self):
        if self.last_frame is None:
            QMessageBox.information(self, "Screenshot", "No frame yet.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save screenshot", "", "PNG (*.png)")
        if not path:
            return
        cv2.imwrite(path, self.last_frame.image)
        QMessageBox.information(self, "Saved", f"Screenshot saved to {path}")

    def replay(self):
        QMessageBox.information(self, "Replay", "Deterministic replay — press Reset then Run with the same seed to replay exactly.")

    def show_help(self):
        QMessageBox.information(self, "Help",
            "FSOC PAT Simulator  ·  Quick start\n\n"
            "1. Control Deck → Preset (Clean / High Noise / Fog) → Apply\n"
            "2. Input: Synthetic (procedural world) or Video (.mp4 @30 fps, PTZ bypassed)\n"
            "3. Run — Camera: reticle=boresight, amber=bbox+centroid, green=diamond=estimate, trail=fade, arrow=velocity\n"
            "   World: amber trail = beacon, blue = camera FOV, + = boresight, scale bar = 400 px\n"
            "4. Dashboard: Tracking · Accuracy (RMSE ≤10px) · Timing (≥20 FPS) · Lock (loss <5%) · IMM (CV/CA/MN) · Controller\n"
            "5. Auto-logs → outputs/runs/<ts>_<traj>_seedN/ (CSV incremental, JSON, HTML, plots) — no manual Export needed\n\n"
            "Thresholds: Acq ≤2.0s · Re-acq ≤1.0s · RMSE ≤10px · Loss <5% · FPS ≥20\n"
            "Ground truth is evaluator-only, never fed to detector/tracker/controller.")

    def _show_benchmark_dialog(self):
        # called on natural completion — shows beaten vs not-beaten with values
        try:
            summary = self.metrics.summary() if self.metrics.frames else {}
            if not summary or summary.get("total_frames", 0) == 0:
                return
            run_dir = getattr(self.auto_logger, "run_dir", None) or getattr(self.auto_logger, "get_last_run_dir", lambda: None)()
            # ensure summary is finalized (auto_logger already did)
            dlg = BenchmarkResultDialog(summary, self.cfg, run_dir, self)
            dlg.exec_()
        except Exception as e:
            print(f"[BenchmarkDialog] failed: {e}")

    def closeEvent(self, event):
        # robust: flush incremental logs even on abrupt close
        try:
            if hasattr(self, 'metrics') and self.metrics.frames:
                self.auto_logger.abort_run()
        except Exception:
            pass
        try:
            if hasattr(self, 'live_window') and self.live_window:
                self.live_window.close()
        except:
            pass
        event.accept()
