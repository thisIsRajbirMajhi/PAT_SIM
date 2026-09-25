"""
AI metrics — detection + identification + end-to-end (Plan §14).

Detection : precision / recall / FPR / miss rate / latency
Identity  : primary precision+recall / decoy rejection / false-lock
            / time-to-identify / identity-switch count / UNKNOWN rate
End-to-end: acquisition ≤2s / re-acquisition ≤1s / RMSE ≤10px / loss <5% / FPS ≥20

The false-primary lock rate is the most important safety metric —
high accuracy with high false-lock is not acceptable.
"""
from __future__ import annotations

from typing import Dict, List, Tuple
import numpy as np


def precision_recall_f1(y_true: np.ndarray, y_pred: np.ndarray, positive: int = 1) -> Dict[str, float]:
    tp = int(((y_pred == positive) & (y_true == positive)).sum())
    fp = int(((y_pred == positive) & (y_true != positive)).sum())
    fn = int(((y_pred != positive) & (y_true == positive)).sum())
    prec = tp / max(tp + fp, 1)
    rec = tp / max(tp + fn, 1)
    f1 = 2 * prec * rec / max(prec + rec, 1e-9)
    return {"precision": prec, "recall": rec, "f1": f1, "tp": tp, "fp": fp, "fn": fn}


def decoy_rejection_rate(true_labels: np.ndarray, pred_labels: np.ndarray, decoy_id: int = 1) -> float:
    """Fraction of true decoys that were predicted as decoy (higher is better)."""
    mask = true_labels == decoy_id
    if mask.sum() == 0:
        return 0.0
    return float((pred_labels[mask] == decoy_id).mean())


def false_lock_rate(true_is_primary: np.ndarray, pred_is_primary: np.ndarray) -> float:
    """
    Fraction of predicted PRIMARY that were not actually PRIMARY.
    Lower is better; this is the key safety metric.
    """
    pred_primary = pred_is_primary == 1
    if pred_primary.sum() == 0:
        return 0.0
    return float((true_is_primary[pred_primary] == 0).mean())


def identity_switch_count(track_pred_sequence: List[int]) -> int:
    """Count label changes along a track (stable identity → 0 switches)."""
    if len(track_pred_sequence) < 2:
        return 0
    return sum(1 for a, b in zip(track_pred_sequence, track_pred_sequence[1:]) if a != b)


def time_to_identify(first_primary_frame: int | None, fps: float = 30.0) -> float | None:
    if first_primary_frame is None:
        return None
    return first_primary_frame / fps


def summarize_end_to_end(metrics_collector) -> Dict:
    """Adapter over evaluation.metrics.MetricsCollector.summary() for report uniformity."""
    s = metrics_collector.summary() if hasattr(metrics_collector, "summary") else {}
    # acquisition / re-acq thresholds per spec
    s["acq_pass"] = (s.get("acquisition_time_s") is not None and s["acquisition_time_s"] <= 2.0) if s else None
    s["reacq_pass"] = (s.get("reacquisition_mean_s") is not None and s["reacquisition_mean_s"] <= 1.0) if s and s.get("reacquisition_mean_s") else None
    s["rmse_pass"] = s.get("rmse_px", 999) <= 10.0 if s else None
    s["loss_pass"] = s.get("target_loss_pct", 100) < 5.0 if s else None
    return s
