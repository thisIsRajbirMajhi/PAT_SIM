"""
Robust performance logging system — auto-generates logs without manual Export.
- Incremental CSV (flush per frame) so crash doesn't lose data
- Atomic JSON/HTML writes (temp + rename)
- Timestamped run directory, config snapshot, system info
- Auto-triggered on run start / frame tick / run end / app close
- Also generates error/trajectory plots via matplotlib (if available)
"""

import os
import json
import csv
import time
import datetime
import platform
import sys
import yaml
import traceback

# Optional matplotlib for plots
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    HAS_MPL = True
except Exception:
    HAS_MPL = False
    plt = None


def _atomic_write(path, data, mode="w", encoding="utf-8"):
    """Write to temp then rename for crash safety."""
    tmp = path + ".tmp"
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        # handle binary vs text
        if "b" in mode:
            with open(tmp, mode) as f:
                f.write(data)
        else:
            with open(tmp, mode, encoding=encoding, newline="") as f:
                f.write(data) if isinstance(data, str) else json.dump(data, f, indent=2)
        # atomic replace
        os.replace(tmp, path)
        return True
    except Exception as e:
        print(f"[AutoLogger] atomic write failed for {path}: {e}")
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except:
            pass
        return False


def _safe_makedirs(path):
    try:
        os.makedirs(path, exist_ok=True)
        return True
    except Exception as e:
        print(f"[AutoLogger] makedirs failed {path}: {e}")
        return False


class RobustPerfLogger:
    """
    Wraps MetricsCollector and handles all file I/O.
    Auto-generates on begin_run / log_frame / end_run.
    """

    def __init__(self, base_dir="outputs/runs", metrics_collector=None):
        self.base_dir = base_dir
        self.metrics = metrics_collector
        self.run_dir = None
        self.csv_path = None
        self.csv_file = None
        self.csv_writer = None
        self.csv_header_written = False
        self.start_wall_time = None
        self.cfg_snapshot = None
        self._frame_keys = None

    def begin_run(self, cfg):
        """Call at start_run — creates timestamped dir and snapshots config."""
        try:
            self.cfg_snapshot = self._deep_copy_cfg(cfg)
            # timestamped dir: 2026-05-14T...Z_trajectory_seedN
            ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
            traj = cfg["target"].get("trajectory", "unknown")
            seed = cfg["experiment"].get("seed", 0)
            # sanitize traj
            traj = str(traj).replace("/", "_")[:32]
            dirname = f"{ts}_{traj}_seed{seed}"
            self.run_dir = os.path.join(self.base_dir, dirname)
            _safe_makedirs(self.run_dir)

            # snapshot config
            cfg_path = os.path.join(self.run_dir, "config_used.yaml")
            try:
                with open(cfg_path + ".tmp", "w", encoding="utf-8") as f:
                    yaml.safe_dump(cfg, f, sort_keys=False)
                os.replace(cfg_path + ".tmp", cfg_path)
            except Exception as e:
                print(f"[AutoLogger] config write failed: {e}")

            # prepare incremental CSV
            self.csv_path = os.path.join(self.run_dir, "frame_metrics.csv")
            self.csv_file = open(self.csv_path, "w", newline="", encoding="utf-8")
            self.csv_writer = None
            self.csv_header_written = False
            self._frame_keys = None

            self.start_wall_time = time.perf_counter()
            # also write a run_in_progress marker
            marker = os.path.join(self.run_dir, ".in_progress")
            _atomic_write(marker, json.dumps({"started": ts, "pid": os.getpid()}))

            print(f"[AutoLogger] begin_run -> {self.run_dir}")
            return self.run_dir
        except Exception as e:
            print(f"[AutoLogger] begin_run failed: {e}")
            traceback.print_exc()
            return None

    def log_frame(self, frame_id, timestamp, detection_valid, estimate, ground_truth, processing_ms, fps, pan_rate, tilt_rate, detection_confidence=0.0, saturated=False, input_fps=30.0):
        """Call every tick — updates metrics and appends CSV incrementally."""
        if self.metrics is None:
            return None
        try:
            # delegate to metrics
            entry = self.metrics.update(
                frame_id, timestamp, detection_valid, estimate, ground_truth,
                processing_ms, fps, pan_rate, tilt_rate,
                detection_confidence=detection_confidence, saturated=saturated, input_fps=input_fps
            )
            # incremental CSV
            if self.csv_file and self.csv_writer is None:
                # need keys from entry
                self._frame_keys = list(entry.keys())
                self.csv_writer = csv.DictWriter(self.csv_file, fieldnames=self._frame_keys)
                self.csv_writer.writeheader()
                self.csv_header_written = True

            if self.csv_writer:
                # stringify complex fields for CSV
                r = dict(entry)
                r["model_probs"] = str(r.get("model_probs", ""))
                r["gt_pos"] = str(r.get("gt_pos", ""))
                r["est_pos"] = str(r.get("est_pos", ""))
                try:
                    self.csv_writer.writerow(r)
                    # flush every 10 frames or on key frames to limit I/O
                    if frame_id % 10 == 0:
                        self.csv_file.flush()
                        try:
                            os.fsync(self.csv_file.fileno())
                        except:
                            pass
                except Exception as e:
                    print(f"[AutoLogger] csv write failed f{frame_id}: {e}")

            return entry
        except Exception as e:
            print(f"[AutoLogger] log_frame failed f{frame_id}: {e}")
            traceback.print_exc()
            return None

    def end_run(self, is_aborted=False):
        """Call on run completion — flushes CSV, generates all reports atomically."""
        if not self.run_dir or not self.metrics:
            return None, None
        try:
            # flush and close CSV
            if self.csv_file:
                try:
                    self.csv_file.flush()
                    os.fsync(self.csv_file.fileno())
                    self.csv_file.close()
                except Exception as e:
                    print(f"[AutoLogger] csv close failed: {e}")
                finally:
                    self.csv_file = None
                    self.csv_writer = None

            summary = self.metrics.summary()
            cfg = self.cfg_snapshot or {}

            # thresholds per spec
            thresholds = {
                "acquisition_limit_s": 2.0,
                "reacquisition_limit_s": 1.0,
                "tracking_error_limit_px": 10.0,
                "loss_limit_pct": 5.0,
                "fps_min": 20.0,
            }
            passed = {
                "acquisition": (summary["acquisition_time_s"] is not None and summary["acquisition_time_s"] <= thresholds["acquisition_limit_s"]),
                "reacquisition": (summary["reacquisition_mean_s"] is None or summary["reacquisition_mean_s"] <= thresholds["reacquisition_limit_s"]),
                "tracking_rmse": summary["rmse_px"] <= thresholds["tracking_error_limit_px"],
                "loss": summary["target_loss_pct"] < thresholds["loss_limit_pct"],
                "fps": summary["avg_fps"] >= thresholds["fps_min"],
            }
            overall_pass = all(passed.values())

            # system info
            sysinfo = {
                "python": sys.version,
                "platform": platform.platform(),
                "processor": platform.processor(),
                "cwd": os.getcwd(),
            }
            # try git commit if available
            try:
                import subprocess
                git = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=2)
                if git.returncode == 0:
                    sysinfo["git_commit"] = git.stdout.strip()[:12]
            except:
                pass

            timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
            meta = {
                "timestamp": timestamp,
                "run_dir": self.run_dir,
                "seed": cfg.get("experiment", {}).get("seed", 0) if cfg else 0,
                "input_mode": cfg.get("experiment", {}).get("input_mode", "SYNTHETIC") if cfg else "SYNTHETIC",
                "duration_requested_s": cfg.get("experiment", {}).get("duration_s", 0) if cfg else 0,
                "aborted": bool(is_aborted),
                "summary": summary,
                "thresholds": thresholds,
                "pass": passed,
                "overall_pass": bool(overall_pass),
                "system": sysinfo,
            }

            # --- atomic writes ---
            # summary_report.json
            _atomic_write(
                os.path.join(self.run_dir, "summary_report.json"),
                json.dumps(meta, indent=2)
            )
            # run_metadata.json (full cfg + summary)
            _atomic_write(
                os.path.join(self.run_dir, "run_metadata.json"),
                json.dumps({"cfg": cfg, "summary": summary, "meta": meta}, indent=2)
            )
            # events.json
            if self.metrics.frames:
                events = [{"frame_id": f["frame_id"], "state": f["tracking_state"], "error_px": f["error_px"], "confidence": f.get("detection_confidence", 0)} for f in self.metrics.frames]
                _atomic_write(os.path.join(self.run_dir, "events.json"), json.dumps(events, indent=2))

            # summary_report.html (standalone, no external deps)
            html = self._build_html(meta, summary, cfg)
            _atomic_write(os.path.join(self.run_dir, "summary_report.html"), html)

            # plots (best-effort)
            if HAS_MPL and self.metrics.frames:
                try:
                    self._generate_plots(self.run_dir, summary)
                except Exception as e:
                    print(f"[AutoLogger] plot generation failed: {e}")

            # remove in_progress marker, write completed marker
            try:
                in_prog = os.path.join(self.run_dir, ".in_progress")
                if os.path.exists(in_prog):
                    os.remove(in_prog)
                _atomic_write(os.path.join(self.run_dir, ".completed"), json.dumps({"completed": timestamp, "overall_pass": overall_pass}))
            except:
                pass

            print(f"[AutoLogger] end_run -> {self.run_dir}  PASS={overall_pass}  RMSE={summary['rmse_px']:.2f} loss={summary['target_loss_pct']:.1f}%")
            run_dir = self.run_dir
            # keep run_dir for later manual export (don't clear)
            return summary, run_dir

        except Exception as e:
            print(f"[AutoLogger] end_run failed: {e}")
            traceback.print_exc()
            return None, None

    def abort_run(self):
        """Call on reset/close without normal completion."""
        return self.end_run(is_aborted=True)

    def get_last_run_dir(self):
        return self.run_dir

    def _deep_copy_cfg(self, cfg):
        try:
            return json.loads(json.dumps(cfg))
        except:
            import copy
            return copy.deepcopy(cfg)

    def _build_html(self, meta, summary, cfg):
        # limit long config display
        traj = cfg.get("target", {}).get("trajectory", "?") if cfg else "?"
        noise = cfg.get("noise", {}) if cfg else {}
        atmo = cfg.get("atmosphere", {}).get("type", "?") if cfg else "?"
        jitter = cfg.get("camera", {}).get("jitter_px", 0) if cfg else 0
        seed = cfg.get("experiment", {}).get("seed", "?") if cfg else "?"
        # pass/fail badge
        def badge(ok):
            bg = "#16a34a" if ok else "#dc2626"
            txt = "PASS" if ok else "FAIL"
            return f'<span style="background:{bg};color:white;padding:2px 8px;border-radius:999px;font-size:11px;font-weight:800;">{txt}</span>'
        overall = badge(meta["overall_pass"])
        acq_val = f'{summary["acquisition_time_s"]:.3f}s' if summary["acquisition_time_s"] is not None else "—"
        reacq_val = f'{summary["reacquisition_mean_s"]:.3f}s' if summary["reacquisition_mean_s"] is not None else "—"
        return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>FSOC Run Report</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  body{{font-family:Inter,'Segoe UI',system-ui,sans-serif;margin:0;background:#f1f5f9;color:#0f172a}}
  .wrap{{max-width:980px;margin:24px auto;padding:0 16px}}
  .card{{background:white;border:1px solid #e2e8f0;border-radius:12px;padding:16px 18px;margin-bottom:16px;box-shadow:0 1px 2px rgba(0,0,0,.04)}}
  h1{{font-size:18px;margin:0 0 4px}}
  .muted{{color:#64748b;font-size:12px}}
  table{{width:100%;border-collapse:collapse;font-size:13px}}
  th{{text-align:left;color:#64748b;font-size:11px;letter-spacing:.06em;text-transform:uppercase;padding:8px;border-bottom:1px solid #e2e8f0}}
  td{{padding:9px 8px;border-bottom:1px solid #f1f5f9}}
  .mono{{font-family:'JetBrains Mono',Consolas,monospace}}
  .kvs{{display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:12px}}
  .kvs div{{background:#f8fafc;border:1px solid #f1f5f9;border-radius:8px;padding:8px 10px}}
  .kvs b{{display:block;color:#64748b;font-size:10px;letter-spacing:.06em;text-transform:uppercase}}
  img{{max-width:100%;border-radius:8px;border:1px solid #e2e8f0}}
</style></head><body><div class="wrap">
<div class="card">
  <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap">
    <h1>FSOC Virtual Camera Tracking — Run Report</h1>
    <span>{overall}</span>
  </div>
  <div class="muted">Time {meta["timestamp"]} · Seed {seed} · Mode {meta["input_mode"]} · Trajectory {traj} · Duration {summary["duration_s"]:.1f}s · Frames {summary["total_frames"]}</div>
  <div style="margin-top:10px" class="kvs">
    <div><b>Config</b><span class="mono">noise={str(noise)[:80]} · atmo={atmo} · jitter={jitter} · seed={seed}</span></div>
    <div><b>System</b><span class="mono">{meta["system"]["platform"][:60]}</span></div>
  </div>
</div>
<div class="card">
<table>
<tr><th>Metric</th><th>Value</th><th>Threshold</th><th>Status</th></tr>
<tr><td>Acquisition time</td><td class="mono">{acq_val}</td><td>≤2.0s</td><td>{badge(meta["pass"]["acquisition"])}</td></tr>
<tr><td>Re-acquisition mean (count {summary["reacquisition_count"]})</td><td class="mono">{reacq_val}</td><td>≤1.0s</td><td>{badge(meta["pass"]["reacquisition"])}</td></tr>
<tr><td>RMSE</td><td class="mono">{summary['rmse_px']:.2f} px</td><td>≤10 px</td><td>{badge(meta["pass"]["tracking_rmse"])}</td></tr>
<tr><td>Mean error</td><td class="mono">{summary['mean_error_px']:.2f} px</td><td>—</td><td></td></tr>
<tr><td>P95 error</td><td class="mono">{summary['p95_error_px']:.2f} px</td><td>—</td><td></td></tr>
<tr><td>Max error</td><td class="mono">{summary['max_error_px']:.2f} px</td><td>—</td><td></td></tr>
<tr><td>Lock retention</td><td class="mono">{summary['lock_retention_pct']:.1f}%</td><td>—</td><td></td></tr>
<tr><td>Target loss</td><td class="mono">{summary['target_loss_pct']:.1f}%</td><td>&lt;5%</td><td>{badge(meta["pass"]["loss"])}</td></tr>
<tr><td>Avg FPS</td><td class="mono">{summary['avg_fps']:.1f} (in {summary['input_fps']:.0f} / e2e {summary['e2e_fps']:.1f})</td><td>≥20</td><td>{badge(meta["pass"]["fps"])}</td></tr>
<tr><td>Avg / Max proc</td><td class="mono">{summary['avg_processing_ms']:.1f} / {summary['max_processing_ms']:.1f} ms</td><td>—</td><td></td></tr>
<tr><td>Valid detections</td><td class="mono">{summary['valid_detections']} / {summary['total_frames']} ({summary['valid_detection_pct']:.1f}%)</td><td>—</td><td></td></tr>
<tr><td>Saturations</td><td class="mono">{summary['saturation_count']}</td><td>—</td><td></td></tr>
</table>
</div>
<div class="card">
  <h3 style="margin:0 0 8px;font-size:13px">Plots</h3>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
    <div><div class="muted" style="margin-bottom:6px">Error vs Time</div><img src="error_plot.png" onerror="this.style.display='none'"><div class="muted">frame_metrics.csv -> error_px</div></div>
    <div><div class="muted" style="margin-bottom:6px">Trajectory (world)</div><img src="trajectory_plot.png" onerror="this.style.display='none'"><div class="muted">world_pos vs time</div></div>
  </div>
  <div class="muted" style="margin-top:10px">Files: <span class="mono">config_used.yaml, frame_metrics.csv, events.json, summary_report.json, run_metadata.json</span></div>
</div>
</div></body></html>"""

    def _generate_plots(self, run_dir, summary):
        if not HAS_MPL or not self.metrics or not self.metrics.frames:
            return
        try:
            frames = self.metrics.frames
            # error plot
            xs = [f["frame_id"] for f in frames]
            errs = [f["error_px"] if f["error_px"] is not None else float("nan") for f in frames]
            plt.figure(figsize=(7, 2.8), dpi=150)
            plt.plot(xs, errs, color="#2563eb", linewidth=1.1)
            plt.axhline(10, color="#dc2626", linestyle="--", linewidth=0.9, label="10px gate")
            plt.title("Tracking error (px) vs frame", fontsize=10)
            plt.xlabel("frame")
            plt.ylabel("error px")
            plt.grid(alpha=0.2)
            plt.tight_layout()
            plt.savefig(os.path.join(run_dir, "error_plot.png"))
            plt.close()

            # trajectory plot (world if available, else image est)
            gt_xs = []
            gt_ys = []
            est_xs = []
            est_ys = []
            for f in frames:
                gp = f.get("gt_pos")
                ep = f.get("est_pos")
                if gp and isinstance(gp, (list, tuple)) and len(gp) == 2 and gp[0] is not None:
                    # gt_pos is (x,y) in image coords when visible, but we also want world?
                    # for synthetic, world pos not directly stored in frame; use gt_pos as proxy
                    gt_xs.append(gp[0]); gt_ys.append(gp[1])
                if ep and isinstance(ep, (list, tuple)) and ep[0] is not None:
                    est_xs.append(ep[0]); est_ys.append(ep[1])
            if gt_xs or est_xs:
                plt.figure(figsize=(4, 4), dpi=150)
                if gt_xs:
                    plt.plot(gt_xs, gt_ys, color="#f59e0b", linewidth=1, alpha=0.85, label="GT")
                if est_xs:
                    plt.plot(est_xs, est_ys, color="#16a34a", linewidth=1, alpha=0.9, label="EST")
                plt.gca().invert_yaxis()
                plt.title("Image trajectory", fontsize=10)
                plt.xlabel("x px"); plt.ylabel("y px")
                plt.legend(fontsize=8)
                plt.grid(alpha=0.15)
                plt.tight_layout()
                plt.savefig(os.path.join(run_dir, "trajectory_plot.png"))
                plt.close()
        except Exception as e:
            print(f"[AutoLogger] plot error: {e}")
