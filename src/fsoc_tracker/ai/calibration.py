"""
Confidence calibration — Plan §9.2 Step 8.

After training, validate on the held-out set:
 - temperature scaling (single parameter) or Platt scaling
 - reliability diagram / ECE (expected calibration error)
 - threshold tuning for primary/decoy regions

No training logic here — this is used by scripts/calibrate_thresholds.py.
The calibrated temperature and thresholds are written to
configs/model_thresholds.yaml and models/metadata/*.

Usage:
    from fsoc_tracker.ai.calibration import calibrate_temperature, find_best_thresholds
"""
from __future__ import annotations

from typing import Tuple, Dict
import numpy as np


def softmax(logits: np.ndarray) -> np.ndarray:
    e = np.exp(logits - np.max(logits, axis=-1, keepdims=True))
    return e / (e.sum(axis=-1, keepdims=True) + 1e-9)


def expected_calibration_error(probs: np.ndarray, labels: np.ndarray, n_bins: int = 15) -> float:
    """
    ECE: weighted mean |accuracy - confidence| per bin.
    probs: (N, C) softmax probabilities; labels: (N,) int class ids.
    """
    confidences = probs.max(axis=1)
    predictions = probs.argmax(axis=1)
    accuracies = (predictions == labels).astype(float)
    bins = np.linspace(0, 1, n_bins + 1)
    ece = 0.0
    for i in range(n_bins):
        mask = (confidences > bins[i]) & (confidences <= bins[i + 1])
        if mask.sum() == 0:
            continue
        acc = accuracies[mask].mean()
        conf = confidences[mask].mean()
        ece += (mask.sum() / len(labels)) * abs(acc - conf)
    return float(ece)


def calibrate_temperature(logits: np.ndarray, labels: np.ndarray) -> float:
    """
    Find temperature T that minimizes NLL on validation set.
    Simple 1-D search over T in [0.3, 4.0].
    Returns T (multiply logits by 1/T is equivalent to dividing).
    """
    best_t, best_nll = 1.0, float("inf")
    for t in np.linspace(0.3, 4.0, 38):
        scaled = logits / t
        probs = softmax(scaled)
        # NLL
        nll = -np.log(probs[np.arange(len(labels)), labels] + 1e-9).mean()
        if nll < best_nll:
            best_nll, best_t = nll, float(t)
    return best_t


def find_best_thresholds(
    primary_probs: np.ndarray,
    true_is_primary: np.ndarray,
    candidate_thresholds=None,
) -> Dict[str, float]:
    """
    Sweep primary threshold 0.50-0.95 and pick best F1 for PRIMARY.
    Returns dict with primary_threshold and metrics at that point.
    """
    if candidate_thresholds is None:
        candidate_thresholds = np.linspace(0.50, 0.95, 19)
    best_f1, best_thr = 0.0, 0.85
    best_metrics = {}
    for thr in candidate_thresholds:
        pred = primary_probs >= thr
        tp = int(((pred == 1) & (true_is_primary == 1)).sum())
        fp = int(((pred == 1) & (true_is_primary == 0)).sum())
        fn = int(((pred == 0) & (true_is_primary == 1)).sum())
        precision = tp / max(tp + fp, 1)
        recall = tp / max(tp + fn, 1)
        f1 = 2 * precision * recall / max(precision + recall, 1e-9)
        if f1 > best_f1:
            best_f1, best_thr = f1, float(thr)
            best_metrics = {"precision": precision, "recall": recall, "f1": f1, "threshold": float(thr)}
    return {"primary_threshold": best_thr, **best_metrics}


def reliability_bins(probs: np.ndarray, labels: np.ndarray, n_bins: int = 10):
    """Return per-bin (confidence, accuracy, count) for plotting."""
    confidences = probs.max(axis=1)
    predictions = probs.argmax(axis=1)
    accuracies = (predictions == labels).astype(float)
    bins = np.linspace(0, 1, n_bins + 1)
    out = []
    for i in range(n_bins):
        mask = (confidences > bins[i]) & (confidences <= bins[i + 1])
        if mask.sum() == 0:
            out.append({"bin": i, "confidence": float((bins[i] + bins[i+1]) / 2), "accuracy": 0.0, "count": 0})
        else:
            out.append({"bin": i, "confidence": float(confidences[mask].mean()), "accuracy": float(accuracies[mask].mean()), "count": int(mask.sum())})
    return out
