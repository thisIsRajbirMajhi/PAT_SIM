from PyQt5.QtWidgets import QWidget, QLabel, QGridLayout, QFrame, QVBoxLayout, QHBoxLayout, QProgressBar
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from .theme import COLORS, STATE_COLORS


class _Card(QFrame):
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.setStyleSheet(f"QFrame#Card {{ background:{COLORS['surface']}; border:1px solid {COLORS['border']}; border-radius:8px; }}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(3)

        head = QHBoxLayout()
        head.setSpacing(6)
        self.dot = QLabel("●")
        self.dot.setStyleSheet(f"color:{COLORS['subtle']}; font-size: 7px;")
        self.dot.setFixedWidth(10)
        t = QLabel(title)
        t.setStyleSheet(f"color:{COLORS['muted']}; font-size:9px; font-weight:700; letter-spacing:0.7px;")
        head.addWidget(self.dot)
        head.addWidget(t)
        head.addStretch()
        self.badge = QLabel("")
        self.badge.setStyleSheet(f"color:{COLORS['subtle']}; font-size:9px; font-weight:700;")
        head.addWidget(self.badge)
        lay.addLayout(head)

        self.value = QLabel("—")
        self.value.setStyleSheet(f"color:{COLORS['text']}; font-size:14px; font-weight:800; letter-spacing:-0.2px;")
        self.value.setWordWrap(True)
        lay.addWidget(self.value)

        # two secondary lines for dense metrics
        self.sub = QLabel("")
        self.sub.setStyleSheet(f"color:{COLORS['muted']}; font-size:10px; font-family:'JetBrains Mono','Consolas',monospace;")
        self.sub.setWordWrap(True)
        lay.addWidget(self.sub)

        self.sub2 = QLabel("")
        self.sub2.setStyleSheet(f"color:{COLORS['subtle']}; font-size:9px; font-family:'JetBrains Mono','Consolas',monospace;")
        self.sub2.setWordWrap(True)
        lay.addWidget(self.sub2)

        self.bar = QProgressBar()
        self.bar.setFixedHeight(4)
        self.bar.setTextVisible(False)
        self.bar.setStyleSheet(f"""
            QProgressBar {{ background:{COLORS['faint']}; border:1px solid {COLORS['border']}; border-radius:2px; }}
            QProgressBar::chunk {{ background:{COLORS['accent']}; border-radius:1px; }}
        """)
        self.bar.setMaximum(100)
        self.bar.setValue(0)
        self.bar.hide()
        lay.addWidget(self.bar)
        lay.addStretch()


class Dashboard(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.grid = QGridLayout(self)
        self.grid.setSpacing(8)
        self.grid.setContentsMargins(0, 0, 0, 0)

        # 8 cards to cover all PDF-required live metrics without crowding
        self.c_state = _Card("Tracking  ·  Detection")
        self.c_acc = _Card("Accuracy  ·  px / °")
        self.c_time = _Card("Timing  ·  Throughput")
        self.c_lock = _Card("Acquisition & Lock")
        self.c_est = _Card("Estimator  ·  EKF-IMM")
        self.c_ctrl = _Card("Controller  ·  Pan-Tilt")
        self.c_env = _Card("Environment")
        self.c_counts = _Card("Counts  ·  Frames")

        # layout: 4 + 4
        cards = [self.c_state, self.c_acc, self.c_time, self.c_lock, self.c_est, self.c_ctrl, self.c_env, self.c_counts]
        for i, c in enumerate(cards):
            r = i // 4
            col = i % 4
            self.grid.addWidget(c, r, col)
        for col in range(4):
            self.grid.setColumnStretch(col, 1)
        self.grid.setRowStretch(0, 1)
        self.grid.setRowStretch(1, 1)

    # extended signature — all live metrics from PDF §9.1 + §28
    def update_metrics(self,
                       state, confidence,
                       raw_centroid, fused_pos,          # (x,y) or None
                       error_px, error_angle_deg,        # current
                       mean_err, rmse, max_err, p95,
                       # timing
                       input_fps, proc_fps, e2e_fps,
                       frame_count, dropped_frames, duration_s,
                       latency_ms, avg_proc_ms, max_proc_ms,
                       # acquisition/lock
                       acq_time, reacq_last, reacq_mean, reacq_max, reacq_count,
                       acq_count, loss_count,
                       lock_pct, loss_pct,
                       valid_detections, valid_pct, avg_conf,
                       # estimator
                       model_probs, innovation,
                       # controller
                       pan_rate, tilt_rate, pan_angle, tilt_angle,
                       saturated, saturation_count,
                       # environment
                       atmo, noise_str, jitter, platform, seed,
                       world_size, trajectory, target_speed, target_size):
        # — Tracking & Detection —
        col = STATE_COLORS.get(state, COLORS["muted"])
        self.c_state.dot.setStyleSheet(f"color:{col}; font-size:8px;")
        self.c_state.badge.setText(f"{confidence*100:.0f}%")
        self.c_state.badge.setStyleSheet(f"color:{col}; font-size:9px; font-weight:800;")
        self.c_state.value.setText(state)
        self.c_state.value.setStyleSheet(f"color:{col}; font-size:14px; font-weight:800;")
        rc = f"({raw_centroid[0]:.0f},{raw_centroid[1]:.0f})" if raw_centroid else "—"
        fp = f"({fused_pos[0]:.0f},{fused_pos[1]:.0f})" if fused_pos else "—"
        self.c_state.sub.setText(f"raw {rc}  →  fused {fp}")
        self.c_state.sub2.setText(f"valid {valid_detections}  ·  {valid_pct:.1f}%  ·  avg conf {avg_conf*100:.0f}%")

        # — Accuracy —
        rmse_col = COLORS["success"] if rmse <= 10 else COLORS["danger"]
        self.c_acc.bar.show()
        self.c_acc.bar.setValue(int(min(100, (rmse/10)*100)))
        self.c_acc.bar.setStyleSheet(f"""
            QProgressBar {{ background:{COLORS['faint']}; border:1px solid {COLORS['border']}; border-radius:2px; }}
            QProgressBar::chunk {{ background:{rmse_col}; }}
        """)
        cur_px = f"{error_px:.1f}px" if error_px is not None else "—"
        cur_ang = f"{error_angle_deg:.2f}°" if error_angle_deg is not None else "—"
        self.c_acc.value.setText(f"{cur_px}  ·  {cur_ang}")
        self.c_acc.value.setStyleSheet(f"color:{COLORS['text']}; font-size:12px; font-weight:800;")
        self.c_acc.badge.setText("PASS ≤10px" if rmse <= 10 else "FAIL >10px")
        self.c_acc.badge.setStyleSheet(f"color:{rmse_col}; font-size:9px; font-weight:800;")
        self.c_acc.sub.setText(f"mean {mean_err:.1f}  ·  RMSE {rmse:.1f}  ·  P95 {p95:.1f}")
        self.c_acc.sub2.setText(f"max {max_err:.1f}  ·  gate 10px")

        # — Timing & Throughput —
        fps_col = COLORS["success"] if proc_fps >= 20 else COLORS["danger"]
        self.c_time.dot.setStyleSheet(f"color:{fps_col}; font-size:8px;")
        self.c_time.value.setText(f"{proc_fps:.1f} FPS")
        self.c_time.badge.setText(f"{latency_ms:.1f} ms")
        self.c_time.badge.setStyleSheet(f"color:{COLORS['muted']}; font-size:9px; font-weight:700;")
        self.c_time.sub.setText(f"in {input_fps:.0f}  ·  proc {proc_fps:.1f}  ·  e2e {e2e_fps:.1f}")
        self.c_time.sub2.setText(f"avg {avg_proc_ms:.1f}ms  ·  max {max_proc_ms:.1f}ms  ·  budget {1000/input_fps:.1f}ms")

        # — Acquisition & Lock —
        if acq_time is not None:
            acq_ok = acq_time <= 2.0
            self.c_lock.value.setText(f"Acq {acq_time:.2f}s")
            self.c_lock.badge.setText("✓ ≤2.0s" if acq_ok else "✗ >2.0s")
            self.c_lock.badge.setStyleSheet(f"color:{COLORS['success'] if acq_ok else COLORS['danger']}; font-size:9px; font-weight:800;")
        else:
            self.c_lock.value.setText("Acq —")
            self.c_lock.badge.setText("—")
            self.c_lock.badge.setStyleSheet(f"color:{COLORS['muted']}; font-size:9px;")
        reacq_txt = f"{reacq_last:.2f}s" if reacq_last is not None else "—"
        reacq_ok = (reacq_mean is None) or (reacq_mean <= 1.0)
        self.c_lock.sub.setText(f"re-acq last {reacq_txt}  ·  mean {(reacq_mean or 0):.2f}s  ·  max {(reacq_max or 0):.2f}s {'✓' if reacq_ok else '✗'} ≤1.0s")
        loss_ok = loss_pct < 5
        self.c_lock.sub2.setText(f"lock {lock_pct:.1f}%  ·  loss {loss_pct:.1f}% {'✓' if loss_ok else '✗'}<5%  ·  ×{reacq_count}")
        self.c_lock.bar.show()
        self.c_lock.bar.setValue(int(lock_pct))
        self.c_lock.bar.setStyleSheet(f"""
            QProgressBar {{ background:{COLORS['faint']}; border:1px solid {COLORS['border']}; border-radius:2px; }}
            QProgressBar::chunk {{ background:{COLORS['success'] if loss_ok else COLORS['danger']}; }}
        """)

        # — Estimator IMM —
        self.c_est.value.setText(f"CV {model_probs[0]:.2f}  CA {model_probs[1]:.2f}  MN {model_probs[2]:.2f}")
        dom = max(range(3), key=lambda i: model_probs[i])
        dom_name = ["CV","CA","MN"][dom]
        self.c_est.badge.setText(f"{dom_name} {model_probs[dom]:.2f}")
        self.c_est.badge.setStyleSheet(f"color:{COLORS['accent']}; font-size:9px; font-weight:800;")
        self.c_est.sub.setText(f"innovation {innovation:.1f}σ  ·  gate 5σ  ·  H tan(α)")
        self.c_est.sub2.setText(f"state [α,β,α̇,β̇,α̈,β̈]  ·  cov tr {innovation:.1f}")
        self.c_est.dot.setStyleSheet(f"color:{COLORS['accent'] if innovation < 12 else COLORS['warning']}; font-size:8px;")

        # — Controller —
        sat_txt = "SAT" if saturated else "OK"
        sat_col = COLORS["danger"] if saturated else COLORS["success"]
        self.c_ctrl.value.setText(f"pan {pan_rate:+.1f}  tilt {tilt_rate:+.1f} °/s")
        self.c_ctrl.badge.setText(f"{sat_txt} ×{saturation_count}")
        self.c_ctrl.badge.setStyleSheet(f"background:{sat_col}; color:white; font-size:8px; font-weight:800; padding:1px 5px; border-radius:3px;")
        pan_ang = f"{pan_angle:+.2f}°" if pan_angle is not None else "—"
        tilt_ang = f"{tilt_angle:+.2f}°" if tilt_angle is not None else "—"
        self.c_ctrl.sub.setText(f"angle {pan_ang} / {tilt_ang}  ·  err {cur_px} {cur_ang}")
        self.c_ctrl.sub2.setText(f"deadzone 2.0px  ·  limit 5.0°/s  ·  PID Kp1.2 Ki0.05 Kd0.15")
        self.c_ctrl.dot.setStyleSheet(f"color:{sat_col}; font-size:8px;")

        # — Environment —
        self.c_env.value.setText(f"{atmo}  ·  {noise_str}")
        self.c_env.sub.setText(f"jitter ±{jitter:.0f}px  ·  plat {platform}  ·  seed {seed}")
        self.c_env.sub2.setText(f"world {world_size[0]}×{world_size[1]}  ·  {trajectory} {target_speed:.1f}px/f  ·  sz {target_size}px")
        self.c_env.dot.setStyleSheet(f"color:{COLORS['muted']}; font-size:8px;")

        # — Counts / Frames —
        self.c_counts.value.setText(f"#{frame_count}  ·  {duration_s:.1f}s")
        self.c_counts.badge.setText(f"drop {dropped_frames}")
        self.c_counts.badge.setStyleSheet(f"color:{COLORS['danger'] if dropped_frames>0 else COLORS['muted']}; font-size:9px; font-weight:700;")
        self.c_counts.sub.setText(f"acq ×{acq_count}  ·  loss ×{loss_count}  ·  re-acq ×{reacq_count}")
        self.c_counts.sub2.setText(f"valid {valid_detections}/{frame_count}  ·  locked {lock_pct:.0f}%")
        self.c_counts.dot.setStyleSheet(f"color:{COLORS['muted']}; font-size:8px;")

    # legacy compat shim — old callers still work
    def update_metrics_legacy(self, *a, **kw):
        return self.update_metrics(*a, **kw)
