from ..environment import (
    build_environment_base_with_mask,
    apply_twinkle,
    environment_changed,
)
from ..target import (
    BeaconRenderer,
    TargetManager,
    get_user_polygon,
    is_hidden,
)


class World:
    """Scene composer: static environment base + target/beacon overlay.

    Ownership split: background construction delegates to environment/;
    all target dynamics/appearance/visibility delegate to target/.
    This class keeps thin mirrors (traj/trajectories/target_*/world_pos/...)
    for backward compatibility — canonical state lives in TargetManager +
    BeaconRenderer.
    """

    def __init__(self, cfg, seed=42):
        self.cfg = cfg
        self.seed = seed
        w = cfg["world"]["width"]
        h = cfg["world"]["height"]
        self.w = w; self.h = h
        self.bg = int(cfg["world"].get("background", 18))
        # build base with all environment systems (+ star mask for twinkle)
        self.base, self.star_mask = self._build_base(cfg, seed)
        # target dynamics + appearance (canonical in target/)
        self._manager = TargetManager(cfg, seed=seed)
        self._renderer = BeaconRenderer(cfg)
        self._sync_target_mirrors()
        self.frame_id = 0
        self.all_world_pos = [traj.step(0) for traj in self.trajectories]
        self.world_pos = self.all_world_pos[0] if self.all_world_pos else self.traj.step(0)

    def _sync_target_mirrors(self):
        m = self._manager
        self.target_count = m.target_count
        self.trajectories = m.trajectories
        self.traj = m.traj
        self.all_world_pos = list(m.all_world_pos)
        self.world_pos = m.world_pos
        r = self._renderer
        self.target_size = r.size
        self.target_intensity = r.intensity
        self.target_shape = r.shape
        self.custom_polygon = r.custom_polygon

    # ---------- base building (delegates to environment/ module) ----------
    def _build_base(self, cfg, seed):
        return build_environment_base_with_mask(cfg, seed)

    def _get_user_polygon(self, cx, cy, half):
        """Return polygon points for user-defined shape. Uses custom_polygon if provided, else default 5-point star."""
        return get_user_polygon(cx, cy, half, self.custom_polygon)

    def update_config(self, cfg, seed=None):
        """Rebuild base only if environment/world relevant fields changed; handle multi-target and shape."""
        # check if rebuild needed (delegates to environment module)
        rebuild = environment_changed(self.cfg, cfg) or (seed is not None and seed != self.seed)
        self.cfg = cfg
        self.w, self.h = cfg["world"]["width"], cfg["world"]["height"]
        self.bg = int(cfg["world"].get("background", 18))
        if seed is not None:
            self.seed = seed
        if rebuild:
            self.base, self.star_mask = self._build_base(cfg, self.seed)
        # target dynamics (rebuilds trajectories if count/shape/trajectory changed)
        self._manager.update_config(cfg, frame_id=self.frame_id)
        # target appearance (size/intensity/shape/polygon live)
        self._renderer.update_config(cfg)
        self._sync_target_mirrors()
        self.all_world_pos = [traj.step(self.frame_id) for traj in self.trajectories]

    def step(self):
        # Update all targets independently (Sr.8 multi-target, canonical in TargetManager)
        self.world_pos = self._manager.step(self.frame_id)
        self.all_world_pos = list(self._manager.all_world_pos)
        self.trajectories = self._manager.trajectories
        self.traj = self._manager.traj
        self.frame_id += 1
        return self.world_pos

    def render_world(self, world_pos=None):
        if world_pos is None:
            world_pos = self.world_pos
        img = self.base.copy()

        # P11 visibility schedule: hide beacon during hidden intervals (forces loss/re-acq)
        if is_hidden(self.frame_id, self.cfg):
            return img  # no beacon drawn

        env = self.cfg.get("environment", {})
        if env.get("stars_enabled") and env.get("stars_twinkle"):
            amount = int(env.get("stars_twinkle_amount", 6))
            img = apply_twinkle(img, self.frame_id, amount=amount, mask=self.star_mask)

        # draw beacon(s) — support count (independent trajectories Sr.8) & shape Sr.9 (including user-defined)
        positions = self._manager.resolve_positions(world_pos, self.target_size)
        # keep mirrors consistent when primary rendering path used
        if world_pos == self.world_pos:
            self.all_world_pos = list(self._manager.all_world_pos)
        return self._renderer.draw(img, positions, self.w, self.h)

    def reset(self, seed=None):
        if seed is not None:
            self.seed = seed
        self.frame_id = 0
        self._manager = TargetManager(self.cfg, seed=self.seed)
        self._renderer.update_config(self.cfg)
        self._sync_target_mirrors()
        self.all_world_pos = [traj.step(0) for traj in self.trajectories]
        self.world_pos = self.all_world_pos[0] if self.all_world_pos else self.traj.step(0)
