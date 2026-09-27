"""Multi-target dynamics manager — owns trajectories + per-frame positions.

Extracted from simulation/world.py (Sr.8 multi-target logic). World keeps thin
mirrors (traj/trajectories/target_count/all_world_pos/world_pos) for backward compat;
canonical state lives here.
"""
from .trajectories import make_trajectory
from .visibility import is_hidden


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
            distractor_cfg = cfg.copy()
            distractor_cfg["target"] = cfg["target"].copy()
            distractor_cfg["target"]["trajectory"] = "random"
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
        self._build(self.cfg, self.seed, frame_id=frame_id)

    def update_config(self, cfg, frame_id=0):
        """Rebuild trajectories if count/shape/trajectory changed. Returns True if rebuilt."""
        old_count = int(self.cfg.get("target", {}).get("count", 1))
        new_count = int(cfg.get("target", {}).get("count", 1))
        old_shape = self.cfg.get("target", {}).get("shape", "square")
        new_shape = cfg.get("target", {}).get("shape", "square")
        old_traj = self.cfg.get("target", {}).get("trajectory")
        new_traj = cfg.get("target", {}).get("trajectory")
        self.cfg = cfg
        if (old_count != new_count) or (old_shape != new_shape) or (old_traj != new_traj):
            self._build(cfg, self.seed, frame_id=frame_id)
            return True
        return False

    def resolve_positions(self, world_pos, size):
        """Positions to draw: independent trajectories if available, else offset fallback."""
        count = int(self.cfg["target"].get("count", 1))
        if len(self.all_world_pos) >= count and world_pos == self.world_pos:
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
    old_t = old_cfg.get("target", {})
    new_t = new_cfg.get("target", {})
    return (
        int(old_t.get("count", 1)) != int(new_t.get("count", 1))
        or old_t.get("shape", "square") != new_t.get("shape", "square")
        or old_t.get("trajectory") != new_t.get("trajectory")
    )


__all__ = ["TargetManager", "target_dynamics_changed", "is_hidden"]
