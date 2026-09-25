"""
Identity state machine — Plan §7 / Prompt Phase 2 & 6.

Extends tracking/state_machine.py semantics to multi-track identity:

    SEARCHING
        ↓
    CANDIDATE_FOUND
        ↓
    IDENTITY_CHECKING
        ├── PRIMARY_CONFIRMED → TRACKING_PRIMARY (full PID)
        ├── DECOY_CONFIRMED   → REJECT_DECOY
        └── UNKNOWN           → MONITOR / SEARCH

Only PRIMARY_CONFIRMED may drive full PID; others use bounded search
or no motion.

This machine is per-track; the global mode is derived as:
 - if any PRIMARY_CONFIRMED → TRACKING_PRIMARY
 - elif any IDENTITY_CHECKING → SEARCHING/CHECKING
 - else SEARCHING
"""
from __future__ import annotations

from ..ai.types import IdentityState

class IdentityStateMachine:
    def __init__(self, cfg: dict):
        ai = cfg.get("ai", {}) if isinstance(cfg, dict) else {}
        thr = ai.get("thresholds", {}) if ai else {}
        self.primary_thr = float(thr.get("primary_threshold", 0.85))
        self.decoy_thr = float(thr.get("decoy_threshold", 0.85))
        self.confirm_frames = int(thr.get("confirmation_frames", 5))
        # UNKNOWN band knobs (defaults preserve the tuned 0.52/0.55 behavior)
        self.unknown_low = float(thr.get("unknown_low", 0.52))
        self.unknown_high = float(thr.get("unknown_high", 0.55))
        # per-track counters
        self._primary_streak: dict[int, int] = {}
        self._decoy_streak: dict[int, int] = {}
        self._state: dict[int, IdentityState] = {}

    def update(self, track_id: int, primary_p: float, decoy_p: float, unknown_p: float, has_observation: bool = True) -> IdentityState:
        """
        Update per-track identity state based on latest probabilities.
        Returns new IdentityState for this track.
        """
        # init
        if track_id not in self._state:
            self._state[track_id] = IdentityState.CANDIDATE_FOUND
            self._primary_streak[track_id] = 0
            self._decoy_streak[track_id] = 0

        if not has_observation:
            # missed frame → decay streaks but keep state, after timeout go TARGET_LOST
            self._primary_streak[track_id] = max(0, self._primary_streak[track_id] - 1)
            self._decoy_streak[track_id] = max(0, self._decoy_streak[track_id] - 1)
            cur = self._state[track_id]
            if cur == IdentityState.PRIMARY_CONFIRMED:
                # need several misses to lose primary
                # we keep PRIMARY_CONFIRMED for a grace period; caller prunes tracks separately
                return cur
            return cur

        # update streaks
        if primary_p >= self.primary_thr:
            self._primary_streak[track_id] += 1
        else:
            self._primary_streak[track_id] = 0

        if decoy_p >= self.decoy_thr:
            self._decoy_streak[track_id] += 1
        else:
            self._decoy_streak[track_id] = 0

        # decide
        if self._primary_streak[track_id] >= self.confirm_frames:
            self._state[track_id] = IdentityState.PRIMARY_CONFIRMED
        elif self._decoy_streak[track_id] >= self.confirm_frames:
            self._state[track_id] = IdentityState.DECOY_CONFIRMED
        elif max(primary_p, decoy_p, unknown_p) < self.unknown_low or unknown_p >= self.unknown_high:
            self._state[track_id] = IdentityState.UNKNOWN
        elif self._state[track_id] == IdentityState.PRIMARY_CONFIRMED:
            # demote stale primary when evidence drops (prevents locked-on ghost)
            if primary_p < self.primary_thr:
                self._state[track_id] = IdentityState.UNKNOWN if unknown_p >= 0.55 else IdentityState.IDENTITY_CHECKING
        elif self._state[track_id] == IdentityState.DECOY_CONFIRMED:
            # demote stale decoy only on strong contrary evidence
            if primary_p >= self.primary_thr and decoy_p < self.decoy_thr:
                self._state[track_id] = IdentityState.IDENTITY_CHECKING
        else:
            self._state[track_id] = IdentityState.IDENTITY_CHECKING

        return self._state[track_id]

    def get(self, track_id: int) -> IdentityState:
        return self._state.get(track_id, IdentityState.SEARCHING)

    def reset_track(self, track_id: int):
        self._primary_streak.pop(track_id, None)
        self._decoy_streak.pop(track_id, None)
        self._state.pop(track_id, None)

    def reset_all(self):
        self._primary_streak.clear()
        self._decoy_streak.clear()
        self._state.clear()
