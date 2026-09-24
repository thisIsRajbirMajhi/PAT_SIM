import numpy as np
import time

class MetricsCollector:
    def __init__(self):
        self.reset()

    def reset(self):
        self.frames = []  # list of dict
        self.t_start = time.perf_counter()
        self.acquisition_time = None
        self.reacq_times = []
        self._acquired = False
        self._lost_since = None
        self._last_state = None
        self.proc_times = []
        self.errors = []
        self.t_acq_start = None
        self.saturation_count = 0
        self.loss_count = 0
        self.acq_count = 0
        self._was_locked = False
        self.confidences = []
        self.input_fps = 30.0
        self.dropped_frames = 0

    def start_run(self):
        self.reset()
        self.t_start = time.perf_counter()
        self.t_acq_start = time.perf_counter()
        # keep input_fps if already set
        self.input_fps = getattr(self, 'input_fps', 30.0)

    def update(self, frame_id, timestamp, detection_valid, estimate, ground_truth, processing_ms, fps, pan_rate, tilt_rate, detection_confidence=0.0, saturated=False, input_fps=30.0):
        # error
        err = None
        err_angle = None
        lock_valid = False
        if detection_valid and ground_truth and ground_truth.image_pos and estimate.pos_px:
            # detection error vs truth? Use estimate pixel vs truth for tracking error
            gt = ground_truth.image_pos
            est = estimate.pos_px
            # But per spec tracking error is |p_t - g_t| where p_t is estimated centroid (detection) - we use detection centroid if valid else IMM pred?
            # Use detection centroid when valid for error, else use IMM predicted
            # For metrics, use detection centroid pixel if valid, else IMM estimate
            # Let's compute using detection vs truth when available, else estimate vs truth
            # We'll store error based on estimate (fused) for control evaluation, but also log detection error.
            # Here we provide estimate error for metrics
            err = float(np.hypot(est[0]-gt[0], est[1]-gt[1]))
            err_angle = float(np.hypot(estimate.pos_angle[0], estimate.pos_angle[1]))
            self.errors.append(err)
            lock_valid = estimate.tracking_state.value in ("LOCKED","ACQUIRING") and detection_valid
        elif ground_truth and ground_truth.image_pos is None:
            # target outside FOV -> no error, count as loss
            pass

        # acquisition timing
        if not self._acquired and estimate.tracking_state.value == "LOCKED":
            self.acquisition_time = time.perf_counter() - self.t_acq_start
            self._acquired = True
            self._lost_since = None
        # reacquisition
        if self._last_state and self._last_state.value in ("LOCKED","ACQUIRING") and estimate.tracking_state.value in ("TEMP_LOST","REACQUIRING","SEARCHING"):
            if self._lost_since is None:
                self._lost_since = time.perf_counter()
        if self._lost_since is not None and estimate.tracking_state.value == "LOCKED":
            reacq = time.perf_counter() - self._lost_since
            self.reacq_times.append(reacq)
            self._lost_since = None

        # saturation and confidence tracking
        self.input_fps = float(input_fps)
        if saturated:
            self.saturation_count += 1
        if detection_confidence is not None:
            self.confidences.append(float(detection_confidence))
        # event counting: acquisition = first LOCKED and each re-LOCK after loss
        cur_state = estimate.tracking_state.value
        prev_state = self._last_state.value if self._last_state else None
        if cur_state == "LOCKED" and prev_state != "LOCKED":
            self.acq_count += 1
        if prev_state == "LOCKED" and cur_state in ("TEMP_LOST","REACQUIRING","SEARCHING","FAILED"):
            self.loss_count += 1
        # dropped frames: count when processing exceeds interval (real-time drop)
        # For synthetic: interval = 1000/input_fps ms; if proc_ms > interval, we would have dropped
        interval_ms = 1000.0 / max(input_fps, 1)
        if processing_ms > interval_ms * 1.05:  # 5% tolerance
            # Estimate number of frames that would have been dropped in this tick
            # e.g., proc 45ms at 30fps (33ms) => 1 frame dropped
            self.dropped_frames += max(1, int(processing_ms / interval_ms))
        # also keep expected vs processed estimate for summary fallback (updated in summary)

        self._last_state = estimate.tracking_state
        self.proc_times.append(processing_ms)
        entry = {
            "frame_id": frame_id,
            "timestamp": timestamp,
            "detection_valid": bool(detection_valid),
            "detection_confidence": float(detection_confidence or 0.0),
            "tracking_state": cur_state,
            "error_px": err,
            "error_angle_deg": err_angle,
            "processing_ms": processing_ms,
            "fps": fps,
            "pan_rate": pan_rate,
            "tilt_rate": tilt_rate,
            "saturated": bool(saturated),
            "model_probs": list(estimate.model_probs),
            "innovation": estimate.innovation,
            "gt_visible": bool(ground_truth.visible) if ground_truth else False,
            "gt_pos": ground_truth.image_pos if ground_truth else None,
            "est_pos": estimate.pos_px,
        }
        self.frames.append(entry)
        return entry

    def summary(self):
        total = len(self.frames)
        valid_errors = [e for e in self.errors if e is not None]
        locked = sum(1 for f in self.frames if f["tracking_state"]=="LOCKED")
        valid_det = sum(1 for f in self.frames if f["detection_valid"])
        loss_pct = 100*(1 - locked/max(total,1))
        mean_err = float(np.mean(valid_errors)) if valid_errors else 0.0
        rmse = float(np.sqrt(np.mean(np.square(valid_errors)))) if valid_errors else 0.0
        max_err = float(np.max(valid_errors)) if valid_errors else 0.0
        p95 = float(np.percentile(valid_errors,95)) if valid_errors else 0.0
        avg_proc = float(np.mean(self.proc_times)) if self.proc_times else 0.0
        max_proc = float(np.max(self.proc_times)) if self.proc_times else 0.0
        fps_vals = [f["fps"] for f in self.frames if f["fps"]>0]
        avg_fps = float(np.mean(fps_vals)) if fps_vals else 0.0
        reacq_mean = float(np.mean(self.reacq_times)) if self.reacq_times else None
        reacq_max = float(np.max(self.reacq_times)) if self.reacq_times else None
        # dropped frames: use incremental counter (real-time drop) + expected vs total fallback
        duration = self.frames[-1]["timestamp"]-self.frames[0]["timestamp"] if total>1 else 0
        expected = int(round(duration * self.input_fps)) if self.input_fps>0 else total
        expected_dropped = max(0, expected - total) if expected>total else 0
        dropped = max(int(self.dropped_frames), expected_dropped)
        # end-to-end FPS = total / duration
        e2e_fps = (total / duration) if duration>0 else avg_fps
        avg_conf = float(np.mean(self.confidences)) if self.confidences else 0.0
        reacq_last = self.reacq_times[-1] if self.reacq_times else None
        return {
            "total_frames": total,
            "duration_s": duration,
            "input_fps": float(self.input_fps),
            "avg_fps": avg_fps,
            "e2e_fps": float(e2e_fps),
            "dropped_frames": int(dropped),
            "acquisition_time_s": self.acquisition_time,
            "reacquisition_times_s": self.reacq_times,
            "reacquisition_last_s": reacq_last,
            "reacquisition_mean_s": reacq_mean,
            "reacquisition_max_s": reacq_max,
            "reacquisition_count": len(self.reacq_times),
            "acquisition_count": int(self.acq_count),
            "loss_count": int(self.loss_count),
            "mean_error_px": mean_err,
            "rmse_px": rmse,
            "max_error_px": max_err,
            "p95_error_px": p95,
            "lock_retention_pct": 100*locked/max(total,1),
            "target_loss_pct": loss_pct,
            "valid_detection_pct": 100*valid_det/max(total,1),
            "valid_detections": int(valid_det),
            "avg_confidence": float(avg_conf),
            "avg_processing_ms": avg_proc,
            "max_processing_ms": max_proc,
            "saturation_count": int(self.saturation_count),
            "locked_frames": locked,
        }
