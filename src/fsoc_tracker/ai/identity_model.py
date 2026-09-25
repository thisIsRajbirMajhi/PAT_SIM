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

from typing import Dict, Optional, Tuple
import time
import numpy as np

from .types import IdentityResult, IdentityState, IdentityEvidence
from .features import SEQ_LEN, EMBED_DIM

try:
    import torch  # type: ignore
    import torch.nn as nn  # type: ignore
    HAS_TORCH = True
except Exception:
    HAS_TORCH = False

try:
    import onnxruntime as ort  # type: ignore
    HAS_ONNX = True
except Exception:
    HAS_ONNX = False


# -------------------------------------------------------------- fallback voter
def _heuristic_identity(seq: np.ndarray, mask: np.ndarray, signature_score: float = 0.5) -> Tuple[float, float, float]:
    """
    Conservative temporal vote: averages beacon prob + signature over
    the valid window. Returns (p_primary, p_decoy, p_unknown).
    """
    valid = mask.sum()
    if valid < 3:
        return 0.20, 0.20, 0.60  # insufficient evidence → UNKNOWN
    # seq[:, 3] is beacon_prob proxy when embeddings unavailable; use signature as tie-breaker
    # prefer UNKNOWN unless strong evidence
    if signature_score >= 0.72 and valid >= 5:
        return 0.78, 0.12, 0.10
    if signature_score <= 0.42:
        return 0.15, 0.70, 0.15
    return 0.30, 0.25, 0.45


# -------------------------------------------------------------- torch GRU
if HAS_TORCH:
    class GRUIdentity(nn.Module):  # type: ignore
        """1-layer GRU for track identity (hidden 64 or 128)."""
        def __init__(self, input_dim: int = EMBED_DIM + 11, hidden: int = 64, num_classes: int = 3):
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
        self._torch_model = None
        self._ort_session = None

        if not self.enabled:
            return
        if self.model_path and self.model_path.endswith(".onnx") and HAS_ONNX:
            try:
                self._ort_session = ort.InferenceSession(self.model_path, providers=["CPUExecutionProvider"])
            except Exception as e:
                print(f"[IdentityClassifier] ONNX load failed: {e}")
        elif self.model_path and self.model_path.endswith((".pt", ".pth")) and HAS_TORCH:
            try:
                ckpt = torch.load(self.model_path, map_location="cpu")  # type: ignore
                m = GRUIdentity(hidden=self.hidden)
                state = ckpt.get("state_dict", ckpt) if isinstance(ckpt, dict) else ckpt
                m.load_state_dict(state, strict=False)
                m.eval()
                self._torch_model = m
            except Exception as e:
                print(f"[IdentityClassifier] Torch load failed: {e}")

    def predict_for_track(self, track, signature_score: float = 0.5) -> IdentityResult:
        """
        Build GRU input from TrackState and return IdentityResult.
        Falls back to heuristic voter when no trained model is loaded.
        """
        t0 = time.perf_counter()
        from .features import build_gru_sequence
        seq, mask = build_gru_sequence(track, seq_len=self.seq_len)

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
                    elif self._torch_model is not None and HAS_TORCH:
                        import torch as _torch  # type: ignore
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
                print(f"[IdentityClassifier] fallback voter ({e})")
                p_primary, p_decoy, p_unknown = _heuristic_identity(seq, mask, signature_score)
        else:
            p_primary, p_decoy, p_unknown = _heuristic_identity(seq, mask, signature_score)

        # map probabilities to IdentityState via thresholds (caller may override)
        # default: require PRIMARY >= 0.85 for confirmation — actual gating in thresholds.py/state machine
        if p_primary >= 0.85:
            state = IdentityState.PRIMARY_CONFIRMED
        elif p_decoy >= 0.85:
            state = IdentityState.DECOY_CONFIRMED
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


def _softmax(x: np.ndarray) -> np.ndarray:
    e = np.exp(x - np.max(x))
    return e / (e.sum() + 1e-9)
