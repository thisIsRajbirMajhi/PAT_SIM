"""
Stage-2 temporal identity classifier — GRU (Plan §9.1 Stage 2 / Prompt Phase 5).

Input : sequence of 20-30 observations per track
        [CNN embedding(128) + centroid(2) + velocity(2) + brightness(1)
         + shape_stability(1) + blink_corr(1) + freq_err(1) + innovation(1) + IMM(3)]
Output: PRIMARY / DECOY / UNKNOWN probabilities + confidence.

Notes
 - One-layer GRU, hidden 64 or 128, configurable via ai.yaml.
 - Falls back to a rule-based temporal voter when no trained weights
   are present, so the pipeline stays runnable without PyTorch.
 - Output never drives PID directly — it goes to the identity state
   machine (thresholds.py) which requires N consecutive confirmations.
"""
from __future__ import annotations

import logging
from typing import Dict, Optional, Tuple
import time
import numpy as np

from .types import IdentityResult, IdentityState, IdentityEvidence
from .features import SEQ_LEN, EMBED_DIM

logger = logging.getLogger(__name__)

# Optional dependencies are loaded lazily. Importing this module must never
# import torch/onnxruntime; those runtimes are only loaded when a model file
# is configured below.
_TORCH_STATE = {"loaded": False, "ok": False, "torch": None, "nn": None}
_ONNX_STATE = {"loaded": False, "ok": False, "module": None}


def _load_torch():
    """Import torch on demand; return (torch, nn) or None."""
    if not _TORCH_STATE["loaded"]:
        try:
            import torch  # type: ignore
            import torch.nn as nn  # type: ignore
            _TORCH_STATE.update({"loaded": True, "ok": True, "torch": torch, "nn": nn})
        except Exception:
            _TORCH_STATE.update({"loaded": True, "ok": False, "torch": None, "nn": None})
    if _TORCH_STATE["ok"]:
        return (_TORCH_STATE["torch"], _TORCH_STATE["nn"])
    return None


def _load_onnxruntime():
    """Import onnxruntime on demand; return the module or None."""
    if not _ONNX_STATE["loaded"]:
        try:
            import onnxruntime as ort  # type: ignore
            _ONNX_STATE.update({"loaded": True, "ok": True, "module": ort})
        except Exception:
            _ONNX_STATE.update({"loaded": True, "ok": False, "module": None})
    return _ONNX_STATE["module"] if _ONNX_STATE["ok"] else None


# -------------------------------------------------------------- fallback voter
def _heuristic_identity(seq: np.ndarray, mask: np.ndarray, signature_score: float = 0.5) -> Tuple[float, float, float]:
    """
    Conservative temporal vote: averages beacon prob + signature over
    the valid window. Returns (p_primary, p_decoy, p_unknown).
    """
    valid = mask.sum()
    if valid < 5:
        return 0.25, 0.20, 0.55  # insufficient evidence → UNKNOWN (need at least 5 obs)
    if signature_score >= 0.60 and valid >= 5:
        return 0.88, 0.06, 0.06
    if signature_score <= 0.42 and valid >= 8:
        return 0.15, 0.70, 0.15
    return 0.30, 0.25, 0.45


# -------------------------------------------------------------- torch GRU
def _build_torch_gru(torch_deps, input_dim: int = EMBED_DIM + 11, hidden: int = 64, num_classes: int = 3):
    """Construct the Stage-2 torch GRU after torch has been loaded lazily."""
    _torch, nn = torch_deps

    class GRUIdentity(nn.Module):  # type: ignore
        """1-layer GRU for track identity (hidden 64 or 128)."""
        def __init__(self, input_dim: int = input_dim, hidden: int = hidden, num_classes: int = num_classes):
            super().__init__()
            self.gru = nn.GRU(input_dim, hidden, num_layers=1, batch_first=True)
            self.fc = nn.Linear(hidden, num_classes)
            self.conf_head = nn.Sequential(nn.Linear(hidden, 16), nn.ReLU(), nn.Linear(16, 1), nn.Sigmoid())

        def forward(self, seq, mask):  # seq (B,T,D), mask (B,T)
            # pack not required for fixed-length padded sequences; GRU handles zeros
            _, h_n = self.gru(seq)  # h_n: (1,B,H)
            h = h_n.squeeze(0)  # (B,H)
            logits = self.fc(h)
            conf = self.conf_head(h).squeeze(1)
            return logits, conf

    return GRUIdentity(input_dim=input_dim, hidden=hidden, num_classes=num_classes)


class IdentityClassifier:
    """
    Stage-2 inference. Instantiate once; call ``predict(track_state)``.
    """
    def __init__(self, cfg: dict):
        ai = cfg.get("ai", {}) if isinstance(cfg, dict) else {}
        self.enabled: bool = bool(ai.get("enabled", False))
        self.model_path: Optional[str] = ai.get("identity_model_path")
        self.timeout_ms: int = int(ai.get("inference_timeout_ms", 40))
        self.seq_len: int = int(ai.get("sequence_length", SEQ_LEN))
        self.hidden: int = int(ai.get("gru_hidden", 64))
        self._torch = None
        self._torch_model = None
        self._ort_session = None

        if not self.enabled:
            return
        # Only load an optional runtime when a model file is actually configured.
        if self.model_path and self.model_path.endswith(".onnx"):
            ort = _load_onnxruntime()
            if ort is None:
                logger.warning("[IdentityClassifier] ONNX Runtime unavailable (%s); using heuristic.", self.model_path)
            else:
                try:
                    self._ort_session = ort.InferenceSession(self.model_path, providers=["CPUExecutionProvider"])
                except Exception as e:
                    logger.warning("[IdentityClassifier] ONNX load failed: %s", e)
        elif self.model_path and self.model_path.endswith((".pt", ".pth")):
            torch_deps = _load_torch()
            if torch_deps is None:
                logger.warning("[IdentityClassifier] PyTorch unavailable (%s); using heuristic.", self.model_path)
            else:
                torch, _nn = torch_deps
                try:
                    ckpt = torch.load(self.model_path, map_location="cpu")  # type: ignore
                    m = _build_torch_gru(torch_deps, hidden=self.hidden)
                    state = ckpt.get("state_dict", ckpt) if isinstance(ckpt, dict) else ckpt
                    m.load_state_dict(state, strict=False)
                    m.eval()
                    self._torch = torch
                    self._torch_model = m
                except Exception as e:
                    logger.warning("[IdentityClassifier] Torch load failed: %s", e)

    def predict_for_track(self, track, signature_score: float = 0.5) -> IdentityResult:
        """
        Build GRU input from TrackState and return IdentityResult.
        Falls back to heuristic voter when no trained model is loaded.
        """
        t0 = time.perf_counter()
        seq, mask = self._build_model_input(track)

        # try learned model within timeout
        timeout_s = self.timeout_ms / 1000.0
        p_primary, p_decoy, p_unknown = 0.34, 0.33, 0.33
        conf = 0.50

        if self.enabled and (self._torch_model is not None or self._ort_session is not None):
            try:
                if (time.perf_counter() - t0) < timeout_s:
                    if self._ort_session is not None:
                        inputs = {
                            self._ort_session.get_inputs()[0].name: seq[None, :, :].astype(np.float32),
                            self._ort_session.get_inputs()[1].name: mask[None, :].astype(np.float32),
                        }
                        logits, c = self._ort_session.run(None, inputs)
                        probs = _softmax(logits[0])
                        p_primary, p_decoy, p_unknown = float(probs[0]), float(probs[1]), float(probs[2])
                        conf = float(c[0]) if c.size else 0.5
                    elif self._torch_model is not None and self._torch is not None:
                        _torch = self._torch
                        seq_t = _torch.from_numpy(seq).unsqueeze(0)
                        mask_t = _torch.from_numpy(mask).unsqueeze(0)
                        with _torch.no_grad():  # type: ignore
                            logits, c = self._torch_model(seq_t, mask_t)
                            probs = _torch.softmax(logits, dim=1).cpu().numpy()[0]  # type: ignore
                            p_primary, p_decoy, p_unknown = float(probs[0]), float(probs[1]), float(probs[2])
                            conf = float(c.cpu().numpy()[0])  # type: ignore
                else:
                    raise TimeoutError("identity inference timeout")
            except Exception as e:
                logger.warning("[IdentityClassifier] fallback voter (%s)", e)
                p_primary, p_decoy, p_unknown = _heuristic_identity(seq, mask, signature_score)
        else:
            p_primary, p_decoy, p_unknown = _heuristic_identity(seq, mask, signature_score)

        # map probabilities to IdentityState — high confidence goes to IDENTITY_CHECKING,
        # pipeline / state machine promotes to PRIMARY/DECOY_CONFIRMED after N consecutive frames
        if p_primary >= 0.85 or p_decoy >= 0.85:
            state = IdentityState.IDENTITY_CHECKING
        elif max(p_primary, p_decoy, p_unknown) < 0.60:
            state = IdentityState.UNKNOWN
        else:
            state = IdentityState.IDENTITY_CHECKING

        evidence = IdentityEvidence(
            optical_signature_score=float(signature_score),
            motion_score=0.0,  # filled by caller from IMM/velocity checks
            appearance_score=0.0,
            reasons=[],
        )
        return IdentityResult(
            track_id=track.track_id,
            primary_probability=float(p_primary),
            decoy_probability=float(p_decoy),
            unknown_probability=float(p_unknown),
            identity_state=state,
            measurement_quality=float(conf),
            evidence=evidence,
            model_version=self.model_path or "heuristic",
        )


    def _build_model_input(self, track) -> Tuple[np.ndarray, np.ndarray]:
        """
        Build the (seq_len, input_dim) GRU input matching the trained model.

        Two layouts exist in the codebase:
         - 139-dim: 128-d CNN embedding + 11 motion/signal features
           (features.build_gru_sequence; used when a full embedding is stored)
         - 11-dim: motion/signal features only (training pipeline layout,
           dataset.SEQ_FEATURE_DIM)
        The layout is selected by the configured model's expected input width.
        """
        from .training.dataset import SEQ_FEATURE_DIM as TRAIN_DIM, build_sequence_from_track
        expected = self._expected_input_dim()
        if expected == TRAIN_DIM:
            # model trained on the 11-dim motion/signal contract
            td = {
                "position_history": list(track.position_history),
                "velocity_history": list(track.velocity_history),
                "brightness_history": list(track.brightness_history),
                "size_history": list(track.size_history),
                "blink_history": list(track.blink_history),
                "innovation_history": list(track.innovation_history),
                "imm_probs_history": list(track.imm_probs_history),
                "track_id": track.track_id,
            }
            sample = build_sequence_from_track(td, seq_len=self.seq_len)
            if sample is None:
                return np.zeros((self.seq_len, TRAIN_DIM), dtype=np.float32), np.zeros((self.seq_len,), dtype=np.float32)
            return sample.sequence, sample.mask
        # default 139-dim layout (CNN embedding + motion/signal)
        from .features import build_gru_sequence
        seq, mask = build_gru_sequence(track, seq_len=self.seq_len)
        feat_dim = seq.shape[1]
        if expected > 0 and feat_dim != expected:
            out = np.zeros((seq.shape[0], expected), dtype=np.float32)
            w = min(feat_dim, expected)
            out[:, :w] = seq[:, :w]
            return out, mask
        return seq, mask

    def _expected_input_dim(self) -> int:
        """Query the loaded model for its expected input feature width."""
        if self._ort_session is not None:
            return int(self._ort_session.get_inputs()[0].shape[-1] or 0)
        if self._torch_model is not None:
            return int(self._torch_model.gru.input_size)
        return -1


def _softmax(x: np.ndarray) -> np.ndarray:
    e = np.exp(x - np.max(x))
    return e / (e.sum() + 1e-9)
