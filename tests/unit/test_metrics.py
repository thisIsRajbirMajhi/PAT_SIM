"""Tests for metrics formulas and performance thresholds."""
import numpy as np
from fsoc_tracker.evaluation.metrics import MetricsCollector
from fsoc_tracker.common.types import Estimate, GroundTruth, Detection
from fsoc_tracker.common.enums import TrackingState

def test_mean_rmse_max():
    mc = MetricsCollector()
    mc.start_run()
    # Simulate 3 frames with errors 3,4,5
    for err in [3,4,5]:
        est = Estimate(pos_px=(320+err,240), pos_angle=(0.1,0), model_probs=(0.6,0.2,0.2), tracking_state=TrackingState.LOCKED, innovation=1)
        gt = GroundTruth(world_pos=(1000,1000), visible=True, image_pos=(320,240))
        # Manually push error via direct append for test
        mc.errors.append(float(err))
        mc.proc_times.append(5.0)
        mc.frames.append({"tracking_state":"LOCKED","fps":30,"detection_valid":True,"error_px":err,"frame_id":0,"timestamp":0,"detection_confidence":0.9,"processing_ms":5,"pan_rate":0,"tilt_rate":0,"model_probs":[0.6,0.2,0.2],"innovation":1,"gt_visible":True,"gt_pos":(320,240),"est_pos":(320+err,240)})
    summ = mc.summary()
    # mean (3+4+5)/3=4, rmse sqrt((9+16+25)/3)= sqrt(16.66)=4.08, max 5
    assert abs(summ["mean_error_px"] - 4.0) < 1e-6
    assert abs(summ["rmse_px"] - np.sqrt((9+16+25)/3)) < 1e-6
    assert summ["max_error_px"] == 5

def test_acquisition_timing():
    mc = MetricsCollector()
    mc.start_run()
    # First 5 frames SEARCHING, then LOCKED -> acquisition should be ~time of first LOCKED
    import time
    est_search = Estimate(pos_px=(320,240), pos_angle=(0,0), model_probs=(0.3,0.3,0.4), tracking_state=TrackingState.SEARCHING, innovation=0)
    est_locked = Estimate(pos_px=(320,240), pos_angle=(0,0), model_probs=(0.6,0.2,0.2), tracking_state=TrackingState.LOCKED, innovation=0)
    gt = GroundTruth(world_pos=(1000,1000), visible=True, image_pos=(320,240))
    for i in range(3):
        mc.update(i, i/30, False, est_search, gt, 5, 30, 0, 0, detection_confidence=0.1, saturated=False)
    # Next frame locked -> acquisition
    mc.update(3, 3/30, True, est_locked, gt, 5, 30, 0, 0, detection_confidence=0.9, saturated=False)
    summ = mc.summary()
    assert summ["acquisition_time_s"] is not None
    assert summ["acquisition_count"] == 1

def test_lock_retention():
    mc = MetricsCollector()
    mc.start_run()
    est_locked = Estimate(pos_px=(320,240), pos_angle=(0,0), model_probs=(0.6,0.2,0.2), tracking_state=TrackingState.LOCKED, innovation=0)
    est_lost = Estimate(pos_px=(320,240), pos_angle=(0,0), model_probs=(0.3,0.3,0.4), tracking_state=TrackingState.TEMP_LOST, innovation=5)
    gt = GroundTruth(world_pos=(1000,1000), visible=True, image_pos=(320,240))
    for i in range(8):
        mc.update(i, i/30, True, est_locked, gt, 5, 30, 0, 0, detection_confidence=0.9, saturated=False)
    for i in range(8,10):
        mc.update(i, i/30, False, est_lost, gt, 5, 30, 0, 0, detection_confidence=0.1, saturated=False)
    summ = mc.summary()
    # 8 locked /10 total =80% lock, 20% loss
    assert abs(summ["lock_retention_pct"] - 80) < 1e-6
    assert abs(summ["target_loss_pct"] - 20) < 1e-6
