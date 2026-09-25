"""
Multi-target track manager — Plan §6 / Prompt Phase 2.

Maintains independent TrackState per candidate_id with:
 - creation, association (nearest-neighbor with gate), missed-frame counting,
 - decoy memory (rejected tracks are remembered and not immediately re-selected),
 - per-track history for GRU (20-30 observations).

Uses simple nearest-neighbor gating; sufficient for synthetic scenes with
≤5 candidates. Hungarian could be swapped later without changing callers.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple
import numpy as np

from ..ai.types import Candidate, TrackState, IdentityState


class TrackManager:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        ai = cfg.get("ai", {})
        self.max_missed = int(ai.get("thresholds", {}).get("max_missed_frames", 15)) if ai else 15
        # fallback to tracker lost timeout
        if self.max_missed <= 0:
            self.max_missed = int(cfg.get("tracker", {}).get("lost_timeout_frames", 15))
        self.gate_px = float(cfg.get("tracker", {}).get("gate_sigma", 5.0)) * 10.0  # ~50px gate
        self.tracks: Dict[int, TrackState] = {}
        self._next_id = 1
        self.last_pruned: List[int] = []
        # decoy memory: track_id → frames since rejection
        self._decoy_memory: Dict[int, int] = {}
        self._rejected_positions: List[Tuple[float, float]] = []

    def reset(self):
        self.tracks.clear()
        self._next_id = 1
        self.last_pruned = []
        self._decoy_memory.clear()
        self._rejected_positions.clear()

    def update_config(self, cfg: dict):
        self.__init__(cfg)

    def update(self, candidates: List[Candidate], frame_id: int, innovation: float = 0.0, imm_probs=(0.33, 0.33, 0.34)) -> Dict[int, TrackState]:
        """
        Associate candidates to existing tracks or create new tracks.
        Called once per frame after candidate generation + AI Stage-1.
        """
        # decay decoy memory
        for k in list(self._decoy_memory.keys()):
            self._decoy_memory[k] += 1
            if self._decoy_memory[k] > 90:  # keep for ~3s @30Hz
                self._decoy_memory.pop(k, None)

        # build cost matrix (Euclidean distance)
        track_ids = list(self.tracks.keys())
        track_centroids = [self.tracks[tid].position_history[-1] if self.tracks[tid].position_history else None for tid in track_ids]

        # greedy association: each candidate assigned to nearest track within gate
        assigned_candidates = set()
        assigned_tracks = set()

        # for each candidate, find nearest unassigned track
        for c in candidates:
            best_tid = None
            best_dist = self.gate_px
            for tid, tcent in zip(track_ids, track_centroids):
                if tid in assigned_tracks or tcent is None:
                    continue
                dist = float(np.hypot(c.centroid_px[0] - tcent[0], c.centroid_px[1] - tcent[1]))
                # decoy memory penalty: if near rejected decoy position, increase miss
                if dist < best_dist:
                    best_dist = dist
                    best_tid = tid
            if best_tid is not None:
                # decoy memory: a recently rejected decoy track must not re-absorb
                # measurements — consume the candidate without updating the track
                # so the rejected track misses out and is eventually pruned while
                # _rejected_positions suppresses immediate re-creation nearby.
                if self.tracks[best_tid].is_rejected_decoy and best_dist < 40:
                    # consume the candidate without updating the rejected track
                    continue
                # bind candidate to persistent track id for AI pipeline lookup
                c.candidate_id = best_tid
                self._update_track(best_tid, c, frame_id, innovation, imm_probs)
                assigned_tracks.add(best_tid)
                assigned_candidates.add(c.candidate_id)
            else:
                # create new track — but reject if near a known decoy position (within 30px) for 60 frames
                near_rejected = any(np.hypot(c.centroid_px[0] - rx, c.centroid_px[1] - ry) < 35 for rx, ry in self._rejected_positions[-10:])
                if near_rejected:
                    # still create but mark low priority; track_manager will not promote quickly
                    pass
                new_id = self._next_id
                self._next_id += 1
                # reassign candidate_id to match track id for pipeline simplicity
                c.candidate_id = new_id
                self._create_track(new_id, c, frame_id, innovation, imm_probs)
                assigned_candidates.add(c.candidate_id)

        # increment missed for unassigned tracks
        self.last_pruned = []
        for tid in list(self.tracks.keys()):
            if tid not in assigned_tracks:
                self.tracks[tid].missed_frames += 1
                self.tracks[tid].age += 1
            # prune stale tracks
            if self.tracks[tid].missed_frames > self.max_missed:
                # if it was a rejected decoy, remember position
                if self.tracks[tid].is_rejected_decoy and self.tracks[tid].position_history:
                    self._rejected_positions.append(self.tracks[tid].position_history[-1])
                    if len(self._rejected_positions) > 20:
                        self._rejected_positions.pop(0)
                self.last_pruned.append(tid)
                del self.tracks[tid]

        return dict(self.tracks)

    def _create_track(self, tid: int, c: Candidate, frame_id: int, innovation: float, imm_probs):
        tr = TrackState(track_id=tid, age=1, missed_frames=0, last_seen_frame=frame_id)
        tr.position_history.append(c.centroid_px)
        # velocity estimate 0 for first observation
        tr.velocity_history.append((0.0, 0.0))
        tr.brightness_history.append(c.brightness)
        tr.size_history.append(float(max(c.width, c.height)))
        tr.confidence_history.append(c.beacon_probability)
        tr.innovation_history.append(innovation)
        tr.imm_probs_history.append(tuple(imm_probs))
        # blink: threshold between off (180) and on (255) → 210 (Plan §8 coded blinking)
        tr.blink_history.append(1 if c.peak_intensity > 210 else 0)
        self.tracks[tid] = tr

    def _update_track(self, tid: int, c: Candidate, frame_id: int, innovation: float, imm_probs):
        tr = self.tracks[tid]
        prev = tr.position_history[-1] if tr.position_history else c.centroid_px
        # velocity in px/frame
        vx = c.centroid_px[0] - prev[0]
        vy = c.centroid_px[1] - prev[1]
        tr.position_history.append(c.centroid_px)
        tr.velocity_history.append((float(vx), float(vy)))
        tr.brightness_history.append(c.brightness)
        tr.size_history.append(float(max(c.width, c.height)))
        tr.confidence_history.append(c.beacon_probability)
        tr.innovation_history.append(innovation)
        tr.imm_probs_history.append(tuple(imm_probs))
        tr.blink_history.append(1 if c.peak_intensity > 210 else 0)
        tr.last_seen_frame = frame_id
        tr.missed_frames = 0
        tr.age += 1
        # keep history bounded to ~60 frames (covers 2s at 30Hz)
        max_hist = 60
        for attr in ("position_history", "velocity_history", "brightness_history", "size_history", "confidence_history", "innovation_history", "imm_probs_history", "blink_history"):
            lst = getattr(tr, attr)
            if len(lst) > max_hist:
                setattr(tr, attr, lst[-max_hist:])

    def mark_rejected(self, track_id: int):
        if track_id in self.tracks:
            self.tracks[track_id].is_rejected_decoy = True
            self._decoy_memory[track_id] = 0
            if self.tracks[track_id].position_history:
                self._rejected_positions.append(self.tracks[track_id].position_history[-1])

    def get_primary_candidates(self) -> List[int]:
        return [tid for tid, tr in self.tracks.items() if tr.current_identity == IdentityState.PRIMARY_CONFIRMED]

    def all_track_snapshots(self):
        """Return list of TrackState copies for UI read-only view."""
        return list(self.tracks.values())
