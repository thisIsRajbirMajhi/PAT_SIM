import cv2
import numpy as np
from ..common.types import Detection
from ..ai.types import Candidate, CandidateClass
from ..ai.features import extract_patch, PATCH_SIZE

class BeaconDetector:
    def __init__(self, cfg):
        d = cfg["detector"]
        cam_res = tuple(cfg["camera"]["resolution"])
        self.k = float(d.get("threshold_k",3.0))
        self.min_area = int(d.get("min_area",8))
        self.max_area = int(d.get("max_area",900))
        self.blur = int(d.get("blur_ksize",3))
        self.block = int(d.get("adaptive_block",51))
        self.C = int(d.get("adaptive_C",-5))
        self.morph = int(d.get("morphology_ksize", 3))
        self.res_w, self.res_h = cam_res
        self.cfg = cfg

    def update_config(self, cfg):
        self.__init__(cfg)

    def detect_candidates(self, frame_gray: np.ndarray, predicted_pos=None):
        """
        Multi-candidate generation (Plan §5). Returns List[Candidate] with
        64x64 patches, numerical features and heuristic scores. Never
        uses brightness alone to decide primary.
        """
        if frame_gray is None or frame_gray.size == 0:
            return []
        if len(frame_gray.shape) == 3:
            img = cv2.cvtColor(frame_gray, cv2.COLOR_BGR2GRAY)
        else:
            img = frame_gray
        if self.blur >= 3:
            k = self.blur if self.blur % 2 == 1 else self.blur + 1
            img = cv2.GaussianBlur(img, (k, k), 0)
        if self.block > 1:
            k = self.block if self.block % 2 == 1 else self.block + 1
            binary = cv2.adaptiveThreshold(img, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, k, self.C)
        else:
            bg = float(np.median(img))
            noise = float(np.std(img)) + 1e-6
            p98 = float(np.percentile(img, 98))
            thresh_val = max(bg + self.k * noise, p98 - 8, 120)
            thresh_val = float(np.clip(thresh_val, 80, 230))
            _, binary = cv2.threshold(img, thresh_val, 255, cv2.THRESH_BINARY)
            
        mk = self.morph if self.morph % 2 == 1 else self.morph + 1
        if mk > 1:
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (mk, mk))
            binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=1)
        num, labels, stats, centroids = cv2.connectedComponentsWithStats(binary, connectivity=8)
        h, w = img.shape
        cx, cy = w / 2, h / 2
        if predicted_pos is not None:
            px, py = predicted_pos
        else:
            px, py = cx, cy
        candidates = []
        cid = 0
        for i in range(1, num):
            area = int(stats[i, cv2.CC_STAT_AREA])
            if area < self.min_area or area > self.max_area:
                continue
            x = int(stats[i, cv2.CC_STAT_LEFT]); y = int(stats[i, cv2.CC_STAT_TOP])
            ww = int(stats[i, cv2.CC_STAT_WIDTH]); hh = int(stats[i, cv2.CC_STAT_HEIGHT])
            aspect = max(ww, hh) / max(1, min(ww, hh))
            if aspect > 3.5:
                continue
            mask = (labels == i).astype(np.uint8) * 255
            mean_int = float(cv2.mean(img, mask=mask)[0])
            peak = float(np.max(img[labels == i])) if np.any(labels == i) else mean_int
            ys, xs = np.where(labels == i)
            intens = img[ys, xs].astype(np.float32)
            s = float(np.sum(intens)) + 1e-6
            cx_det = float(np.sum(intens * xs) / s)
            cy_det = float(np.sum(intens * ys) / s)
            bbox_area = ww * hh
            fill = area / max(1, bbox_area)
            dist = float(np.hypot(cx_det - px, cy_det - py))
            # local contrast
            try:
                local_contrast = float(np.std(img[max(0, y):y+hh, max(0, x):x+ww]))
            except Exception:
                local_contrast = 0.0
            # need patch for AI
            try:
                patch = extract_patch(img, (cx_det, cy_det), size=PATCH_SIZE)
            except Exception:
                patch = None
            brightness_score = (peak / 255.0) * 0.3 + (mean_int / 255.0) * 0.2
            shape_score = fill * 0.2 + (1 - min(aspect - 1, 1)) * 0.1
            prox_score = max(0, 1 - dist / (max(w, h) * 0.6)) * 0.2
            score = brightness_score + shape_score + prox_score
            if peak > 200:
                score += 0.15
            cid += 1
            c = Candidate(
                candidate_id=cid,
                centroid_px=(cx_det, cy_det),
                bbox=(x, y, ww, hh),
                area=float(area),
                width=ww, height=hh,
                aspect_ratio=float(aspect),
                brightness=float(mean_int),
                peak_intensity=float(peak),
                local_contrast=float(local_contrast),
                compactness=float(fill),
                distance_from_prediction=float(dist),
                patch=patch,
                beacon_probability=float(np.clip(score, 0, 1)),
                detection_class=CandidateClass.UNKNOWN,
                measurement_quality=float(np.clip(0.35 + fill * 0.3 + peak / 255 * 0.2, 0, 1)),
            )
            candidates.append(c)
        # sort by score descending (highest beacon prob first) but do not equate to primary
        candidates.sort(key=lambda c: c.beacon_probability, reverse=True)
        return candidates

    def detect(self, frame_gray: np.ndarray, predicted_pos=None) -> Detection:
        """Backward-compatible single-best detection (wraps detect_candidates)."""
        cands = self.detect_candidates(frame_gray, predicted_pos=predicted_pos)
        if not cands:
            return Detection(valid=False, confidence=0.0)
        best = cands[0]
        confidence = float(np.clip(0.35 + best.beacon_probability * 0.65 + (best.peak_intensity - 180) / 255 * 0.2, 0, 1))
        return Detection(valid=True, centroid_px=best.centroid_px, bbox=best.bbox, confidence=confidence, score=best.beacon_probability, area=best.area)
