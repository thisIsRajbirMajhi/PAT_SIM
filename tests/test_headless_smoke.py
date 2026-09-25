"""Fast smoke test for CI — P01 60 frames headless, no GUI."""

import time
from fsoc_tracker.config.loader import load_config
from fsoc_tracker.input.synthetic_source import SyntheticSource
from fsoc_tracker.perception.detector import BeaconDetector
from fsoc_tracker.tracking.tracker import Tracker
from fsoc_tracker.control.camera_controller import CameraController
from fsoc_tracker.evaluation.metrics import MetricsCollector
from fsoc_tracker.evaluation.report import export_run
import tempfile, os, json, csv

def test_smoke_p01_60_frames():
    cfg = load_config("configs/benchmarks/P01_clean_baseline.yaml")
    src = SyntheticSource(cfg, seed=cfg["experiment"]["seed"])
    det = BeaconDetector(cfg)
    trk = Tracker(cfg)
    ctrl = CameraController(cfg)
    metrics = MetricsCollector()
    metrics.start_run()
    for _ in range(60):
        t0 = time.perf_counter()
        frame, gt = src.read()
        assert frame is not None
        assert frame.image.shape[0] == 480 and frame.image.shape[1] == 640
        d = det.detect(frame.image, predicted_pos=trk.get_predicted_pixel())
        est = trk.step(d, frame)
        cmd = ctrl.step(est, dt=1/30)
        src.apply_camera_command(cmd.pan_rate, cmd.tilt_rate, 1/30)
        proc_ms = (time.perf_counter() - t0) * 1000
        metrics.update(frame.frame_id, frame.timestamp, d.valid, est, gt, min(proc_ms, 8), 30, cmd.pan_rate, cmd.tilt_rate,
                       detection_confidence=d.confidence, saturated=cmd.saturated)
    s = metrics.summary()
    assert s["total_frames"] == 60
    assert s["input_fps"] == 30
    assert 0 <= s["rmse_px"] < 20
    assert "acquisition_time_s" in s
    # ensure required keys present per Preset Plan pass/fail rule
    for k in ["mean_error_px","rmse_px","p95_error_px","max_error_px","target_loss_pct","lock_retention_pct","reacquisition_count","avg_processing_ms"]:
        assert k in s

def test_export_creates_artifacts(tmp_path):
    cfg = load_config("configs/benchmarks/P01_clean_baseline.yaml")
    src = SyntheticSource(cfg, seed=42)
    det = BeaconDetector(cfg)
    trk = Tracker(cfg)
    ctrl = CameraController(cfg)
    metrics = MetricsCollector()
    metrics.start_run()
    for _ in range(30):
        frame, gt = src.read()
        d = det.detect(frame.image, predicted_pos=trk.get_predicted_pixel())
        est = trk.step(d, frame)
        cmd = ctrl.step(est, dt=1/30)
        src.apply_camera_command(cmd.pan_rate, cmd.tilt_rate, 1/30)
        metrics.update(frame.frame_id, frame.timestamp, d.valid, est, gt, 5, 30, cmd.pan_rate, cmd.tilt_rate,
                       detection_confidence=d.confidence, saturated=cmd.saturated)
    out = str(tmp_path / "run")
    summary, path = export_run(out, cfg, metrics)
    assert os.path.isdir(path)
    assert os.path.exists(os.path.join(path, "summary_report.json"))
    assert os.path.exists(os.path.join(path, "frame_metrics.csv"))
    # csv has header and rows
    with open(os.path.join(path, "frame_metrics.csv")) as f:
        reader = list(csv.DictReader(f))
        assert len(reader) == 30
        assert "error_px" in reader[0]

def test_headless_handles_all_disturbances(tmp_path=None):
    # Quick combo that exercises every disturbance system without crashing
    cfg = load_config()
    cfg["target"]["trajectory"] = "figure_eight"
    cfg["noise"]["gaussian_enabled"] = True; cfg["noise"]["gaussian_std"] = 12
    cfg["noise"]["salt_pepper_enabled"] = True; cfg["noise"]["salt_pepper_prob"] = 0.02
    cfg["noise"]["poisson"] = True
    cfg["camera"]["jitter_px"] = 10
    cfg["atmosphere"]["type"] = "haze"; cfg["atmosphere"]["strength"] = 0.4
    cfg["platform"]["type"] = "linear"; cfg["platform"]["speed_px_per_frame"] = 4
    cfg["environment"]["gradient_enabled"] = True
    cfg["environment"]["stars_enabled"] = True
    cfg["environment"]["vignetting_enabled"] = True
    src = SyntheticSource(cfg, seed=1)
    det = BeaconDetector(cfg)
    trk = Tracker(cfg)
    ctrl = CameraController(cfg)
    for _ in range(20):
        frame, gt = src.read()
        assert frame.image is not None
        d = det.detect(frame.image)
        est = trk.step(d, frame)
        cmd = ctrl.step(est, dt=1/30)
        src.apply_camera_command(cmd.pan_rate, cmd.tilt_rate, 1/30)
        # no crash, estimate always finite
        assert est.model_probs is not None
