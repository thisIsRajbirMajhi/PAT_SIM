import cv2
import numpy as np
from ..common.types import Detection

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
        self.res_w, self.res_h = cam_res
        self.cfg = cfg

    def update_config(self, cfg):
        self.__init__(cfg)

    def detect(self, frame_gray: np.ndarray, predicted_pos=None) -> Detection:
        if frame_gray is None or frame_gray.size==0:
            return Detection(valid=False)
        # Sr.2 Camera Type: monochrome or colour — handle both
        if len(frame_gray.shape) == 3:
            img = cv2.cvtColor(frame_gray, cv2.COLOR_BGR2GRAY)
        else:
            img = frame_gray
        # preprocess: small gaussian blur
        if self.blur >= 3:
            k = self.blur if self.blur%2==1 else self.blur+1
            img = cv2.GaussianBlur(img, (k,k), 0)

        # adaptive vs percentile threshold: use mean + k*std method per plan
        # estimate background
        bg = float(np.median(img))
        noise = float(np.std(img)) + 1e-6
        # also consider percentile 98
        p98 = float(np.percentile(img, 98))
        thresh_val = max(bg + self.k*noise, p98 - 8, 120)  # clamp low bound
        thresh_val = float(np.clip(thresh_val, 80, 230))

        _, binary = cv2.threshold(img, thresh_val, 255, cv2.THRESH_BINARY)

        # morphological opening to remove salt noise fragments
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3,3))
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=1)

        # connected components
        num, labels, stats, centroids = cv2.connectedComponentsWithStats(binary, connectivity=8)
        best = None
        best_score = -1e9
        h,w = img.shape
        cx, cy = w/2, h/2
        # predicted gating distance
        for i in range(1, num):  # skip background 0
            area = stats[i, cv2.CC_STAT_AREA]
            if area < self.min_area or area > self.max_area:
                continue
            x = stats[i, cv2.CC_STAT_LEFT]; y = stats[i, cv2.CC_STAT_TOP]
            ww = stats[i, cv2.CC_STAT_WIDTH]; hh = stats[i, cv2.CC_STAT_HEIGHT]
            aspect = max(ww, hh) / max(1, min(ww, hh))
            if aspect > 3.5:
                continue
            # mask for this component
            mask = (labels == i).astype(np.uint8)*255
            mean_int = cv2.mean(img, mask=mask)[0]
            peak = float(np.max(img[labels==i])) if np.any(labels==i) else mean_int
            # centroid intensity-weighted
            ys, xs = np.where(labels==i)
            intens = img[ys, xs].astype(np.float32)
            s = float(np.sum(intens)) + 1e-6
            cx_det = float(np.sum(intens * xs) / s)
            cy_det = float(np.sum(intens * ys) / s)
            # shape compactness: area vs bbox area
            bbox_area = ww*hh
            fill = area / max(1, bbox_area)
            # distance from center / prediction
            if predicted_pos is not None:
                px, py = predicted_pos
                dist = np.hypot(cx_det - px, cy_det - py)
            else:
                dist = np.hypot(cx_det - cx, cy_det - cy)
            # scoring
            brightness_score = (peak/255.0)*0.3 + (mean_int/255.0)*0.2
            shape_score = fill*0.2 + (1 - min(aspect-1,1))*0.1
            prox_score = max(0, 1 - dist/ (max(w,h)*0.6))*0.2
            score = brightness_score + shape_score + prox_score
            # bonus for compact bright
            if peak > 200: score += 0.15
            if score > best_score:
                best_score = score
                # intensity weighted centroid refined
                best = (cx_det, cy_det, x, y, ww, hh, area, peak, mean_int, score)

        if best is None:
            return Detection(valid=False, confidence=0.0)

        cx_det, cy_det, x, y, ww, hh, area, peak, mean_int, score = best
        # confidence mapping
        confidence = float(np.clip(0.35 + score*0.65 + (peak-180)/255*0.2, 0, 1))
        return Detection(valid=True, centroid_px=(cx_det, cy_det), bbox=(x,y,ww,hh), confidence=confidence, score=score, area=area)
