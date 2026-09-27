"""Evaluator-only ground-truth bridge — canonical home (moved verbatim from simulation/ground_truth.py)."""
from dataclasses import dataclass


@dataclass
class GroundTruthFrame:
    frame_id: int
    world_pos: tuple
    image_pos: tuple | None
    visible: bool


class GroundTruthLog:
    def __init__(self):
        self.frames = []

    def add(self, frame_id, world_pos, image_pos):
        self.frames.append(GroundTruthFrame(frame_id, world_pos, image_pos, image_pos is not None))

    def clear(self):
        self.frames.clear()


__all__ = ["GroundTruthFrame", "GroundTruthLog"]
