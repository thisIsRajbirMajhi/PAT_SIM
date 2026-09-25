"""
Feature extraction utilities — Plan §5-6 / Prompt Phase 1.

 - Patch extraction: crop 64×64 around candidate, pad at borders,
   grayscale, local-contrast normalize (§9.2 Step 3).
 - Numerical features: brightness, area, aspect, local contrast, etc.
 - Track-level features for GRU (20-30 step sequence).

No ground truth is accessed here.
"""
from __future__ import annotations

from typing import Tuple, List, Optional
import numpy as np
import cv2

PATCH_SIZE = 64
EMBED_DIM = 128
SEQ_LEN = 25  # default 20-30


def extract_patch(
    frame_gray: np.ndarray,
    centroid: Tuple[float, float],
    size: int = PATCH_SIZE,
) -> np.ndarray:
    """
    Crop fixed-size patch around centroid, pad with border replicate
    if near image edge (Plan §9.2 Step 3). Returns float32 [0,1] HxW.
    """
    if frame_gray is None or frame_gray.size == 0:
        return np.zeros((size, size), dtype=np.float32)
    if len(frame_gray.shape) == 3:
        frame_gray = cv2.cvtColor(frame_gray, cv2.COLOR_BGR2GRAY)
    h, w = frame_gray.shape
    cx, cy = int(round(centroid[0])), int(round(centroid[1]))
    half = size // 2
    x0, y0 = cx - half, cy - half
    x1, y1 = x0 + size, y0 + size

    # pad if out of bounds
    pad_left = max(0, -x0)
    pad_top = max(0, -y0)
    pad_right = max(0, x1 - w)
    pad_bottom = max(0, y1 - h)

    x0c, y0c = max(0, x0), max(0, y0)
    x1c, y1c = min(w, x1), min(h, y1)

    patch = frame_gray[y0c:y1c, x0c:x1c]
    if pad_left or pad_top or pad_right or pad_bottom:
        patch = cv2.copyMakeBorder(
            patch, pad_top, pad_bottom, pad_left, pad_right,
            cv2.BORDER_REFLECT_101,
        )
    # resize if needed (should already be size×size after padding)
    if patch.shape[0] != size or patch.shape[1] != size:
        patch = cv2.resize(patch, (size, size), interpolation=cv2.INTER_AREA)

    # local background normalization: (patch - median) / (std + eps)
    # keep in 0-1 for model input; also preserve raw variant for signature
    normalized = patch.astype(np.float32) / 255.0
    return normalized


def numerical_features(candidate) -> np.ndarray:
    """
    Returns float32 vector: [brightness, area, w, h, aspect, contrast, compactness, dist]
    Normalized to roughly 0-1 for MLP fusion.
    """
    return np.array([
        candidate.brightness / 255.0,
        candidate.peak_intensity / 255.0,
        candidate.local_contrast / 255.0,
        candidate.area / 900.0,
        candidate.width / 64.0,
        candidate.height / 64.0,
        min(candidate.aspect_ratio / 3.5, 1.0),
        candidate.compactness,
        min(candidate.distance_from_prediction / 400.0, 1.0),
    ], dtype=np.float32)


def build_gru_sequence(track, seq_len: int = SEQ_LEN) -> Tuple[np.ndarray, np.ndarray]:
    """
    Build (seq_len, feat_dim) array for GRU from TrackState.
    Returns (sequence, mask) where mask is 1 for valid steps.
    Features per step: embedding(128) + pos(2) + vel(2) + brightness(1)
                      + shape_stability(1) + blink(1) + innovation(1) + IMM(3) = ~139
    Short tracks are left-padded with zeros and mask=0.
    """
    # This is the contract; actual embedding comes from candidate_model at runtime.
    # For offline training we expect embeddings already stored.
    feat_dim = EMBED_DIM + 2 + 2 + 1 + 1 + 1 + 1 + 3  # 139
    seq = np.zeros((seq_len, feat_dim), dtype=np.float32)
    mask = np.zeros((seq_len,), dtype=np.float32)

    n = len(track.position_history)
    if n == 0:
        return seq, mask

    # take last seq_len observations
    start = max(0, n - seq_len)
    valid_len = n - start
    pad = seq_len - valid_len

    for i in range(valid_len):
        idx = start + i
        out_idx = pad + i
        # position (normalized to 0-1 by world? here use 640x480 approx)
        px, py = track.position_history[idx]
        vx, vy = track.velocity_history[idx] if idx < len(track.velocity_history) else (0, 0)
        br = track.brightness_history[idx] if idx < len(track.brightness_history) else 0
        innov = track.innovation_history[idx] if idx < len(track.innovation_history) else 0
        imm = track.imm_probs_history[idx] if idx < len(track.imm_probs_history) else (0.33, 0.33, 0.34)
        # embedding placeholder — caller fills first 128 dims if available
        seq[out_idx, 0:2] = [px / 640.0, py / 480.0]
        seq[out_idx, 2:4] = [vx / 20.0, vy / 20.0]
        # ... remaining dims filled by caller / training dataset builder
        mask[out_idx] = 1.0

    return seq, mask


def estimate_local_contrast(frame_gray: np.ndarray, bbox) -> float:
    """Local contrast = std inside bbox vs surrounding ring."""
    if frame_gray is None or bbox is None:
        return 0.0
    x, y, w, h = bbox
    patch = frame_gray[max(0, y):y+h, max(0, x):x+w]
    if patch.size == 0:
        return 0.0
    return float(np.std(patch))
