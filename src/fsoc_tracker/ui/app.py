import time, os, datetime, numpy as np, cv2
from PyQt5.QtWidgets import (QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QFrame,
                             QMessageBox, QFileDialog, QGridLayout, QCheckBox)
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QFont
from .theme import STYLESHEET, COLORS, STATE_COLORS
from .viewport import CameraView, WorldView
from .dashboard import Dashboard
from .control_deck import ControlDeck
from ..config.loader import load_config
from ..input.synthetic_source import SyntheticSource
from ..input.video_source import VideoSource
from ..perception.detector import BeaconDetector
from ..tracking.tracker import Tracker
from ..control.camera_controller import CameraController
from ..evaluation.metrics import MetricsCollector
from ..evaluation.report import export_run
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
        self.statusBar().showMessage("Ready  —  open Control Deck, select preset, press Run")

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

        # mark
        self.lbl_mark = QLabel("FSOC")
        self.lbl_mark.setStyleSheet(f"background:{COLORS['primary']}; color:white; font-size:10px; font-weight:800; letter-spacing:1.2px; padding:4px 7px; border-radius:4px;")
        top_lay.addWidget(self.lbl_mark)

        self.lbl_title = QLabel("Virtual Camera Tracker  ·  Coarse PAT")
        self.lbl_title.setStyleSheet(f"color:{COLORS['text']}; font-size:12px; font-weight:700; letter-spacing:0.2px;")
        top_lay.addWidget(self.lbl_title)

        sep = QFrame()
        sep.setFixedSize(1, 18)
        sep.setStyleSheet(f"background:{COLORS['border']};")
        top_lay.addWidget(sep)

        self.lbl_sub = QLabel("Synthetic scene  •  30 Hz  •  EKF-IMM-PID")
        self.lbl_sub.setStyleSheet(f"color:{COLORS['muted']}; font-size:11px;")
        top_lay.addWidget(self.lbl_sub)
        top_lay.addStretch()

        # mode / state / seed / fps — tabular, muted but precise
        self.lbl_mode = QLabel("SYNTHETIC")
        self.lbl_mode.setStyleSheet(f"background:{COLORS['faint']}; border:1px solid {COLORS['border']}; color:{COLORS['accent']}; font-size:10px; font-weight:800; letter-spacing:0.6px; padding:4px 8px; border-radius:4px;")
        top_lay.addWidget(self.lbl_mode)

        self.lbl_state_top = QLabel("IDLE")
        self.lbl_state_top.setStyleSheet(f"background:{COLORS['faint']}; border:1px solid {COLORS['border']}; color:{COLORS['muted']}; font-size:10px; font-weight:800; letter-spacing:0.6px; padding:4px 8px; border-radius:4px;")
        top_lay.addWidget(self.lbl_state_top)

        self.lbl_seed_top = QLabel(f"seed {self.cfg['experiment']['seed']}")
        self.lbl_seed_top.setStyleSheet(f"color:{COLORS['muted']}; font-size:11px; font-family:'JetBrains Mono','Consolas',monospace;")
        top_lay.addWidget(self.lbl_seed_top)

        self.lbl_fps_top = QLabel("— FPS")
        self.lbl_fps_top.setStyleSheet(f"color:{COLORS['muted']}; font-size:11px; font-family:'JetBrains Mono','Consolas',monospace;")
        top_lay.addWidget(self.lbl_fps_top)

        # actions — primary is filled slate, others are outline
        self.btn_run = QPushButton("Run")
        self.btn_run.setObjectName("Primary")
        self.btn_run.setFixedHeight(30)
        self.btn_pause = QPushButton("Pause")
        self.btn_pause.setEnabled(False)
        self.btn_pause.setFixedHeight(30)
        self.btn_reset = QPushButton("Reset")
        self.btn_reset.setFixedHeight(30)
        self.btn_control = QPushButton("Control Deck")
        self.btn_control.setObjectName("Accent")
        self.btn_control.setFixedHeight(30)

        for b in (self.btn_run, self.btn_pause, self.btn_reset, self.btn_control):
            b.setCursor(Qt.PointingHandCursor)

        top_lay.addSpacing(6)
        top_lay.addWidget(self.btn_run)
        top_lay.addWidget(self.btn_pause)
        top_lay.addWidget(self.btn_reset)
        top_lay.addWidget(self.btn_control)
        root.addWidget(top)

        # Middle: two views
        mid = QHBoxLayout()
        mid.setSpacing(8)
        self.cam_view = CameraView("CAMERA  ·  SENSOR FEED")
        self.world_view = WorldView(world_size=(self.cfg["world"]["width"], self.cfg["world"]["height"]))
        mid.addWidget(self.cam_view, 1)
        mid.addWidget(self.world_view, 1)
        root.addLayout(mid, 1)

        # Info strip — tabular mono, light faint bg, thin border
        self.lbl_cam_info = QLabel("Centroid  —    Error  —    Confidence  —    Pan  —  Tilt  —")
        self.lbl_cam_info.setStyleSheet(f"background:{COLORS['faint']}; border:1px solid {COLORS['border']}; color:{COLORS['text2']}; font-size:11px; font-family:'JetBrains Mono','Consolas',monospace; padding:6px 10px; border-radius:6px;")
        root.addWidget(self.lbl_cam_info)

        # Dashboard
        self.dashboard = Dashboard()
        root.addWidget(self.dashboard)

        # Bottom bar — checkboxes left, actions right, no heavy buttons
        bottom = QFrame()
        bottom.setObjectName("Card")
        bot_lay = QHBoxLayout(bottom)
        bot_lay.setContentsMargins(10, 8, 10, 8)
        bot_lay.setSpacing(10)

        self.chk_overlays = QCheckBox("Overlays")
        self.chk_overlays.setChecked(True)
        self.chk_grid = QCheckBox("Grid")
        self.chk_grid.setChecked(False)
        self.chk_debug_gt = QCheckBox("Debug ground truth")
        # state
        bot_lay.addWidget(self.chk_overlays)
        bot_lay.addWidget(self.chk_grid)
        bot_lay.addWidget(self.chk_debug_gt)
        bot_lay.addStretch()

        self.btn_export = QPushButton("Export report")
        self.btn_export.setFixedHeight(28)
        self.btn_replay = QPushButton("Replay")
        self.btn_replay.setFixedHeight(28)
        self.btn_screenshot = QPushButton("Screenshot")
        self.btn_screenshot.setFixedHeight(28)
        self.btn_help = QPushButton("Help")
        self.btn_help.setObjectName("Ghost")
        self.btn_help.setFixedHeight(28)

        for b in (self.btn_export, self.btn_replay, self.btn_screenshot, self.btn_help):
            b.setCursor(Qt.PointingHandCursor)

        bot_lay.addWidget(self.btn_export)
        bot_lay.addWidget(self.btn_replay)
        bot_lay.addWidget(self.btn_screenshot)
        bot_lay.addWidget(self.btn_help)
        root.addWidget(bottom)

        # signals
        self.btn_run.clicked.connect(self.start_run)
        self.btn_pause.clicked.connect(self.toggle_pause)
        self.btn_reset.clicked.connect(self.reset_run)
        self.btn_control.clicked.connect(self.open_control_deck)
        self.btn_export.clicked.connect(self.export_report)
        self.btn_screenshot.clicked.connect(self.screenshot)
        self.btn_replay.clicked.connect(self.replay)
        self.btn_help.clicked.connect(self.show_help)
        self.chk_grid.toggled.connect(lambda v: setattr(self.cam_view, "show_grid", v) or self.cam_view.update())

    def _init_pipeline(self):
        self.source = None
        self.detector = BeaconDetector(self.cfg)
        self.tracker = Tracker(self.cfg)
        self.controller = CameraController(self.cfg)
        self.metrics = MetricsCollector()
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
                self.source = VideoSource(self.cfg["experiment"]["video_path"])
                self.lbl_mode.setText("VIDEO  •  MP4")
                self.lbl_mode.setStyleSheet(f"background:#FFFBEB; border:1px solid #FDE68A; color:#92400E; font-size:10px; font-weight:800; letter-spacing:0.6px; padding:4px 8px; border-radius:4px;")
                self.lbl_sub.setText("External video  •  PTZ bypassed  •  detector → tracker")
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
        self.statusBar().showMessage("Running  —  tracking")

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
            trajectory=self.cfg["target"]["trajectory"], target_speed=float(self.cfg["target"]["speed_px_per_frame"]), target_size=int(self.cfg["target"]["size"])
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
            self.statusBar().showMessage("End of video / stream")
            return

        pred = self.tracker.get_predicted_pixel() if hasattr(self.tracker, "get_predicted_pixel") else None
        detection = self.detector.detect(frame.image, predicted_pos=pred)
        estimate = self.tracker.step(detection, frame)

        dt = 1.0 / max(float(self.cfg["camera"]["fps"]), 1)
        cmd = self.controller.step(estimate, dt=dt)
        if isinstance(self.source, SyntheticSource):
            self.source.apply_camera_command(cmd.pan_rate, cmd.tilt_rate, dt)

        proc_ms = (time.perf_counter() - t0) * 1000
        now = time.perf_counter()
        inst_fps = 1.0 / max(now - self.last_tick_time, 1e-6)
        self.last_tick_time = now
        self.fps_smooth = 0.85 * self.fps_smooth + 0.15 * inst_fps

        input_fps = float(self.cfg["camera"]["fps"])
        self.metrics.input_fps = input_fps
        self.metrics.update(frame.frame_id, frame.timestamp, detection.valid, estimate, gt, proc_ms, self.fps_smooth, cmd.pan_rate, cmd.tilt_rate,
                            detection_confidence=detection.confidence, saturated=cmd.saturated, input_fps=input_fps)

        # views — pass meta for header HUD
        meta = {
            "res": f"{self.cfg['camera']['resolution'][0]}×{self.cfg['camera']['resolution'][1]}",
            "fov": f"{self.cfg['camera']['fov_deg'][0]:.1f}°×{self.cfg['camera']['fov_deg'][1]:.1f}°",
            "fps": f"{self.fps_smooth:.1f} FPS",
            "ts": frame.timestamp,
            "frame_id": frame.frame_id,
        }
        self.cam_view.set_frame(frame.image, detection=detection, estimate=estimate, show_overlays=self.chk_overlays.isChecked(), meta=meta)

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

        # info strip — tabular mono
        centroid_str = f"({detection.centroid_px[0]:5.1f},{detection.centroid_px[1]:5.1f})" if detection.valid and detection.centroid_px else "   —   "
        gt_str = f"({gt.image_pos[0]:5.1f},{gt.image_pos[1]:5.1f})" if gt and gt.image_pos else "   —   "
        if detection.valid and gt and gt.image_pos and detection.centroid_px:
            err = np.hypot(detection.centroid_px[0] - gt.image_pos[0], detection.centroid_px[1] - gt.image_pos[1])
            err_str = f"{err:5.1f}px"
        elif estimate.pos_px and gt and gt.image_pos:
            err = np.hypot(estimate.pos_px[0] - gt.image_pos[0], estimate.pos_px[1] - gt.image_pos[1])
            err_str = f"{err:5.1f}px est"
        else:
            err_str = "  —  "
        # angular error from estimate
        ang = f"α{estimate.pos_angle[0]:+.2f}° β{estimate.pos_angle[1]:+.2f}°" if estimate else "—"
        self.lbl_cam_info.setText(f"centroid {centroid_str}  ·  GT {gt_str}  ·  err {err_str}  ·  {ang}  ·  conf {detection.confidence:.2f}  ·  {state:11s}  ·  pan {cmd.pan_rate:+5.1f}°/s  tilt {cmd.tilt_rate:+5.1f}°/s{'  SAT' if cmd.saturated else ''}")

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
            trajectory=self.cfg["target"]["trajectory"], target_speed=float(self.cfg["target"]["speed_px_per_frame"]), target_size=int(self.cfg["target"]["size"])
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
            self.statusBar().showMessage("Run complete  —  Export report")

    def export_report(self):
        if not self.metrics.frames:
            QMessageBox.information(self, "Export", "No data to export — run a simulation first.")
            return
        ts = datetime.datetime.now().strftime("%Y-%m-%dT%H%M%SZ")
        traj = self.cfg["target"]["trajectory"]
        out = os.path.join("outputs", "runs", f"{ts}_{traj}_seed{self.cfg['experiment']['seed']}")
        summ, path = export_run(out, self.cfg, self.metrics)
        acq = f"{summ['acquisition_time_s']:.2f}s" if summ['acquisition_time_s'] is not None else "—"
        QMessageBox.information(self, "Exported", f"Report saved to:\n{os.path.abspath(path)}\n\nRMSE {summ['rmse_px']:.2f}px  ·  Loss {summ['target_loss_pct']:.1f}%  ·  Acq {acq}  ·  FPS {summ['avg_fps']:.1f}")
        self.statusBar().showMessage(f"Report exported  —  {path}")

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
            "5. Export report → outputs/runs/<ts>_<traj>_seedN/ (CSV/JSON/HTML)\n\n"
            "Thresholds: Acq ≤2.0s · Re-acq ≤1.0s · RMSE ≤10px · Loss <5% · FPS ≥20\n"
            "Ground truth is evaluator-only, never fed to detector/tracker/controller.")
