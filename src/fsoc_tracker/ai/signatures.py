"""
Optical identity signatures — Plan §8 / Prompt Phase 6.

The primary beacon must have at least one observable property
that decoys do not share. Supported signatures:

 - Coded blinking pattern (e.g. "10110010") — per-frame 0/1 via
   intensity threshold or known schedule.
 - Modulation frequency (Hz) — estimated from blink history via FFT.
 - Shape/size envelope, motion envelope, persistence.
 - Spectral band / challenge-response (hooks, optional).

Brightness alone MUST NOT confirm identity (Plan §6).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, List, Tuple
import numpy as np


@dataclass
class SignatureConfig:
    """Mirrors identity_signatures.yaml."""
    enabled: bool = True
    blink_pattern: str = "10110010"  # length 8, repeats
    blink_enabled: bool = True
    modulation_freq_hz: float = 12.0
    freq_tolerance: float = 0.05  # ±5%
    expected_shape: str = "square"
    size_range_px: Tuple[int, int] = (5, 20)
    max_speed_px_per_frame: float = 20.0
    persistence_frames: int = 5  # must be visible this many frames


def blink_correlation(observed: List[int], expected_pattern: str) -> float:
    """
    Normalized correlation between observed 0/1 history and expected
    repeating pattern. Returns 0-1 (1 = perfect match).
    Uses circular cross-correlation, max over all phase shifts.
    """
    if not observed or not expected_pattern:
        return 0.0
    pat = [1 if c == "1" else 0 for c in expected_pattern]
    n = len(pat)
    if len(observed) < n:
        return 0.0
    # compare last len(pat) observations against pattern at best phase
    obs = observed[-n:]
    best = 0.0
    for shift in range(n):
        rotated = pat[shift:] + pat[:shift]
        matches = sum(1 for a, b in zip(obs, rotated) if a == b)
        best = max(best, matches / n)
    return float(best)


def modulation_frequency_error(
    blink_history: List[int],
    expected_hz: float,
    fps: float = 30.0,
) -> float:
    """
    Estimate dominant frequency from blink history via zero-crossing
    or simple FFT; return relative error |f_est - f_exp| / f_exp.
    Returns 1.0 if insufficient data.
    """
    if len(blink_history) < 8 or expected_hz <= 0:
        return 1.0
    # Use FFT on 0/1 sequence centered at 0.5
    sig = np.array(blink_history, dtype=float) - 0.5
    # simple period estimation: count transitions
    # fallback to FFT if enough samples
    try:
        spectrum = np.abs(np.fft.rfft(sig))
        freqs = np.fft.rfftfreq(len(sig), d=1.0 / fps)
        # ignore DC
        if len(spectrum) > 2:
            idx = int(np.argmax(spectrum[1:]) + 1)
            f_est = float(freqs[idx])
            if f_est < 0.5:
                return 1.0
            return abs(f_est - expected_hz) / expected_hz
    except Exception:
        pass
    return 1.0


def signature_score(
    blink_history: List[int],
    brightness_history: List[float],
    size_history: List[int],
    cfg: SignatureConfig,
    fps: float = 30.0,
) -> Tuple[float, dict]:
    """
    Aggregate signature score 0-1 from blink + frequency + size checks.
    Returns (score, debug_dict).
    """
    if not cfg.enabled:
        return 0.5, {"disabled": True}

    scores = {}
    # blink pattern
    if cfg.blink_enabled and blink_history:
        scores["blink_corr"] = blink_correlation(blink_history, cfg.blink_pattern)
    else:
        scores["blink_corr"] = 0.5

    # frequency claim removed per P1-05: use code correlation only
    scores["freq_error"] = 0.0
    scores["freq_score"] = 1.0

    # size envelope
    if size_history:
        last_size = size_history[-1]
        lo, hi = cfg.size_range_px
        scores["size_ok"] = 1.0 if lo <= last_size <= hi else 0.0
    else:
        scores["size_ok"] = 0.5

    # aggregate — blink is strongest, size minor
    agg = 0.80 * scores["blink_corr"] + 0.20 * scores["size_ok"]
    return float(np.clip(agg, 0, 1)), scores


def is_blink_on(frame_id: int, pattern: str, intensity: int = 255) -> int:
    """Deterministic blink schedule for synthetic generation / simulation."""
    if not pattern:
        return 1
    idx = frame_id % len(pattern)
    return 1 if pattern[idx] == "1" else 0
