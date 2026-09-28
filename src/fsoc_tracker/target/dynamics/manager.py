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
    "count", "trajectory", "trajectories", "distractor_trajectory",
    "speed_px_per_frame", "speeds",
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
        import copy as _copy
        tgt0 = cfg.get("target", {}) if isinstance(cfg, dict) else {}
        per0 = tgt0.get("trajectories")
        # Primary target: trajectories[0] when an explicit per-target list is
        # given, else the single `trajectory` field.
        if isinstance(per0, (list, tuple)) and len(per0) >= 1 and per0[0]:
            primary_cfg = _copy.deepcopy(cfg)
            primary_cfg["target"]["trajectory"] = per0[0]
            if isinstance(tgt0.get("speeds"), (list, tuple)) and len(tgt0["speeds"]) >= 1 \
                    and tgt0["speeds"][0] is not None:
                primary_cfg["target"]["speed_px_per_frame"] = float(tgt0["speeds"][0])
            self.traj = make_trajectory(primary_cfg, seed=seed)
        else:
            self.traj = make_trajectory(cfg, seed=seed)
        self.trajectories.append(self.traj)
        # Additional targets: independent trajectories.
        # Priority: explicit per-target `trajectories` list > `distractor_trajectory`
        # > follow the primary trajectory type (with offset seeds/positions so
        # they separate instead of overlapping).
        import copy as _copy
        tgt = cfg.get("target", {}) if isinstance(cfg, dict) else {}
        per_list = tgt.get("trajectories")
        dist_traj = tgt.get("distractor_trajectory")
        speeds = tgt.get("speeds")
        base_speed = float(tgt.get("speed_px_per_frame", 2.8))
        world_w = cfg.get("world", {}).get("width", 2000)
        world_h = cfg.get("world", {}).get("height", 2000)
        for i in range(1, self.target_count):
            distractor_cfg = _copy.deepcopy(cfg)
            if isinstance(per_list, (list, tuple)) and i < len(per_list) and per_list[i]:
                distractor_cfg["target"]["trajectory"] = per_list[i]
            elif dist_traj:
                distractor_cfg["target"]["trajectory"] = dist_traj
            # else: keep primary trajectory (independent instance below)
            if isinstance(speeds, (list, tuple)) and i < len(speeds) and speeds[i] is not None:
                distractor_cfg["target"]["speed_px_per_frame"] = float(speeds[i])
            elif not (isinstance(per_list, (list, tuple)) and i < len(per_list) and per_list[i]) \
                    and not dist_traj and not (isinstance(speeds, (list, tuple)) and i < len(speeds)):
                # default separation when following primary: vary speed +-30%
                distractor_cfg["target"]["speed_px_per_frame"] = base_speed * (0.7 + 0.6 * ((i % 3) / 2))
            # Separate fixed starts so same-family targets do not overlap: offset
            # by a deterministic fraction of the world size when the primary uses
            # a fixed (centre/user-defined) start.
            try:
                mode = str(tgt.get("initial_mode", "random")).lower()
            except Exception:
                mode = "random"
            if mode in ("centre", "center", "user-defined", "user_defined"):
                try:
                    base_init = tgt.get("initial_pos")
                    if base_init is None:
                        base_init = [world_w // 2, world_h // 2]
                    ox = int((world_w * (0.18 * i)) % max(world_w - 100, 1))
                    oy = int((world_h * (0.13 * i)) % max(world_h - 100, 1))
                    distractor_cfg["target"]["initial_pos"] = [
                        int((int(base_init[0]) + ox - world_w // 4) % max(world_w - 100, 1)) + 50,
                        int((int(base_init[1]) + oy - world_h // 4) % max(world_h - 100, 1)) + 50,
                    ]
                    distractor_cfg["target"]["initial_mode"] = "user-defined"
                except Exception:
                    pass
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
            elif k in ("trajectories", "distractor_trajectory"):
                old_n = [normalize_trajectory_type(x) if x else x for x in (old_t.get(k) or [])] \
                    if isinstance(old_t.get(k), (list, tuple)) else (
                        normalize_trajectory_type(old_t.get(k)) if old_t.get(k) else old_t.get(k))
                new_n = [normalize_trajectory_type(x) if x else x for x in (new_t.get(k) or [])] \
                    if isinstance(new_t.get(k), (list, tuple)) else (
                        normalize_trajectory_type(new_t.get(k)) if new_t.get(k) else new_t.get(k))
                if old_n != new_n:
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
        elif k in ("trajectories", "distractor_trajectory"):
            def _norm(v):
                if isinstance(v, (list, tuple)):
                    return [normalize_trajectory_type(x) if x else x for x in v]
                return normalize_trajectory_type(v) if v else v
            if _norm(old_t.get(k)) != _norm(new_t.get(k)):
                return True
        elif old_t.get(k) != new_t.get(k):
            return True
    return False


__all__ = ["TargetManager", "target_dynamics_changed", "is_hidden"]
