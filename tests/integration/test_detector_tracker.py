"""Integration: detector -> tracker -> controller closed loop."""
import numpy as np
from fsoc_tracker.config.loader import load_config
from fsoc_tracker.input.synthetic_source import SyntheticSource
from fsoc_tracker.perception.detector import BeaconDetector
from fsoc_tracker.tracking.tracker import Tracker
from fsoc_tracker.control.camera_controller import CameraController

def test_closed_loop_lock():
    cfg = load_config()
    cfg["target"]["trajectory"] = "circular"
    cfg["target"]["speed_px_per_frame"] = 2.5
    src = SyntheticSource(cfg, seed=42)
    det = BeaconDetector(cfg)
    trk = Tracker(cfg)
    ctrl = CameraController(cfg)
    # Run 60 frames, expect lock
    for _ in range(60):
        f, gt = src.read()
        d = det.detect(f.image, predicted_pos=trk.get_predicted_pixel())
        est = trk.step(d, f)
        cmd = ctrl.step(est, dt=1/30)
        src.apply_camera_command(cmd.pan_rate, cmd.tilt_rate, 1/30)
    assert est.tracking_state.value in ("LOCKED", "ACQUIRING")
    # Check that estimate is close to gt when visible
    if gt.image_pos and est.pos_px:
        err = np.hypot(est.pos_px[0]-gt.image_pos[0], est.pos_px[1]-gt.image_pos[1])
        assert err < 15  # within reasonable

def test_video_pipeline():
    # Test video adapter path (synthetic video via synthetic_source still, but check interface)
    from fsoc_tracker.input.video_source import VideoSource
    import cv2, tempfile, os
    # Create temp video
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        path = tmp.name
    try:
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        vw = cv2.VideoWriter(path, fourcc, 30, (640,480), isColor=False)
        for i in range(10):
            img = np.full((480,640), 20, dtype=np.uint8)
            cv2.rectangle(img, (320-5,240-5), (320+5,240+5), 255, -1)
            vw.write(img)
        vw.release()
        vs = VideoSource(path)
        cfg = load_config()
        det = BeaconDetector(cfg)
        f, gt = vs.read()
        assert f is not None
        d = det.detect(f.image)
        assert d.valid  # should detect beacon at centre
        vs.release()
    finally:
        try:
            os.remove(path)
        except:
            pass
