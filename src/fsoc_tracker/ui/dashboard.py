from PyQt5.QtWidgets import QWidget, QLabel, QGridLayout, QFrame, QVBoxLayout, QHBoxLayout, QProgressBar, QScrollArea, QSizePolicy
from PyQt5.QtCore import Qt
from .theme import COLORS, STATE_COLORS


class MetricRow(QFrame):
    """Single metric field: left label + right value + optional unit/status dot."""
    def __init__(self, label, parent=None, mono=True):
        super().__init__(parent)
        self.setStyleSheet("QFrame { border: none; }")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 2)
        lay.setSpacing(6)
        self.lbl = QLabel(label)
        self.lbl.setStyleSheet(f"color:{COLORS['muted']}; font-size:11px; font-weight:600;")
        self.lbl.setMinimumWidth(108)
        self.lbl.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.val = QLabel("—")
        f = "font-family:'JetBrains Mono','Consolas',monospace; font-size:13px; font-weight:700;" if mono else f"color:{COLORS['text']}; font-size:13px; font-weight:600;"
        self.val.setStyleSheet(f"color:{COLORS['text']}; {f}")
        self.val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.val.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.unit = QLabel("")
        self.unit.setStyleSheet(f"color:{COLORS['subtle']}; font-size:10px;")
        self.unit.setFixedWidth(32)
        lay.addWidget(self.lbl, 0)
        lay.addWidget(self.val, 1)
        lay.addWidget(self.unit, 0)
        # hairline separator below
        self.setFixedHeight(22)

    def set_value(self, text, color=None, tooltip=None):
        self.val.setText(text)
        if color:
            self.val.setStyleSheet(f"color:{color}; font-family:'JetBrains Mono','Consolas',monospace; font-size:13px; font-weight:800;")
        else:
            self.val.setStyleSheet(f"color:{COLORS['text']}; font-family:'JetBrains Mono','Consolas',monospace; font-size:13px; font-weight:700;")
        if tooltip:
            self.setToolTip(tooltip)


class SectionCard(QFrame):
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.setStyleSheet(f"QFrame#Card {{ background:{COLORS['surface']}; border:1px solid {COLORS['border']}; border-radius:8px; }}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(2)

        head = QHBoxLayout()
        head.setSpacing(6)
        self.dot = QLabel("●")
        self.dot.setStyleSheet(f"color:{COLORS['subtle']}; font-size:10px;")
        self.dot.setFixedWidth(12)
        t = QLabel(title)
        t.setStyleSheet(f"color:{COLORS['muted']}; font-size:11px; font-weight:700; letter-spacing:0.7px;")
        head.addWidget(self.dot)
        head.addWidget(t)
        head.addStretch()
        self.badge = QLabel("")
        self.badge.setStyleSheet(f"color:{COLORS['subtle']}; font-size:10px; font-weight:700;")
        head.addWidget(self.badge)
        lay.addLayout(head)

        # separator
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background:{COLORS['border']}; border:none;")
        lay.addWidget(sep)

        self.rows_lay = QVBoxLayout()
        self.rows_lay.setSpacing(0)
        self.rows_lay.setContentsMargins(0, 4, 0, 0)
        lay.addLayout(self.rows_lay)
        lay.addStretch()

        self.rows = {}

    def add_row(self, key, label, mono=True):
        r = MetricRow(label, mono=mono)
        self.rows[key] = r
        self.rows_lay.addWidget(r)
        return r

    def row(self, key):
        return self.rows[key]


class Dashboard(QWidget):
    """
    Live dashboard where EVERY required metric has its own dedicated field (MetricRow).
    Grouped into 8 instrument sections for readability, but each metric is an isolated row
    with label + mono value + unit, not a combined string. Covers PDF §9.1 + §28 + thresholds.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # grid of section cards — scrollable if height is tight
        self.grid = QGridLayout()
        self.grid.setSpacing(8)
        self.grid.setContentsMargins(0, 0, 0, 0)

        container = QWidget()
        container.setLayout(self.grid)
        # we keep without scroll for now (fits 920px height with 8 cards); if needed wrap in QScrollArea later

        # --- create sections ---
        self.s_tracking = SectionCard("TRACKING  ·  DETECTION")
        self.s_tracking.add_row("state", "State")
        self.s_tracking.add_row("raw_x", "Raw centroid X", mono=True)
        self.s_tracking.add_row("raw_y", "Raw centroid Y", mono=True)
        self.s_tracking.add_row("fused_x", "Fused est. X", mono=True)
        self.s_tracking.add_row("fused_y", "Fused est. Y", mono=True)
        self.s_tracking.add_row("conf_cur", "Confidence (cur)", mono=True)
        self.s_tracking.add_row("conf_avg", "Confidence (avg)", mono=True)
        self.s_tracking.add_row("valid_n", "Valid detections", mono=True)
        self.s_tracking.add_row("valid_pct", "Valid %", mono=True)

        self.s_accuracy = SectionCard("ACCURACY")
        self.s_accuracy.add_row("cur_px", "Current error", mono=True)
        self.s_accuracy.add_row("cur_ang", "Current ang. error", mono=True)
        self.s_accuracy.add_row("mean", "Mean error", mono=True)
        self.s_accuracy.add_row("rmse", "RMSE", mono=True)
        self.s_accuracy.add_row("p95", "P95 error", mono=True)
        self.s_accuracy.add_row("mx", "Max error", mono=True)

        self.s_timing = SectionCard("TIMING  ·  THROUGHPUT")
        self.s_timing.add_row("in_fps", "Input FPS", mono=True)
        self.s_timing.add_row("proc_fps", "Processed FPS", mono=True)
        self.s_timing.add_row("e2e_fps", "End-to-end FPS", mono=True)
        self.s_timing.add_row("frames", "Frame count", mono=True)
        self.s_timing.add_row("dropped", "Dropped frames", mono=True)
        self.s_timing.add_row("duration", "Duration", mono=True)
        self.s_timing.add_row("lat_cur", "Latency (cur)", mono=True)
        self.s_timing.add_row("lat_avg", "Latency (avg)", mono=True)
        self.s_timing.add_row("lat_max", "Latency (max)", mono=True)

        self.s_lock = SectionCard("ACQUISITION & LOCK")
        self.s_lock.add_row("acq_time", "Acquisition time", mono=True)
        self.s_lock.add_row("acq_cnt", "Acq. count", mono=True)
        self.s_lock.add_row("reacq_last", "Re-acq last", mono=True)
        self.s_lock.add_row("reacq_mean", "Re-acq mean", mono=True)
        self.s_lock.add_row("reacq_max", "Re-acq max", mono=True)
        self.s_lock.add_row("reacq_cnt", "Re-acq count", mono=True)
        self.s_lock.add_row("lock_pct", "Lock retention", mono=True)
        self.s_lock.add_row("loss_pct", "Target loss", mono=True)
        self.s_lock.add_row("loss_cnt", "Loss count", mono=True)

        self.s_estimator = SectionCard("ESTIMATOR  ·  EKF-IMM")
        self.s_estimator.add_row("cv", "Model CV", mono=True)
        self.s_estimator.add_row("ca", "Model CA", mono=True)
        self.s_estimator.add_row("mn", "Model MN", mono=True)
        self.s_estimator.add_row("dominant", "Dominant model", mono=True)
        self.s_estimator.add_row("innovation", "Innovation", mono=True)
        self.s_estimator.add_row("gate", "Gate σ", mono=True)

        self.s_controller = SectionCard("CONTROLLER  ·  PAN-TILT")
        self.s_controller.add_row("pan_rate", "Pan rate", mono=True)
        self.s_controller.add_row("tilt_rate", "Tilt rate", mono=True)
        self.s_controller.add_row("pan_ang", "Pan angle", mono=True)
        self.s_controller.add_row("tilt_ang", "Tilt angle", mono=True)
        self.s_controller.add_row("err_px", "Pixel error", mono=True)
        self.s_controller.add_row("err_ang", "Angular error", mono=True)
        self.s_controller.add_row("saturated", "Saturated", mono=True)
        self.s_controller.add_row("sat_cnt", "Saturation count", mono=True)

        self.s_env = SectionCard("ENVIRONMENT & PARAMETERS")
        self.s_env.add_row("cam_type", "Camera Type", mono=True)
        self.s_env.add_row("cam_res", "Resolution", mono=True)
        self.s_env.add_row("cam_fov", "Field of View", mono=True)
        self.s_env.add_row("cam_fps", "Frame Rate", mono=True)
        self.s_env.add_row("cam_init", "Initial Camera", mono=True)
        self.s_env.add_row("world", "World Dimensions", mono=True)
        self.s_env.add_row("tgt_type", "Target Type", mono=True)
        self.s_env.add_row("tgt_count", "Target Count", mono=True)
        self.s_env.add_row("tgt_shape", "Target Shape", mono=True)
        self.s_env.add_row("tgt_size", "Target Size", mono=True)
        self.s_env.add_row("tgt_init", "Initial Target", mono=True)
        self.s_env.add_row("traj", "Motion Trajectory", mono=True)
        self.s_env.add_row("tgt_speed", "Target speed", mono=True)
        self.s_env.add_row("max_pan", "Maximum Pan Speed", mono=True)
        self.s_env.add_row("max_tilt", "Maximum Tilt Speed", mono=True)
        self.s_env.add_row("upd_hz", "Update Rate", mono=True)
        self.s_env.add_row("atmo", "Atmospheric Condition", mono=True)
        self.s_env.add_row("atmo_str", "  Atmo strength", mono=True)
        self.s_env.add_row("noise", "Image Noise", mono=True)
        self.s_env.add_row("gauss", "  Gaussian σ", mono=True)
        self.s_env.add_row("spp", "  S&P prob", mono=True)
        self.s_env.add_row("poisson", "  Poisson", mono=True)
        self.s_env.add_row("jitter", "Camera Jitter", mono=True)
        self.s_env.add_row("platform", "Platform Motion", mono=True)
        self.s_env.add_row("plat_speed", "  Plat speed", mono=True)
        self.s_env.add_row("seed", "Seed", mono=True)
        # gradient / stars / vignetting / brightness — each own field
        self.s_env.add_row("gradient", "Gradient", mono=True)
        self.s_env.add_row("stars", "Stars", mono=True)
        self.s_env.add_row("vignetting", "Vignetting", mono=True)
        self.s_env.add_row("brightness", "Brightness", mono=True)
        self.s_env.add_row("vid_centre", "Video centre", mono=True)

        self.s_counts = SectionCard("COUNTS")
        self.s_counts.add_row("frame_id", "Frame ID", mono=True)
        self.s_counts.add_row("elapsed", "Elapsed", mono=True)

        # layout: 4 columns × 2 rows = 8 cards
        cards = [self.s_tracking, self.s_accuracy, self.s_timing, self.s_lock,
                 self.s_estimator, self.s_controller, self.s_env, self.s_counts]
        for i, c in enumerate(cards):
            r = i // 4
            col = i % 4
            self.grid.addWidget(c, r, col)
        for col in range(4):
            self.grid.setColumnStretch(col, 1)
        self.grid.setRowStretch(0, 1)
        self.grid.setRowStretch(1, 1)

        outer.addWidget(container)

    def update_metrics(self,
                       state, confidence,
                       raw_centroid, fused_pos,
                       error_px, error_angle_deg,
                       mean_err, rmse, max_err, p95,
                       input_fps, proc_fps, e2e_fps,
                       frame_count, dropped_frames, duration_s,
                       latency_ms, avg_proc_ms, max_proc_ms,
                       acq_time, reacq_last, reacq_mean, reacq_max, reacq_count,
                       acq_count, loss_count,
                       lock_pct, loss_pct,
                       valid_detections, valid_pct, avg_conf,
                       model_probs, innovation,
                       pan_rate, tilt_rate, pan_angle, tilt_angle,
                       saturated, saturation_count,
                       atmo, noise_str, jitter, platform, seed,
                       world_size, trajectory, target_speed, target_size,
                        gradient_enabled=False, gradient_type="linear",
                        stars_enabled=False, stars_density=0.0, stars_brightness=0,
                        vignetting_enabled=False, vignetting_strength=0.0,
                        brightness_gain=1.0, brightness_offset=0,
                        vid_centre_x=0.0, vid_centre_y=0.0,
                        cam_type="monochrome", cam_res="640×480", cam_fov="4.0×3.0", cam_fps=30, cam_init="centre",
                        tgt_type="beacon_spot", tgt_count=1, tgt_shape="square", tgt_init="random",
                        max_pan=5.0, max_tilt=5.0, update_hz=30,
                        atmo_strength=0.0, gauss_std=0.0, spp_prob=0.0, poisson_enabled=False, platform_speed=0.0):
        # helper to format
        def fmt(v, nd=1, unit=""):
            if v is None:
                return "—"
            try:
                return f"{v:.{nd}f}{unit}"
            except:
                return str(v)

        # --- TRACKING ---
        col = STATE_COLORS.get(state, COLORS["muted"])
        self.s_tracking.dot.setStyleSheet(f"color:{col}; font-size:10px;")
        self.s_tracking.badge.setText(f"{confidence*100:.0f}%")
        self.s_tracking.badge.setStyleSheet(f"color:{col}; font-size:10px; font-weight:800;")
        self.s_tracking.row("state").set_value(state, color=col)
        if raw_centroid:
            self.s_tracking.row("raw_x").set_value(f"{raw_centroid[0]:.1f}", tooltip="raw centroid X (px)")
            self.s_tracking.row("raw_y").set_value(f"{raw_centroid[1]:.1f}", tooltip="raw centroid Y (px)")
            self.s_tracking.row("raw_x").unit.setText("px")
            self.s_tracking.row("raw_y").unit.setText("px")
        else:
            self.s_tracking.row("raw_x").set_value("—"); self.s_tracking.row("raw_x").unit.setText("px")
            self.s_tracking.row("raw_y").set_value("—"); self.s_tracking.row("raw_y").unit.setText("px")
        if fused_pos:
            self.s_tracking.row("fused_x").set_value(f"{fused_pos[0]:.1f}")
            self.s_tracking.row("fused_y").set_value(f"{fused_pos[1]:.1f}")
            self.s_tracking.row("fused_x").unit.setText("px")
            self.s_tracking.row("fused_y").unit.setText("px")
        else:
            self.s_tracking.row("fused_x").set_value("—"); self.s_tracking.row("fused_x").unit.setText("px")
            self.s_tracking.row("fused_y").set_value("—"); self.s_tracking.row("fused_y").unit.setText("px")
        self.s_tracking.row("conf_cur").set_value(f"{confidence*100:.1f}", color=col)
        self.s_tracking.row("conf_cur").unit.setText("%")
        self.s_tracking.row("conf_avg").set_value(f"{avg_conf*100:.1f}")
        self.s_tracking.row("conf_avg").unit.setText("%")
        self.s_tracking.row("valid_n").set_value(f"{valid_detections}")
        self.s_tracking.row("valid_pct").set_value(f"{valid_pct:.1f}", color=COLORS["success"] if valid_pct>90 else COLORS["muted"])
        self.s_tracking.row("valid_pct").unit.setText("%")

        # --- ACCURACY (each own field) ---
        cur_px_c = COLORS["text"]
        self.s_accuracy.row("cur_px").set_value(fmt(error_px,1), color=cur_px_c)
        self.s_accuracy.row("cur_px").unit.setText("px")
        self.s_accuracy.row("cur_ang").set_value(fmt(error_angle_deg,2) if error_angle_deg is not None else "—", color=cur_px_c)
        self.s_accuracy.row("cur_ang").unit.setText("°")
        self.s_accuracy.row("mean").set_value(fmt(mean_err,1))
        self.s_accuracy.row("mean").unit.setText("px")
        rmse_c = COLORS["success"] if rmse <= 10 else COLORS["danger"]
        self.s_accuracy.row("rmse").set_value(fmt(rmse,1), color=rmse_c)
        self.s_accuracy.row("rmse").unit.setText("px")
        self.s_accuracy.row("p95").set_value(fmt(p95,1))
        self.s_accuracy.row("p95").unit.setText("px")
        self.s_accuracy.row("mx").set_value(fmt(max_err,1), color=COLORS["danger"] if max_err>12 else COLORS["text"])
        self.s_accuracy.row("mx").unit.setText("px")
        self.s_accuracy.badge.setText("PASS ≤10px" if rmse <= 10 else "FAIL")
        self.s_accuracy.badge.setStyleSheet(f"color:{rmse_c}; font-size:10px; font-weight:800;")
        self.s_accuracy.dot.setStyleSheet(f"color:{rmse_c}; font-size:10px;")

        # --- TIMING ---
        fps_c = COLORS["success"] if proc_fps >= 20 else COLORS["danger"]
        self.s_timing.dot.setStyleSheet(f"color:{fps_c}; font-size:10px;")
        self.s_timing.row("in_fps").set_value(fmt(input_fps,1))
        self.s_timing.row("in_fps").unit.setText("Hz")
        self.s_timing.row("proc_fps").set_value(fmt(proc_fps,1), color=fps_c)
        self.s_timing.row("proc_fps").unit.setText("FPS")
        self.s_timing.row("e2e_fps").set_value(fmt(e2e_fps,1))
        self.s_timing.row("e2e_fps").unit.setText("FPS")
        self.s_timing.row("frames").set_value(f"{frame_count}")
        self.s_timing.row("dropped").set_value(f"{dropped_frames}", color=COLORS["danger"] if dropped_frames>0 else COLORS["muted"])
        self.s_timing.row("duration").set_value(fmt(duration_s,1))
        self.s_timing.row("duration").unit.setText("s")
        self.s_timing.row("lat_cur").set_value(fmt(latency_ms,1))
        self.s_timing.row("lat_cur").unit.setText("ms")
        self.s_timing.row("lat_avg").set_value(fmt(avg_proc_ms,1))
        self.s_timing.row("lat_avg").unit.setText("ms")
        self.s_timing.row("lat_max").set_value(fmt(max_proc_ms,1), color=COLORS["danger"] if max_proc_ms>18 else COLORS["text"])
        self.s_timing.row("lat_max").unit.setText("ms")

        # --- LOCK ---
        if acq_time is not None:
            acq_c = COLORS["success"] if acq_time <= 2.0 else COLORS["danger"]
            self.s_lock.row("acq_time").set_value(fmt(acq_time,2), color=acq_c)
            self.s_lock.row("acq_time").unit.setText("s")
        else:
            self.s_lock.row("acq_time").set_value("—")
            self.s_lock.row("acq_time").unit.setText("s")
        self.s_lock.row("acq_cnt").set_value(f"{acq_count}")
        self.s_lock.row("reacq_last").set_value(fmt(reacq_last,2) if reacq_last is not None else "—")
        self.s_lock.row("reacq_last").unit.setText("s")
        reacq_c = COLORS["success"] if (reacq_mean is None or reacq_mean <= 1.0) else COLORS["danger"]
        self.s_lock.row("reacq_mean").set_value(fmt(reacq_mean,2) if reacq_mean is not None else "—", color=reacq_c)
        self.s_lock.row("reacq_mean").unit.setText("s")
        self.s_lock.row("reacq_max").set_value(fmt(reacq_max,2) if reacq_max is not None else "—")
        self.s_lock.row("reacq_max").unit.setText("s")
        self.s_lock.row("reacq_cnt").set_value(f"{reacq_count}")
        self.s_lock.row("lock_pct").set_value(fmt(lock_pct,1), color=COLORS["success"] if lock_pct>95 else COLORS["muted"])
        self.s_lock.row("lock_pct").unit.setText("%")
        loss_c = COLORS["success"] if loss_pct < 5 else COLORS["danger"]
        self.s_lock.row("loss_pct").set_value(fmt(loss_pct,1), color=loss_c)
        self.s_lock.row("loss_pct").unit.setText("%")
        self.s_lock.row("loss_cnt").set_value(f"{loss_count}")
        self.s_lock.badge.setText("✓" if loss_pct < 5 and (acq_time is None or acq_time <= 2.0) else "✗")
        self.s_lock.badge.setStyleSheet(f"color:{COLORS['success'] if (loss_pct <5) else COLORS['danger']}; font-size:10px;")
        self.s_lock.dot.setStyleSheet(f"color:{loss_c}; font-size:10px;")

        # --- ESTIMATOR ---
        self.s_estimator.row("cv").set_value(f"{model_probs[0]:.2f}")
        self.s_estimator.row("ca").set_value(f"{model_probs[1]:.2f}")
        self.s_estimator.row("mn").set_value(f"{model_probs[2]:.2f}")
        dom = max(range(3), key=lambda i: model_probs[i])
        dom_name = ["CV","CA","MN"][dom]
        self.s_estimator.row("dominant").set_value(f"{dom_name} {model_probs[dom]:.2f}", color=COLORS["accent"])
        self.s_estimator.row("innovation").set_value(f"{innovation:.1f}", color=COLORS["warning"] if innovation>5 else COLORS["text"])
        self.s_estimator.row("innovation").unit.setText("σ")
        self.s_estimator.row("gate").set_value("5.0")
        self.s_estimator.row("gate").unit.setText("σ")
        self.s_estimator.dot.setStyleSheet(f"color:{COLORS['accent'] if innovation < 5 else COLORS['warning']}; font-size:10px;")

        # --- CONTROLLER ---
        self.s_controller.row("pan_rate").set_value(f"{pan_rate:+.2f}")
        self.s_controller.row("pan_rate").unit.setText("°/s")
        self.s_controller.row("tilt_rate").set_value(f"{tilt_rate:+.2f}")
        self.s_controller.row("tilt_rate").unit.setText("°/s")
        self.s_controller.row("pan_ang").set_value(fmt(pan_angle,2) if pan_angle is not None else "—")
        self.s_controller.row("pan_ang").unit.setText("°")
        self.s_controller.row("tilt_ang").set_value(fmt(tilt_angle,2) if tilt_angle is not None else "—")
        self.s_controller.row("tilt_ang").unit.setText("°")
        self.s_controller.row("err_px").set_value(fmt(error_px,1) if error_px is not None else "—")
        self.s_controller.row("err_px").unit.setText("px")
        self.s_controller.row("err_ang").set_value(fmt(error_angle_deg,2) if error_angle_deg is not None else "—")
        self.s_controller.row("err_ang").unit.setText("°")
        sat_c = COLORS["danger"] if saturated else COLORS["success"]
        self.s_controller.row("saturated").set_value("SAT" if saturated else "OK", color=sat_c)
        self.s_controller.row("sat_cnt").set_value(f"{saturation_count}", color=sat_c if saturation_count>0 else COLORS["muted"])
        self.s_controller.dot.setStyleSheet(f"color:{sat_c}; font-size:10px;")

        # --- ENVIRONMENT & PARAMETERS — each own field ---
        self.s_env.row("cam_type").set_value(cam_type)
        self.s_env.row("cam_res").set_value(cam_res)
        self.s_env.row("cam_fov").set_value(cam_fov)
        self.s_env.row("cam_fps").set_value(f"{cam_fps}")
        self.s_env.row("cam_fps").unit.setText("Hz")
        self.s_env.row("cam_init").set_value(cam_init)
        self.s_env.row("tgt_type").set_value(tgt_type)
        self.s_env.row("tgt_count").set_value(f"{tgt_count}")
        self.s_env.row("tgt_shape").set_value(tgt_shape)
        self.s_env.row("tgt_init").set_value(tgt_init)
        self.s_env.row("max_pan").set_value(f"{max_pan:.1f}")
        self.s_env.row("max_pan").unit.setText("°/s")
        self.s_env.row("max_tilt").set_value(f"{max_tilt:.1f}")
        self.s_env.row("max_tilt").unit.setText("°/s")
        self.s_env.row("upd_hz").set_value(f"{update_hz}")
        self.s_env.row("upd_hz").unit.setText("Hz")
        self.s_env.row("atmo").set_value(atmo)
        self.s_env.row("atmo_str").set_value(f"{atmo_strength:.2f}")
        self.s_env.row("atmo_str").unit.setText("")
        self.s_env.row("noise").set_value(noise_str if noise_str else "clean")
        self.s_env.row("gauss").set_value(f"{gauss_std:.1f}")
        self.s_env.row("gauss").unit.setText("px")
        self.s_env.row("spp").set_value(f"{spp_prob:.3f}")
        self.s_env.row("poisson").set_value("ON" if poisson_enabled else "OFF", color=COLORS['accent'] if poisson_enabled else COLORS['muted'])
        self.s_env.row("jitter").set_value(f"±{jitter:.0f}")
        self.s_env.row("jitter").unit.setText("px")
        self.s_env.row("platform").set_value(platform)
        self.s_env.row("plat_speed").set_value(f"{platform_speed:.1f}")
        self.s_env.row("plat_speed").unit.setText("px/f")
        self.s_env.row("seed").set_value(f"{seed}")
        self.s_env.row("world").set_value(f"{world_size[0]}×{world_size[1]}")
        self.s_env.row("world").unit.setText("px")
        self.s_env.row("traj").set_value(trajectory)
        self.s_env.row("tgt_speed").set_value(f"{target_speed:.1f}")
        self.s_env.row("tgt_speed").unit.setText("px/f")
        self.s_env.row("tgt_size").set_value(f"{target_size}")
        self.s_env.row("tgt_size").unit.setText("px")
        # --- new env systems each own field ---
        grad_txt = f"{gradient_type} {'ON' if gradient_enabled else 'OFF'}"
        self.s_env.row("gradient").set_value(grad_txt, color=COLORS['accent'] if gradient_enabled else COLORS['muted'])
        self.s_env.row("gradient").unit.setText("")
        self.s_env.row("stars").set_value(f"{'ON' if stars_enabled else 'OFF'} {stars_density:.4f}", color=COLORS['accent'] if stars_enabled else COLORS['muted'])
        self.s_env.row("stars").unit.setText(f"{stars_brightness}" if stars_enabled else "")
        vig_txt = f"{'ON' if vignetting_enabled else 'OFF'} {vignetting_strength:.2f}" if vignetting_enabled else "OFF"
        self.s_env.row("vignetting").set_value(vig_txt, color=COLORS['accent'] if vignetting_enabled else COLORS['muted'])
        self.s_env.row("vignetting").unit.setText("")
        bright_txt = f"×{brightness_gain:.2f} {brightness_offset:+d}"
        self.s_env.row("brightness").set_value(bright_txt)
        self.s_env.row("brightness").unit.setText("")
        vid_txt = f"{vid_centre_x:+.0f},{vid_centre_y:+.0f}" if (vid_centre_x !=0 or vid_centre_y !=0) else "0,0 (centre)"
        self.s_env.row("vid_centre").set_value(vid_txt, color=COLORS['accent'] if (vid_centre_x !=0 or vid_centre_y !=0) else COLORS['muted'])
        self.s_env.row("vid_centre").unit.setText("px")

        # --- COUNTS ---
        self.s_counts.row("frame_id").set_value(f"{frame_count}")
        self.s_counts.row("elapsed").set_value(fmt(duration_s,1))
        self.s_counts.row("elapsed").unit.setText("s")
