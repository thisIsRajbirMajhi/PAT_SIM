import cv2, time
import numpy as np
from .base import FrameSource
from ..common.types import Frame, GroundTruth

class VideoSource(FrameSource):
    """
    External video adapter for Benchmark Performance-2.
    - Preserves frame order (sequential read, no reordering or skipping)
    - Handles any resolution natively (no silent resize that would change error scale)
    - Normalizes timestamps to 30fps per spec unless native_fps is set
    - Optional per-frame ground-truth annotations CSV for centroiding comparison
    - Supports image centre calibration (pixel offset) for videos where principal point != frame centre
    - Clearly bypasses PTZ: is_ptz_enabled == False, no camera commands are applied
    """
    def __init__(self, path: str, target_fps: float = 30.0, centre_offset_x: float = 0.0, centre_offset_y: float = 0.0,
                 annotations_path: str = None, native_fps: bool = False):
        self.path = path
        self.cap = cv2.VideoCapture(path)
        if not self.cap.isOpened():
            raise FileNotFoundError(f"Cannot open video: {path}")
        # Original FPS from file; fallback to target_fps if unavailable (some codecs report 0)
        raw_fps = self.cap.get(cv2.CAP_PROP_FPS)
        file_fps = float(raw_fps) if raw_fps and 1 <= raw_fps <= 240 else float(target_fps)
        # Spec Benchmark-2: .mp4 @30fps. Normalize timestamps to target_fps so
        # acquisition/re-acquisition seconds stay comparable across files, unless
        # the caller explicitly requests native timing.
        self.native_fps = bool(native_fps)
        self.file_fps = float(file_fps)
        self._fps = float(file_fps) if self.native_fps else float(target_fps)
        self._w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self._h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.frame_id = 0
        # Calibration: image centre offset in pixels (user-defined via Control Deck)
        self.centre_offset_x = float(centre_offset_x)
        self.centre_offset_y = float(centre_offset_y)
        # PTZ is explicitly disabled for video mode — measurement only
        self.is_ptz_enabled = False
        # For frame order verification
        self._last_frame_id = -1
        # Optional annotations: CSV rows frame_id,x,y[,visible] or x,y per line
        self.annotations = self._load_annotations(annotations_path) if annotations_path else {}

    @property
    def fps(self): return self._fps
    @property
    def resolution(self): return (self._w, self._h)

    def is_opened(self): return self.cap.isOpened()
    def release(self): self.cap.release()

    def set_centre_calibration(self, offset_x: float, offset_y: float):
        """Allow calibration of image centre (pixel coordinates) for offset videos."""
        self.centre_offset_x = float(offset_x)
        self.centre_offset_y = float(offset_y)

    def get_calibrated_centre(self):
        """Return calibrated image centre: (W/2 + offset_x, H/2 + offset_y)."""
        return (self._w / 2.0 + self.centre_offset_x, self._h / 2.0 + self.centre_offset_y)

    def reset(self):
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        self.frame_id = 0
        self._last_frame_id = -1

    @staticmethod
    def _load_annotations(path):
        """Load {frame_id: (x, y, visible)} from CSV (frame_id,x,y[,visible] or x,y)."""
        import csv as _csv
        import os as _os
        ann = {}
        if not path or not _os.path.exists(path):
            if path:
                raise FileNotFoundError(f"Annotations not found: {path}")
            return ann
        with open(path, newline="") as f:
            rows = [r for r in _csv.reader(f) if r and not str(r[0]).strip().startswith("#")]
        if not rows:
            return ann
        # header detection: non-numeric first row
        try:
            float(rows[0][0])
            has_header = False
        except Exception:
            has_header = True
            rows = rows[1:]
        for i, row in enumerate(rows):
            try:
                vals = [v for v in row if str(v).strip() != ""]
                if len(vals) >= 4:
                    fid, x, y, vis = int(float(vals[0])), float(vals[1]), float(vals[2]), vals[3]
                    visible = str(vis).strip().lower() not in ("0", "false", "no", "hidden", "n")
                elif len(vals) == 3:
                    fid, x, y = int(float(vals[0])), float(vals[1]), float(vals[2])
                    visible = True
                elif len(vals) == 2:
                    fid, x, y = i, float(vals[0]), float(vals[1])
                    visible = True
                else:
                    continue
                ann[int(fid)] = (float(x), float(y), bool(visible))
            except Exception:
                continue
        return ann

    def read(self):
        # Preserve frame order: sequential read, no skipping, no reordering
        ret, frame = self.cap.read()
        if not ret:
            return None, None
        # Handle native resolution without silent resize (preserve error scale)
        # Do NOT resize to 640x480; keep original dimensions so centroid error stays in native pixels
        # If frame dimensions differ from reported _w/_h (variable), update
        h, w = frame.shape[:2]
        if w != self._w or h != self._h:
            # Update to actual frame size (some videos have inconsistent reported size)
            self._w, self._h = w, h
        # Convert to grayscale for monochrome processing (spec: monochrome focal plane array)
        # If already gray, keep; if colour, convert via standard luminance
        if len(frame.shape) == 3:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        else:
            gray = frame
        # Verify frame order: frame_id must increment by 1
        assert self.frame_id == self._last_frame_id + 1, f"Frame order violated: got {self.frame_id} after {self._last_frame_id}"
        self._last_frame_id = self.frame_id
        f = Frame(image=gray, frame_id=self.frame_id, timestamp=self.frame_id / self._fps, source_name="video")
        # Ground truth: predefined annotations when supplied (Benchmark-2
        # centroiding comparison); otherwise measurement-only dummy.
        ann = self.annotations.get(self.frame_id)
        if ann is not None:
            ax, ay, vis = ann
            gt = GroundTruth(world_pos=(0, 0), visible=bool(vis),
                             image_pos=(float(ax), float(ay)) if vis else None)
        else:
            gt = GroundTruth(world_pos=(0, 0), visible=False, image_pos=None)
        self.frame_id += 1
        return f, gt
