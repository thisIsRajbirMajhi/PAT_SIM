"""
AI inference pipeline — wiring Plan §9.1 / Prompt Phase 7.

Responsibilities
 - Orchestrates: classical candidates → CandidateClassifier → TrackManager
   → IdentityClassifier → IdentityStateMachine.
 - Never calls EKF.update or PID.step directly — it only returns
   IdentityResults for the tracker/controller to consume.
 - Safe fallback (Plan §9.2 Step 11): on timeout / exception it
   increases measurement uncertainty, suppresses aggressive PID, and
   logs the failure. It NEVER confirms a primary on failure.

Usage (from Tracker / MainWindow):
    pipeline = AIInferencePipeline(cfg)
    results: List[AIInferenceResult] = pipeline.step(frame_gray, candidates, tracks)
    # caller then feeds the PRIMARY_CONFIRMED track's measurement to EKF

When ai.enabled == false the pipeline short-circuits and returns [].
"""
from __future__ import annotations

import time
from typing import List, Dict, Optional
import numpy as np

from .types import Candidate, AIInferenceResult, IdentityState, TrackState
from .candidate_model import CandidateClassifier
from .identity_model import IdentityClassifier
from .signatures import SignatureConfig, signature_score
from .thresholds import ThresholdConfig, decide_identity


class AIInferencePipeline:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        ai = cfg.get("ai", {}) if isinstance(cfg, dict) else {}
        self.enabled: bool = bool(ai.get("enabled", False))
        self.candidate_clf = CandidateClassifier(cfg)
        self.identity_clf = IdentityClassifier(cfg)
        # signature + threshold configs loaded from ai.yaml (with defaults)
        sig = ai.get("signatures", ai.get("signature", {})) if isinstance(ai, dict) else {}
        self.sig_cfg = SignatureConfig(
            enabled=bool(sig.get("enabled", True)),
            blink_pattern=str(sig.get("blink_pattern", "10110010")),
            modulation_freq_hz=float(sig.get("modulation_freq_hz", 12.0)),
            freq_tolerance=float(sig.get("freq_tolerance", 0.05)),
            expected_shape=str(sig.get("expected_shape", "square")),
            size_range_px=tuple(sig.get("size_range_px", (5, 20))),  # type: ignore
            max_speed_px_per_frame=float(sig.get("max_speed_px_per_frame", 20.0)),
        )
        thr = ai.get("thresholds", {}) if isinstance(ai, dict) else {}
        self.thr_cfg = ThresholdConfig(
            primary_threshold=float(thr.get("primary_threshold", 0.85)),
            decoy_threshold=float(thr.get("decoy_threshold", 0.85)),
            confirmation_frames=int(thr.get("confirmation_frames", 5)),
            unknown_low=float(thr.get("unknown_low", 0.45)),
            unknown_high=float(thr.get("unknown_high", 0.85)),
        )
        self._fps: float = float(cfg.get("camera", {}).get("fps", 30.0))
        # per-track confirmation counters (track_id → consecutive primary frames)
        self._confirm_counters: Dict[int, int] = {}
        self._decoy_counters: Dict[int, int] = {}

    def update_config(self, cfg: dict) -> None:
        self.__init__(cfg)

    # ------------------------------------------------------------------
    def step(
        self,
        frame_gray: np.ndarray,
        candidates: List[Candidate],
        tracks: Dict[int, TrackState],
    ) -> List[AIInferenceResult]:
        """
        Run Stage-1 + Stage-2 for all candidates/tracks.
        Returns one AIInferenceResult per candidate (identity may be None
        for the first few frames of a new track).
        """
        if not self.enabled or not candidates:
            return []

        t0 = time.perf_counter()
        timeout_s = float(self.cfg.get("ai", {}).get("inference_timeout_ms", 80)) / 1000.0

        # Stage-1: annotate candidates
        try:
            candidates = self.candidate_clf.predict(candidates)
        except Exception as e:
            # safe fallback: mark all UNKNOWN
            return [
                AIInferenceResult(candidate=c, identity=None, fallback_triggered=True, error=str(e))
                for c in candidates
            ]

        results: List[AIInferenceResult] = []
        for c in candidates:
            if (time.perf_counter() - t0) > timeout_s:
                results.append(AIInferenceResult(candidate=c, identity=None, fallback_triggered=True, error="pipeline timeout"))
                continue

            track = tracks.get(c.candidate_id)
            if track is None:
                # new track — not enough history for GRU; return Stage-1 only
                results.append(AIInferenceResult(candidate=c, identity=None, latency_ms=(time.perf_counter()-t0)*1000))
                continue

            # signature score from track history
            sig_score, _dbg = signature_score(
                track.blink_history, track.brightness_history,
                getattr(track, 'size_history', track.brightness_history),
                self.sig_cfg, fps=self._fps,
            )
            try:
                identity = self.identity_clf.predict_for_track(track, signature_score=sig_score)
                # apply temporal confirmation thresholds
                identity = self._apply_confirmation(track.track_id, identity)
                # enrich evidence
                identity.evidence.optical_signature_score = float(sig_score)
                results.append(AIInferenceResult(candidate=c, identity=identity, latency_ms=(time.perf_counter()-t0)*1000))
            except Exception as e:
                results.append(AIInferenceResult(candidate=c, identity=None, fallback_triggered=True, error=str(e)))

        return results

    # ------------------------------------------------------------------
    def _apply_confirmation(self, track_id: int, res) -> object:
        """
        Require primary/decoy confidence to hold for N consecutive frames
        before confirming (Plan §6). Otherwise keep as IDENTITY_CHECKING.
        """
        # primary confirmation
        if res.primary_probability >= self.thr_cfg.primary_threshold:
            self._confirm_counters[track_id] = self._confirm_counters.get(track_id, 0) + 1
        else:
            self._confirm_counters[track_id] = 0
        # decoy confirmation
        if res.decoy_probability >= self.thr_cfg.decoy_threshold:
            self._decoy_counters[track_id] = self._decoy_counters.get(track_id, 0) + 1
        else:
            self._decoy_counters[track_id] = 0

        if self._confirm_counters[track_id] >= self.thr_cfg.confirmation_frames:
            res.identity_state = IdentityState.PRIMARY_CONFIRMED
        elif self._decoy_counters[track_id] >= self.thr_cfg.confirmation_frames:
            res.identity_state = IdentityState.DECOY_CONFIRMED
        elif res.primary_probability < self.thr_cfg.unknown_high and res.decoy_probability < self.thr_cfg.decoy_threshold:
            # low confidence → UNKNOWN / keep checking
            if res.identity_state == IdentityState.PRIMARY_CONFIRMED:
                res.identity_state = IdentityState.IDENTITY_CHECKING
        return res

    # ------------------------------------------------------------------
    def primary_track_id(self, results: List[AIInferenceResult]) -> Optional[int]:
        """Return track_id of the PRIMARY_CONFIRMED candidate, or None."""
        for r in results:
            if r.identity and r.identity.identity_state == IdentityState.PRIMARY_CONFIRMED:
                return r.candidate.candidate_id
        return None

    def rejected_ids(self, results: List[AIInferenceResult]) -> List[int]:
        return [r.candidate.candidate_id for r in results if r.identity and r.identity.identity_state == IdentityState.DECOY_CONFIRMED]
