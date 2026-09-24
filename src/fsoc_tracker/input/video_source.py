import cv2, time
import numpy as np
from .base import FrameSource
from ..common.types import Frame, GroundTruth

class VideoSource(FrameSource):
    """
    External video adapter for Benchmark Performance-2.
    - Preserves frame order (sequential read, no reordering or skipping)
    - Handles any resolution natively (no silent resize that would change error scale)
    - Reports original FPS (from file) and lets caller measure actual processing FPS
    - Supports image centre calibration (pixel offset) for videos where principal point != frame centre
    - Clearly bypasses PTZ: is_ptz_enabled == False, no camera commands are applied
    """
    def __init__(self, path: str, target_fps: float = 30.0, centre_offset_x: float = 0.0, centre_offset_y: float = 0.0):
        self.path = path
        self.cap = cv2.VideoCapture(path)
        if not self.cap.isOpened():
            raise FileNotFoundError(f"Cannot open video: {path}")
        # Original FPS from file; fallback to target_fps if unavailable (some codecs report 0)
        raw_fps = self.cap.get(cv2.CAP_PROP_FPS)
        self._fps = float(raw_fps) if raw_fps and 1 <= raw_fps <= 240 else float(target_fps)
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
        # No ground truth for external video — evaluator compares externally against predefined annotations
        gt = GroundTruth(world_pos=(0, 0), visible=False, image_pos=None)
        self.frame_id += 1
        return f, gt
