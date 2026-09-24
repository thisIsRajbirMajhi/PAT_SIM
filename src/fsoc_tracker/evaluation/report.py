import os, json, csv, time, datetime
import yaml

def export_run(output_dir, cfg, metrics_collector):
    os.makedirs(output_dir, exist_ok=True)
    summary = metrics_collector.summary()
    # config
    with open(os.path.join(output_dir, "config_used.yaml"), "w") as f:
        yaml.safe_dump(cfg, f, sort_keys=False)
    # metadata
    meta = {
        "timestamp": datetime.datetime.now().isoformat(),
        "seed": cfg["experiment"]["seed"],
        "input_mode": cfg["experiment"]["input_mode"],
        "summary": summary,
        "thresholds": {
            "acquisition_limit_s": 2.0,
            "reacquisition_limit_s": 1.0,
            "tracking_error_limit_px": 10.0,
            "loss_limit_pct": 5.0,
            "fps_min": 20.0,
        },
        "pass": {
            "acquisition": (summary["acquisition_time_s"] is not None and summary["acquisition_time_s"] <= 2.0),
            "reacquisition": (summary["reacquisition_mean_s"] is None or summary["reacquisition_mean_s"] <= 1.0),
            "tracking_rmse": summary["rmse_px"] <= 10.0,
            "loss": summary["target_loss_pct"] < 5.0,
            "fps": summary["avg_fps"] >= 20.0,
        }
    }
    with open(os.path.join(output_dir, "summary_report.json"), "w") as f:
        json.dump(meta, f, indent=2)
    with open(os.path.join(output_dir, "run_metadata.json"), "w") as f:
        json.dump({"cfg": cfg, "summary": summary, "time": meta["timestamp"]}, f, indent=2)
    # frame metrics csv
    if metrics_collector.frames:
        keys = list(metrics_collector.frames[0].keys())
        # flatten some
        with open(os.path.join(output_dir, "frame_metrics.csv"), "w", newline="") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=keys)
            writer.writeheader()
            for row in metrics_collector.frames:
                # stringify complex fields
                r = dict(row)
                r["model_probs"] = str(r["model_probs"])
                r["gt_pos"] = str(r["gt_pos"])
                r["est_pos"] = str(r["est_pos"])
                writer.writerow(r)
        # events json
        events = [{"frame_id": f["frame_id"], "state": f["tracking_state"], "error": f["error_px"]} for f in metrics_collector.frames]
        with open(os.path.join(output_dir, "events.json"), "w") as f:
            json.dump(events, f, indent=2)
    # html summary
    html = f"""<html><head><title>FSOC Run Report</title></head><body style="font-family:Inter,Arial,sans-serif;padding:24px">
<h2>FSOC Virtual Camera Tracking — Run Report</h2>
<p><b>Time:</b> {meta['timestamp']} &nbsp; <b>Seed:</b> {cfg['experiment']['seed']} &nbsp; <b>Mode:</b> {cfg['experiment']['input_mode']}</p>
<table border=1 cellpadding=8 cellspacing=0>
<tr><th>Metric</th><th>Value</th><th>Threshold</th><th>Status</th></tr>
<tr><td>Acquisition time</td><td>{summary['acquisition_time_s']}</td><td>≤2.0s</td><td>{'PASS' if meta['pass']['acquisition'] else 'FAIL'}</td></tr>
<tr><td>Re-acquisition mean</td><td>{summary['reacquisition_mean_s']}</td><td>≤1.0s</td><td>{'PASS' if meta['pass']['reacquisition'] else 'FAIL'}</td></tr>
<tr><td>RMSE</td><td>{summary['rmse_px']:.2f} px</td><td>≤10 px</td><td>{'PASS' if meta['pass']['tracking_rmse'] else 'FAIL'}</td></tr>
<tr><td>Mean error</td><td>{summary['mean_error_px']:.2f} px</td><td>—</td><td></td></tr>
<tr><td>Max error</td><td>{summary['max_error_px']:.2f} px</td><td>—</td><td></td></tr>
<tr><td>P95 error</td><td>{summary['p95_error_px']:.2f} px</td><td>—</td><td></td></tr>
<tr><td>Lock retention</td><td>{summary['lock_retention_pct']:.1f}%</td><td>—</td><td></td></tr>
<tr><td>Target loss</td><td>{summary['target_loss_pct']:.1f}%</td><td>&lt;5%</td><td>{'PASS' if meta['pass']['loss'] else 'FAIL'}</td></tr>
<tr><td>Avg FPS</td><td>{summary['avg_fps']:.1f}</td><td>≥20</td><td>{'PASS' if meta['pass']['fps'] else 'FAIL'}</td></tr>
<tr><td>Avg proc ms</td><td>{summary['avg_processing_ms']:.1f} ms</td><td>—</td><td></td></tr>
</table>
<p>Config: trajectory={cfg['target']['trajectory']}, noise={cfg['noise']}, atmosphere={cfg['atmosphere']['type']}, jitter={cfg['camera']['jitter_px']}</p>
</body></html>"""
    with open(os.path.join(output_dir, "summary_report.html"), "w", encoding="utf-8") as f:
        f.write(html)
    return summary, output_dir
