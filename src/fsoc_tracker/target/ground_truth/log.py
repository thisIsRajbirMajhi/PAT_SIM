"""Evaluator-only ground-truth bridge — canonical home (moved verbatim from simulation/ground_truth.py)."""
from dataclasses import dataclass


@dataclass
class GroundTruthFrame:
    frame_id: int
    world_pos: tuple
    image_pos: tuple | None
    visible: bool
    target_id: int = 0


class GroundTruthLog:
    """Ordered per-frame ground truth. target_id tracks multi-target beacons."""

    def __init__(self):
        self.frames = []

    def add(self, frame_id, world_pos, image_pos, target_id=0):
        self.frames.append(GroundTruthFrame(frame_id, world_pos, image_pos,
                                            image_pos is not None, target_id))

    def extend(self, frames):
        self.frames.extend(frames)

    def clear(self):
        self.frames.clear()

    reset = clear

    def __len__(self):
        return len(self.frames)

    def __iter__(self):
        return iter(self.frames)


__all__ = ["GroundTruthFrame", "GroundTruthLog"]
