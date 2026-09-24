from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QScrollArea, QWidget, QPushButton, QGridLayout
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from .theme import COLORS
import os

class BenchmarkResultDialog(QDialog):
    """
    Modal shown when simulation completes — clearly separates
    BEATEN vs NOT BEATEN benchmarks with values vs thresholds.
    """
    def __init__(self, summary, cfg, run_dir, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Benchmark Results — FSOC Tracker")
        self.setModal(True)
        self.resize(720, 560)
        self.setStyleSheet(f"QDialog {{ background: {COLORS['bg']}; }}")

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        # Overall banner
        thresholds = {
            "acq": 2.0,
            "reacq": 1.0,
            "rmse": 10.0,
            "loss": 5.0,
            "fps": 20.0,
        }
        # determine overall
        checks = []
        # build list of (key, name, value, threshold, unit, beaten, fmt)
        acq = summary.get("acquisition_time_s")
        reacq_mean = summary.get("reacquisition_mean_s")
        reacq_max = summary.get("reacquisition_max_s")
        rmse = summary.get("rmse_px", 0)
        mean_err = summary.get("mean_error_px", 0)
        max_err = summary.get("max_error_px", 0)
        p95 = summary.get("p95_error_px", 0)
        loss = summary.get("target_loss_pct", 100)
        lock = summary.get("lock_retention_pct", 0)
        fps = summary.get("avg_fps", 0)
        # also additional
        avg_proc = summary.get("avg_processing_ms", 0)

        def is_beaten(name, val, thr, cmp="le"):
            if val is None:
                return False
            if cmp == "le":
                return val <= thr
            if cmp == "lt":
                return val < thr
            if cmp == "ge":
                return val >= thr
            return False

        items = [
            ("Acquisition Time", acq, thresholds["acq"], "s", "le", f"{acq:.3f}s" if acq is not None else "—", f"≤{thresholds['acq']:.1f}s"),
            ("Re-acquisition (mean)", reacq_mean, thresholds["reacq"], "s", "le", f"{reacq_mean:.3f}s" if reacq_mean is not None else "— (no loss)", f"≤{thresholds['reacq']:.1f}s"),
            ("Re-acquisition (max)", reacq_max, thresholds["reacq"], "s", "le", f"{reacq_max:.3f}s" if reacq_max is not None else "—", f"≤{thresholds['reacq']:.1f}s"),
            ("Tracking RMSE", rmse, thresholds["rmse"], "px", "le", f"{rmse:.2f} px", f"≤{thresholds['rmse']:.0f} px"),
            ("Mean Error", mean_err, thresholds["rmse"], "px", "le", f"{mean_err:.2f} px", f"≤{thresholds['rmse']:.0f} px"),
            ("Max Error", max_err, None, "px", None, f"{max_err:.2f} px", "—"),
            ("P95 Error", p95, None, "px", None, f"{p95:.2f} px", "—"),
            ("Target Loss", loss, thresholds["loss"], "%", "lt", f"{loss:.1f}%", f"<{thresholds['loss']:.0f}%"),
            ("Lock Retention", lock, 95.0, "%", "ge", f"{lock:.1f}%", f"≥95%"),
            ("Processing Speed", fps, thresholds["fps"], "FPS", "ge", f"{fps:.1f} FPS", f"≥{thresholds['fps']:.0f} FPS"),
            ("Avg Proc. Time", avg_proc, None, "ms", None, f"{avg_proc:.1f} ms", "—"),
        ]

        beaten = []
        not_beaten = []
        neutral = []
        for name, val, thr, unit, cmp, val_str, thr_str in items:
            if thr is None:
                neutral.append((name, val_str, thr_str, None))
            else:
                ok = is_beaten(name, val, thr, cmp)
                if ok:
                    beaten.append((name, val_str, thr_str, val))
                else:
                    not_beaten.append((name, val_str, thr_str, val))

        all_beaten = len(not_beaten) == 0
        # filter neutral out of verdict? neutral are not counted as fail
        # overall beaten means all thresholded are beaten
        actually_beaten = all([
            is_beaten("acq", acq, 2.0, "le") if acq is not None else False,
            is_beaten("reacq", reacq_mean if reacq_mean is not None else 0, 1.0, "le") if reacq_mean is not None or summary.get("reacquisition_count",0)==0 else True,
            is_beaten("rmse", rmse, 10.0, "le"),
            is_beaten("loss", loss, 5.0, "lt"),
            is_beaten("fps", fps, 20.0, "ge"),
        ])

        # Banner
        banner = QFrame()
        banner.setStyleSheet(f"QFrame {{ background: {'#f0fdf4' if actually_beaten else '#fef2f2'}; border:1px solid {'#bbf7d0' if actually_beaten else '#fecaca'}; border-radius:10px; }}")
        blay = QVBoxLayout(banner)
        blay.setContentsMargins(14, 12, 14, 12)
        icon = "✓" if actually_beaten else "✗"
        title = QLabel(f"{icon}  {'All Benchmarks Beaten' if actually_beaten else 'Some Benchmarks Not Beaten'}")
        title.setStyleSheet(f"color:{'#15803d' if actually_beaten else '#b91c1c'}; font-size:14px; font-weight:800;")
        blay.addWidget(title)
        sub = QLabel(f"Run: {os.path.basename(run_dir) if run_dir else '—'}  •  Seed {cfg.get('experiment',{}).get('seed','?')}  •  {cfg.get('target',{}).get('trajectory','?')}  •  {summary.get('total_frames',0)} frames  •  {summary.get('duration_s',0):.1f}s")
        sub.setStyleSheet(f"color:{COLORS['muted']}; font-size:11px;")
        blay.addWidget(sub)
        if run_dir:
            run_lbl = QLabel(f"Logs: {os.path.abspath(run_dir)}")
            run_lbl.setStyleSheet(f"color:{COLORS['subtle']}; font-size:10px; font-family:'JetBrains Mono',Consolas,monospace;")
            run_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
            blay.addWidget(run_lbl)
        root.addWidget(banner)

        # Scroll area for two sections
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet(f"QScrollArea {{ background: transparent; border: none; }}")
        inner = QWidget()
        inner_lay = QVBoxLayout(inner)
        inner_lay.setContentsMargins(0, 0, 0, 0)
        inner_lay.setSpacing(12)

        def make_section(title_text, items_list, is_beaten_section):
            sec = QFrame()
            sec.setStyleSheet(f"QFrame {{ background: white; border:1px solid {COLORS['border']}; border-radius:10px; }}")
            slay = QVBoxLayout(sec)
            slay.setContentsMargins(12, 10, 12, 10)
            slay.setSpacing(8)
            hdr = QHBoxLayout()
            dot = QLabel("●")
            dot.setStyleSheet(f"color:{'#16a34a' if is_beaten_section else '#dc2626'}; font-size:10px;")
            dot.setFixedWidth(12)
            t = QLabel(title_text)
            t.setStyleSheet(f"color:{COLORS['text']}; font-size:11px; font-weight:800; letter-spacing:0.4px;")
            hdr.addWidget(dot)
            hdr.addWidget(t)
            hdr.addStretch()
            cnt = QLabel(f"{len(items_list)} parameters")
            cnt.setStyleSheet(f"color:{COLORS['muted']}; font-size:10px;")
            hdr.addWidget(cnt)
            slay.addLayout(hdr)
            # separator
            sep = QFrame()
            sep.setFixedHeight(1)
            sep.setStyleSheet(f"background:{COLORS['border']}; border:none;")
            slay.addWidget(sep)
            # grid header
            gh = QHBoxLayout()
            for txt, w in [("Parameter", 180), ("Value", 110), ("Threshold", 90), ("Status", 60)]:
                l = QLabel(txt)
                l.setStyleSheet(f"color:{COLORS['subtle']}; font-size:9px; font-weight:700; letter-spacing:0.5px;")
                l.setFixedWidth(w)
                if txt == "Parameter":
                    l.setAlignment(Qt.AlignLeft)
                else:
                    l.setAlignment(Qt.AlignCenter)
                gh.addWidget(l)
            gh.addStretch()
            slay.addLayout(gh)
            # rows
            for name, val_str, thr_str, raw_val in items_list:
                row = QFrame()
                row.setStyleSheet(f"QFrame {{ background:{COLORS['faint'] if is_beaten_section else '#fef2f2'}; border:1px solid {COLORS['border']}; border-radius:6px; }}")
                rlay = QHBoxLayout(row)
                rlay.setContentsMargins(8, 6, 8, 6)
                n = QLabel(name)
                n.setStyleSheet(f"color:{COLORS['text']}; font-size:11px; font-weight:600;")
                n.setFixedWidth(180)
                v = QLabel(val_str)
                v.setStyleSheet(f"color:{COLORS['text']}; font-size:11px; font-family:'JetBrains Mono',Consolas,monospace; font-weight:700;")
                v.setFixedWidth(110)
                v.setAlignment(Qt.AlignCenter)
                thr_lbl = QLabel(thr_str)
                thr_lbl.setStyleSheet(f"color:{COLORS['muted']}; font-size:11px; font-family:'JetBrains Mono',Consolas,monospace;")
                thr_lbl.setFixedWidth(90)
                thr_lbl.setAlignment(Qt.AlignCenter)
                # status pill
                if thr_str == "—":
                    status = QLabel("—")
                    status.setStyleSheet(f"color:{COLORS['subtle']}; font-size:11px;")
                else:
                    # determine beaten for this row
                    # find original item to know cmp — recompute quickly
                    # we already have is_beaten_section flag, so use it for color
                    ok = is_beaten_section
                    # but for neutral section, not used
                    status = QLabel("BEATEN" if ok else "NOT BEATEN")
                    bg = "#16a34a" if ok else "#dc2626"
                    status.setStyleSheet(f"background:{bg}; color:white; font-size:9px; font-weight:800; padding:2px 6px; border-radius:4px;")
                status.setFixedWidth(80)
                status.setAlignment(Qt.AlignCenter)
                rlay.addWidget(n)
                rlay.addWidget(v)
                rlay.addWidget(thr_lbl)
                rlay.addWidget(status)
                rlay.addStretch()
                slay.addWidget(row)
            return sec

        # Beaten section (green)
        if beaten:
            inner_lay.addWidget(make_section(f"BEATEN  ·  {len(beaten)} parameters", beaten, True))
        # Not beaten section (red)
        if not_beaten:
            inner_lay.addWidget(make_section(f"NOT BEATEN  ·  {len(not_beaten)} parameters", not_beaten, False))
        # Neutral / info only
        if neutral:
            inner_lay.addWidget(make_section(f"INFO  ·  {len(neutral)} parameters", neutral, True))

        # Additional info
        info = QLabel("Thresholds per spec:  Acq ≤2.0s  ·  Re-acq ≤1.0s  ·  RMSE ≤10px  ·  Loss <5%  ·  FPS ≥20  ·  Gate 5σ")
        info.setStyleSheet(f"color:{COLORS['subtle']}; font-size:10px; background:{COLORS['faint']}; border:1px solid {COLORS['border']}; border-radius:6px; padding:8px 10px;")
        info.setAlignment(Qt.AlignCenter)
        inner_lay.addWidget(info)

        inner_lay.addStretch()
        scroll.setWidget(inner)
        root.addWidget(scroll, 1)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.btn_open = QPushButton("Open Logs Folder")
        self.btn_open.setFixedHeight(32)
        self.btn_open.setCursor(Qt.PointingHandCursor)
        btn_row.addWidget(self.btn_open)
        self.btn_close = QPushButton("Close")
        self.btn_close.setObjectName("Primary")
        self.btn_close.setFixedHeight(32)
        self.btn_close.setCursor(Qt.PointingHandCursor)
        self.btn_close.setMinimumWidth(90)
        btn_row.addWidget(self.btn_close)
        root.addLayout(btn_row)

        self.btn_close.clicked.connect(self.accept)
        self.btn_open.clicked.connect(lambda: self._open_folder(run_dir))

        self.run_dir = run_dir

    def _open_folder(self, path):
        if not path or not os.path.isdir(path):
            return
        try:
            import subprocess, sys
            if sys.platform.startswith("win"):
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception:
            pass
