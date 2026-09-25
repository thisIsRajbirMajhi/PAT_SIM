"""
Stage-1 candidate classifier — MobileNetV3-Small (Plan §9.1 Stage 1 / Prompt Phase 4).

Input : 64×64 grayscale patch + 9 numerical features (features.numerical_features)
Output: BEACON_LIKE / DECOY_LIKE / NOISE / UNKNOWN probabilities,
        measurement_quality (0-1), and 128-d appearance embedding.

Notes
 - Runs on CPU / edge; supports quantized ONNX/TFLite export.
 - Inference must never block the tracking loop: ``predict`` has a
   hard timeout and returns UNKNOWN on failure (safe fallback).
 - Training script in ai/training/train_candidate.py creates and
   saves the weights consumed here; this module only loads + infers.
 - If PyTorch / ONNX Runtime is unavailable, a deterministic
   heuristic fallback classifier is used so the pipeline stays runnable
   with ``ai.enabled == false`` or without model files.

Public API:
    CandidateClassifier(cfg)         — load from configs/ai.yaml
    .predict(candidates, frame)      — list[Candidate] → list[Candidate] (annotated)
    .embed(patch)                    — patch → 128-d embedding (for GRU)
"""
from __future__ import annotations

import logging
from typing import List, Optional, Tuple
from pathlib import Path
import time
import numpy as np

from .types import Candidate, CandidateClass
from .features import PATCH_SIZE

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


# ------------------------------------------------------------------ fallback
def _heuristic_classify(c: Candidate) -> Tuple[CandidateClass, float, float]:
    """
    Lightweight fallback when no learned model is available.
    Uses brightness + compactness + area envelope. Returns
    (class, beacon_prob, quality). Calibrated to be conservative:
    prefers UNKNOWN over false BEACON_LIKE.
    """
    # compactness and size gate
    size_ok = 5 <= c.area <= 900 and 1.0 <= c.aspect_ratio <= 3.5
    bright = c.peak_intensity / 255.0
    # threshold tuned from detector defaults: bright compact blobs → beacon
    score = 0.35 * bright + 0.25 * c.compactness + (0.20 if size_ok else 0.0) + 0.10 * (c.local_contrast / 80.0)
    score = float(np.clip(score, 0, 1))
    quality = float(np.clip(0.30 + 0.55 * c.compactness + 0.15 * bright, 0, 1))
    if score >= 0.62 and bright >= 0.55:
        return CandidateClass.BEACON_LIKE, float(np.clip(0.55 + 0.40 * score, 0, 1)), quality
    if score <= 0.38:
        return CandidateClass.NOISE, float(np.clip(0.45 + 0.30 * (1 - score), 0, 1)), quality
    return CandidateClass.UNKNOWN, 0.50, quality * 0.65


# -------------------------------------------------------------- torch model
def _build_torch_candidate(torch_deps, num_classes: int = 4, embed_dim: int = 128):
    """Construct the Stage-1 torch model after torch has been loaded lazily."""
    torch, nn = torch_deps

    class MobileNetV3SmallPatch(nn.Module):  # type: ignore
        """
        Thin wrapper around torchvision MobileNetV3-Small adapted for
        single-channel 64×64 input. The numerical feature branch is a
        2-layer MLP fused before the classifier head.
        Only instantiated during training or when torch weights are present.
        """
        def __init__(self, num_classes: int = num_classes, embed_dim: int = embed_dim):
            super().__init__()
            try:
                from torchvision.models import mobilenet_v3_small  # type: ignore
                backbone = mobilenet_v3_small(weights=None)
                # adapt first conv to 1 channel
                orig = backbone.features[0][0]
                new_conv = nn.Conv2d(1, orig.out_channels, kernel_size=orig.kernel_size,
                                     stride=orig.stride, padding=orig.padding, bias=False)
                with torch.no_grad():
                    new_conv.weight[:] = orig.weight.mean(dim=1, keepdim=True)
                backbone.features[0][0] = new_conv
                self.backbone = backbone.features
                feat_dim = 576  # mobilenet_v3_small last channel
            except Exception:
                # minimal CNN fallback if torchvision unavailable
                self.backbone = nn.Sequential(
                    nn.Conv2d(1, 16, 3, 2, 1), nn.BatchNorm2d(16), nn.Hardswish(),
                    nn.Conv2d(16, 32, 3, 2, 1), nn.BatchNorm2d(32), nn.Hardswish(),
                    nn.AdaptiveAvgPool2d(1),
                )
                feat_dim = 32
            self.feat_dim = feat_dim
            self.num_feat = 9
            self.mlp = nn.Sequential(nn.Linear(self.num_feat, 32), nn.ReLU(), nn.Linear(32, 32), nn.ReLU())
            self.embed_head = nn.Linear(feat_dim + 32, embed_dim)
            self.cls_head = nn.Linear(feat_dim + 32, num_classes)
            self.quality_head = nn.Sequential(nn.Linear(feat_dim + 32, 16), nn.ReLU(), nn.Linear(16, 1), nn.Sigmoid())

        def forward(self, patch, num_feat):  # patch: (B,1,64,64), num_feat: (B,9)
            f = self.backbone(patch)
            if f.dim() == 4:
                f = f.mean(dim=(2, 3))
            g = self.mlp(num_feat)
            h = torch.cat([f, g], dim=1)
            emb = self.embed_head(h)
            logits = self.cls_head(h)
            qual = self.quality_head(h).squeeze(1)
            return logits, qual, emb

    return MobileNetV3SmallPatch(num_classes=num_classes, embed_dim=embed_dim)


# -------------------------------------------------------------- public classifier
_CLASS_ORDER = [CandidateClass.BEACON_LIKE, CandidateClass.DECOY_LIKE, CandidateClass.NOISE, CandidateClass.UNKNOWN]


class CandidateClassifier:
    """
    Stage-1 inference. Thread-safe for single-frame pipeline.
    Set ``cfg['ai']['candidate_model_path']`` to a .pt or .onnx file;
    otherwise the heuristic fallback is used.
    """
    def __init__(self, cfg: dict):
        ai = cfg.get("ai", {}) if isinstance(cfg, dict) else {}
        self.enabled: bool = bool(ai.get("enabled", False))
        self.model_path: Optional[str] = ai.get("candidate_model_path") or ai.get("model_path")
        self.timeout_ms: int = int(ai.get("inference_timeout_ms", 40))
        self.patch_size: int = int(ai.get("patch_size", PATCH_SIZE))
        self.device = "cpu"
        self._torch = None
        self._torch_model = None
        self._ort_session = None

        if not self.enabled:
            return
        # Only load an optional runtime when a model file is actually configured.
        # try ONNX first (preferred for deployment)
        if self.model_path and self.model_path.endswith(".onnx"):
            ort = _load_onnxruntime()
            if ort is None:
                logger.warning("[CandidateClassifier] ONNX Runtime unavailable (%s); using heuristic.", self.model_path)
            else:
                try:
                    self._ort_session = ort.InferenceSession(self.model_path, providers=["CPUExecutionProvider"])
                except Exception as e:
                    logger.warning("[CandidateClassifier] ONNX load failed (%s): %s; using heuristic.", self.model_path, e)
        elif self.model_path and self.model_path.endswith((".pt", ".pth")):
            torch_deps = _load_torch()
            if torch_deps is None:
                logger.warning("[CandidateClassifier] PyTorch unavailable (%s); using heuristic.", self.model_path)
            else:
                torch, _nn = torch_deps
                try:
                    ckpt = torch.load(self.model_path, map_location="cpu")  # type: ignore
                    m = _build_torch_candidate(torch_deps)
                    # tolerate checkpoint dict variations
                    state = ckpt.get("state_dict", ckpt) if isinstance(ckpt, dict) else ckpt
                    m.load_state_dict(state, strict=False)
                    m.eval()
                    self._torch = torch
                    self._torch_model = m
                except Exception as e:
                    logger.warning("[CandidateClassifier] Torch load failed (%s): %s; using heuristic.", self.model_path, e)

    # -- single candidate -------------------------------------------------
    def _infer_heuristic(self, c: Candidate) -> Candidate:
        cls, prob, qual = _heuristic_classify(c)
        c.detection_class = cls
        c.beacon_probability = prob if cls == CandidateClass.BEACON_LIKE else (1 - prob if cls == CandidateClass.NOISE else 0.5)
        c.measurement_quality = qual
        # dummy embedding: encode brightness/contrast/size as first dims
        emb = np.zeros((128,), dtype=np.float32)
        emb[0] = c.brightness / 255.0
        emb[1] = c.local_contrast / 80.0
        emb[2] = c.compactness
        emb[3] = c.beacon_probability
        c.appearance_embedding = emb
        return c

    def predict(self, candidates: List[Candidate]) -> List[Candidate]:
        """
        Annotate each candidate in-place. Returns same list.
        Honors hard timeout per frame (sum over candidates).
        """
        if not candidates:
            return candidates
        if not self.enabled or (self._torch_model is None and self._ort_session is None):
            return [self._infer_heuristic(c) for c in candidates]

        t0 = time.perf_counter()
        timeout_s = self.timeout_ms / 1000.0
        out: List[Candidate] = []
        for c in candidates:
            if (time.perf_counter() - t0) > timeout_s:
                # timeout → mark remaining as UNKNOWN fallback
                c.detection_class = CandidateClass.UNKNOWN
                c.measurement_quality = 0.35
                out.append(c)
                continue
            try:
                out.append(self._infer_one(c))
            except Exception as e:
                logger.warning("[CandidateClassifier] inference error: %s", e)
                out.append(self._infer_heuristic(c))
        return out

    def _infer_one(self, c: Candidate) -> Candidate:
        # ONNX path
        if self._ort_session is not None:
            import cv2 as _cv2  # local import
            patch = c.patch if c.patch is not None else np.zeros((64, 64), np.float32)
            patch_n = patch[None, None, :, :].astype(np.float32)  # (1,1,64,64)
            from .features import numerical_features
            num = numerical_features(c)[None, :].astype(np.float32)
            # input names depend on export; try common names
            try:
                inputs = {self._ort_session.get_inputs()[0].name: patch_n}
                if len(self._ort_session.get_inputs()) > 1:
                    inputs[self._ort_session.get_inputs()[1].name] = num
                logits, qual, emb = self._ort_session.run(None, inputs)
            except Exception:
                return self._infer_heuristic(c)
            probs = _softmax(logits[0])
            idx = int(np.argmax(probs))
            c.detection_class = _CLASS_ORDER[idx]
            c.beacon_probability = float(probs[0])
            c.measurement_quality = float(np.clip(qual[0] if qual.size else 0.5, 0, 1))
            c.appearance_embedding = emb[0].astype(np.float32) if emb.size else c.appearance_embedding
            return c
        # Torch path
        if self._torch_model is not None and self._torch is not None:
            _torch = self._torch
            patch = c.patch if c.patch is not None else np.zeros((64, 64), np.float32)
            patch_t = _torch.from_numpy(patch).unsqueeze(0).unsqueeze(0)  # (1,1,64,64)
            from .features import numerical_features as _nf
            num_t = _torch.from_numpy(_nf(c)).unsqueeze(0)
            with _torch.no_grad():  # type: ignore
                logits, qual, emb = self._torch_model(patch_t, num_t)
                probs = _torch.softmax(logits, dim=1).cpu().numpy()[0]  # type: ignore
                q = float(qual.cpu().numpy()[0])  # type: ignore
                e = emb.cpu().numpy()[0]  # type: ignore
            idx = int(np.argmax(probs))
            c.detection_class = _CLASS_ORDER[idx]
            c.beacon_probability = float(probs[0])
            c.measurement_quality = float(np.clip(q, 0, 1))
            c.appearance_embedding = e.astype(np.float32)
            return c
        return self._infer_heuristic(c)


def _softmax(x: np.ndarray) -> np.ndarray:
    e = np.exp(x - np.max(x))
    return e / (e.sum() + 1e-9)
