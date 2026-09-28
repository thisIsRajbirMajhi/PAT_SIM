"""Live dashboard — exact replica of the requested pill layout.

Dark bar (#595959), white labels, light value pills (#E8E8E8),
telemetry strip with TRACK ID / DET CONF / TRACK AGE / LAST DETECT / FOV STATUS.
"""
from PyQt5.QtWidgets import QWidget, QLabel, QGridLayout, QFrame, QVBoxLayout, QHBoxLayout
from PyQt5.QtCore import Qt

BAR = "#595959"
VALUE_PILL = "#E8E8E8"


class Dashboard(QWidget):
    """Compact live dashboard matching the reference screenshot exactly."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background: {BAR};")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        grid_wrap = QWidget()
        grid_wrap.setStyleSheet("background: transparent;")
        outer.addWidget(grid_wrap)
        grid = QGridLayout(grid_wrap)
        grid.setContentsMargins(60, 28, 60, 14)
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(12)
        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 0)
        grid.setColumnStretch(3, 1)
        self._grid = grid

        self._values = {}

        def add_row(r, c_label, label_text, key):
            lab = QLabel(label_text)
            lab.setStyleSheet("color: white; font-size: 15px; font-weight: 700; background: transparent;")
            val = QLabel("—")
            val.setAlignment(Qt.AlignCenter)
            val.setMinimumWidth(190)
            val.setFixedHeight(30)
            val.setStyleSheet(
                f"QLabel {{ background: {VALUE_PILL}; color: #111111; "
                "border-radius: 15px; font-size: 13px; font-weight: 600; }}"
            )
            val.setTextInteractionFlags(Qt.TextSelectableByMouse)
            grid.addWidget(lab, r, c_label * 2)
            grid.addWidget(val, r, c_label * 2 + 1)
            self._values[key] = val

        # top group — exactly as screenshot
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

        # telemetry strip — exactly as screenshot
        strip = QFrame()
        strip.setStyleSheet("QFrame { background: transparent; border: none; border-top: 1px solid #6B7280; }")
        strip_lay = QHBoxLayout(strip)
        strip_lay.setContentsMargins(60, 10, 60, 22)
        strip_lay.setSpacing(18)
        self._tele_vals = {}
        for _tkey, _caption in (("track_id", "TRACK ID"), ("det_conf", "DET CONF"),
                                ("age", "TRACK AGE"), ("last", "LAST DETECT"),
                                ("fov", "FOV STATUS"), ("search", "SEARCH")):
            _box = QVBoxLayout()
            _box.setSpacing(4)
            _cap = QLabel(_caption)
            _cap.setStyleSheet(
                "color: #CBD5E1; font-size: 10px; font-weight: 800; "
                "letter-spacing: 0.6px; background: transparent;")
            _val = QLabel("—")
            _val.setAlignment(Qt.AlignCenter)
            _val.setMinimumWidth(150)
            _val.setFixedHeight(30)
            _val.setStyleSheet(
                f"QLabel {{ background: {VALUE_PILL}; color: #111111; "
                "border-radius: 15px; font-size: 13px; font-weight: 600; }}")
            _val.setTextInteractionFlags(Qt.TextSelectableByMouse)
            _box.addWidget(_cap)
            _box.addWidget(_val)
            _wrap = QWidget()
            _wrap.setStyleSheet("background: transparent;")
            _wrap.setLayout(_box)
            strip_lay.addWidget(_wrap)
            self._tele_vals[_tkey] = _val
        strip_lay.addStretch()
        outer.addWidget(strip)

    # ---- compat: old card API had row(key).set_value(...) ----
    def row(self, key):
        val = self._values.get(key, self._tele_vals.get(key))
        if val is None:
            raise KeyError(key)

        class _Row:
            def __init__(self, lbl):
                self.val = lbl
                self.unit = QLabel("")

            def set_value(self, text, color=None, tooltip=None):
                self.val.setText(text)

        return _Row(val)

    def reset(self):
        for v in self._values.values():
            v.setText("—")
        for v in self._tele_vals.values():
            v.setText("—")

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
                       atmo_strength=0.0, gauss_std=0.0, spp_prob=0.0, poisson_enabled=False, platform_speed=0.0,
                       # live per-track telemetry for the bottom strip
                       track_label=None, det_conf=None, track_age_s=None,
                       last_detect_age_s=None, fov=None, search_case=None):
        V = self._values
        V["state"].setText(str(state) if state is not None else "—")
        V["valid"].setText(f"{int(valid_detections)}")
        try:
            V["conf"].setText(f"{float(avg_conf) * 100:.1f}%" if avg_conf else "—")
        except Exception:
            V["conf"].setText("—")
        try:
            V["raw"].setText(f"{raw_centroid[0]:.1f}, {raw_centroid[1]:.1f}"
                             if raw_centroid is not None else "—")
        except Exception:
            V["raw"].setText("—")
        try:
            V["fused"].setText(f"{fused_pos[0]:.1f}, {fused_pos[1]:.1f}"
                               if fused_pos is not None else "—")
        except Exception:
            V["fused"].setText("—")
        try:
            V["fps"].setText(f"{float(proc_fps):.1f}")
        except Exception:
            V["fps"].setText("—")
        try:
            V["lat_avg"].setText(f"{float(avg_proc_ms):.1f} ms")
        except Exception:
            V["lat_avg"].setText("—")
        try:
            V["lat_max"].setText(f"{float(max_proc_ms):.1f} ms")
        except Exception:
            V["lat_max"].setText("—")
        try:
            V["trk_err"].setText(f"{float(mean_err):.2f} px")
        except Exception:
            V["trk_err"].setText("—")
        V["ang_err"].setText(f"{float(error_angle_deg):.2f}°"
                             if error_angle_deg is not None else "—")
        try:
            V["mean_max"].setText(f"{float(mean_err):.1f} / {float(max_err):.1f} px")
        except Exception:
            V["mean_max"].setText("—")
        try:
            V["rmse_p95"].setText(f"{float(rmse):.1f} / {float(p95):.1f} px")
        except Exception:
            V["rmse_p95"].setText("—")
        try:
            V["lock"].setText(f"{float(lock_pct):.1f}%")
        except Exception:
            V["lock"].setText("—")
        try:
            V["loss"].setText(f"{float(loss_pct):.1f}% ({int(loss_count)})")
        except Exception:
            V["loss"].setText("—")
        try:
            if acq_time is not None:
                V["acq"].setText(f"{float(acq_time):.2f}s ({int(acq_count)})")
            else:
                V["acq"].setText(f"— ({int(acq_count)})")
        except Exception:
            V["acq"].setText("—")
        try:
            if reacq_mean is not None:
                V["reacq"].setText(f"{float(reacq_mean):.2f}s ({int(reacq_count)})")
            else:
                V["reacq"].setText(f"— ({int(reacq_count)})")
        except Exception:
            V["reacq"].setText("—")
        # bottom strip
        T = self._tele_vals
        T["track_id"].setText(str(track_label) if track_label is not None else "—")
        T["det_conf"].setText(f"{float(det_conf) * 100:.0f}%"
                              if det_conf is not None else "—")
        T["age"].setText(f"{float(track_age_s):.2f} s"
                         if track_age_s is not None else "—")
        T["last"].setText(f"{float(last_detect_age_s):.2f} s"
                          if last_detect_age_s is not None else "—")
        T["fov"].setText(str(fov) if fov is not None else "—")
        try:
            T["search"].setText(str(search_case) if search_case else "—")
        except Exception:
            pass
