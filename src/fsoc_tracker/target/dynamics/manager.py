"""Multi-target dynamics manager — owns trajectories + per-frame positions.

Extracted from simulation/world.py (Sr.8 multi-target logic). World keeps thin
mirrors (traj/trajectories/target_count/all_world_pos/world_pos) for backward compat;
canonical state lives here.
"""
import copy

import numpy as np

from .trajectories import make_trajectory, normalize_trajectory_type
from .visibility import is_hidden

# cfg keys whose change requires rebuilding trajectories (checked in update_config)
_DYNAMICS_KEYS = (
    "count", "trajectory", "speed_px_per_frame",
    "initial_pos", "initial_mode", "custom_trajectory_file",
    "custom_trajectory_path",
)


class TargetManager:
    def __init__(self, cfg, seed=42):
        self.cfg = cfg
        self.seed = seed
        self._build(cfg, seed, frame_id=0)

    def _build(self, cfg, seed, frame_id=0):
        self.target_count = int(cfg["target"].get("count", 1))
        self.trajectories = []
        # Primary target uses selected trajectory with main seed
        self.traj = make_trajectory(cfg, seed=seed)
        self.trajectories.append(self.traj)
        # Additional targets use independent random trajectories with offset seeds
        for i in range(1, self.target_count):
            distractor_cfg = copy.deepcopy(cfg)
            distractor_cfg["target"]["trajectory"] = "random"
            # vary distractor speed +-30% so they separate from the primary
            distractor_cfg["target"]["speed_px_per_frame"] = float(
                cfg["target"].get("speed_px_per_frame", 2.8)
            ) * (0.7 + 0.6 * ((i % 3) / 2))
            self.trajectories.append(make_trajectory(distractor_cfg, seed=seed + i * 1009))
        self.all_world_pos = [traj.step(frame_id) for traj in self.trajectories]
        self.world_pos = self.all_world_pos[0] if self.all_world_pos else self.traj.step(frame_id)

    def step(self, frame_id):
        self.all_world_pos = [traj.step(frame_id) for traj in self.trajectories]
        self.world_pos = self.all_world_pos[0] if self.all_world_pos else self.traj.step(frame_id)
        return self.world_pos

    def reset(self, seed=None, frame_id=0):
        if seed is not None:
            self.seed = seed
        for traj in self.trajectories:
            traj.reset()
        self._build(self.cfg, self.seed, frame_id=frame_id)

    def update_config(self, cfg, frame_id=0):
        """Rebuild trajectories if any dynamics key changed. Returns True if rebuilt."""
        old_t = self.cfg.get("target", {}) if isinstance(self.cfg, dict) else {}
        new_t = cfg.get("target", {}) if isinstance(cfg, dict) else {}
        self.cfg = cfg
        for k in _DYNAMICS_KEYS:
            if k == "trajectory":
                if normalize_trajectory_type(old_t.get(k)) != normalize_trajectory_type(new_t.get(k)):
                    break
            elif old_t.get(k) != new_t.get(k):
                break
        else:
            return False
        self._build(cfg, self.seed, frame_id=frame_id)
        return True

    def resolve_positions(self, world_pos, size):
        """Positions to draw: independent trajectories if available, else offset fallback."""
        count = int(self.cfg["target"].get("count", 1))
        if len(self.all_world_pos) >= count and (
            world_pos is self.world_pos
            or (isinstance(world_pos, (list, tuple)) and isinstance(self.world_pos, (list, tuple))
                and np.allclose(world_pos, self.world_pos))
        ):
            return self.all_world_pos[:count]
        if len(self.all_world_pos) == count:
            return list(self.all_world_pos)
        positions = []
        for idx in range(max(1, count)):
            off = (idx - (count - 1) / 2) * (size + 22) if count > 1 else 0
            positions.append((world_pos[0] + off, world_pos[1]))
        if positions and world_pos:
            positions[0] = world_pos
        return positions


def target_dynamics_changed(old_cfg, new_cfg):
    old_t = old_cfg.get("target", {}) if isinstance(old_cfg, dict) else {}
    new_t = new_cfg.get("target", {}) if isinstance(new_cfg, dict) else {}
    for k in _DYNAMICS_KEYS:
        if k == "trajectory":
            if normalize_trajectory_type(old_t.get(k)) != normalize_trajectory_type(new_t.get(k)):
                return True
        elif old_t.get(k) != new_t.get(k):
            return True
    return False


__all__ = ["TargetManager", "target_dynamics_changed", "is_hidden"]
