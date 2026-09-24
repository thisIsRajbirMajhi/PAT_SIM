import cv2, time
import numpy as np
from .base import FrameSource
from ..common.types import Frame, GroundTruth

class VideoSource(FrameSource):
    def __init__(self, path: str, target_fps: float = 30.0):
        self.path = path
        self.cap = cv2.VideoCapture(path)
        if not self.cap.isOpened():
            raise FileNotFoundError(f"Cannot open video: {path}")
        self._fps = self.cap.get(cv2.CAP_PROP_FPS) or target_fps
        self._w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self._h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.frame_id = 0

    @property
    def fps(self): return self._fps
    @property
    def resolution(self): return (self._w, self._h)

    def is_opened(self): return self.cap.isOpened()
    def release(self): self.cap.release()

    def reset(self):
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        self.frame_id = 0

    def read(self):
        ret, frame = self.cap.read()
        if not ret:
            return None, None
        # convert to grayscale (spec: monochrome)
        if len(frame.shape)==3:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        else:
            gray = frame
        f = Frame(image=gray, frame_id=self.frame_id, timestamp=self.frame_id/self._fps, source_name="video")
        # no ground truth for external video - evaluator compares externally
        gt = GroundTruth(world_pos=(0,0), visible=False, image_pos=None)
        self.frame_id += 1
        return f, gt
