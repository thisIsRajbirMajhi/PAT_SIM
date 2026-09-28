"""Display status + target telemetry derived from real tracking conditions.

Single source of truth for every overlay layer (camera banner, target tag,
world view, bottom telemetry). The renderer must consume :class:`DisplayState`
and :class:`TrackTelemetry` — never re-derive state from unrelated variables.

States (no IDENTIFIED: this pipeline has no classifier, so classification is
never claimed):
    INITIALIZING      run just started, models warming up
    SCANNING          actively sweeping, no track held
    TARGET_DETECTED   first valid detection of a possible target
    VERIFYING         consecutive detections building (candidate gate)
    ACQUIRING         tracker initializing a stable track
    TRACKING          locked target, visible, quality nominal
    OFF_SCREEN        locked target geometrically outside the camera FOV
                      while the IMM prediction is still fresh
    DEGRADED          locked target, measurement quality deteriorated
                      (high innovation sustained, or flapping detections)
    LOST              tracker can no longer maintain the target
    REACQUIRING       actively attempting recovery after a loss

Hysteresis everywhere a one-frame glitch could flip the banner: loss needs
several consecutive misses, FOV transitions need confirmation, degradation
needs sustained evidence and sustained recovery.
"""
from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple


class DisplayStatus(str, Enum):
    INITIALIZING = "INITIALIZING"
    SCANNING = "SCANNING"
    TARGET_DETECTED = "TARGET_DETECTED"
    VERIFYING = "VERIFYING"
    ACQUIRING = "ACQUIRING"
    TRACKING = "TRACKING"
    OFF_SCREEN = "OFF_SCREEN"
    DEGRADED = "DEGRADED"
    LOST = "LOST"
    REACQUIRING = "REACQUIRING"


# label, stroke color, semantic role. Crosshair marks stay white; only the
# pill/box strokes carry these colors.
STATUS_META = {
    DisplayStatus.INITIALIZING: ("INITIALIZING", "#9AA4B2", "neutral"),
    DisplayStatus.SCANNING: ("SCANNING", "#38BDF8", "active"),
    DisplayStatus.TARGET_DETECTED: ("TARGET DETECTED", "#FACC15", "attention"),
    DisplayStatus.VERIFYING: ("VERIFYING TARGET", "#F59E0B", "attention"),
    DisplayStatus.ACQUIRING: ("ACQUIRING TRACK", "#FB923C", "active"),
    DisplayStatus.TRACKING: ("TRACKING", "#60A5FA", "stable"),
    DisplayStatus.OFF_SCREEN: ("TRACKING \u2014 OFF-SCREEN", "#22D3EE", "informational"),
    DisplayStatus.DEGRADED: ("TRACK DEGRADED", "#EA580C", "warning"),
    DisplayStatus.LOST: ("TARGET LOST", "#EF4444", "error"),
    DisplayStatus.REACQUIRING: ("REACQUIRING", "#A78BFA", "warning"),
}


@dataclass
class DisplayState:
    """System-level overlay state for the current tick."""
    status: DisplayStatus
    label: str = ""
    color_hex: str = "#9AA4B2"
    show_no_target: bool = False  # secondary "NO TARGET" chip (scanning, empty frame)

    def __post_init__(self):
        meta_label, meta_color, _ = STATUS_META[self.status]
        if not self.label:
            self.label = meta_label
        if self.color_hex in ("", "#9AA4B2"):
            self.color_hex = meta_color


@dataclass
class TrackTelemetry:
    """Per-target telemetry. Every field is either a real measurement or None.

    det_conf: last valid DETECTOR confidence (0..1), never synthesized.
    track_age_s: seconds since the current track locked.
    last_detect_age_s: seconds since the last valid detection.
    fov: "IN FOV" | "OFF-SCREEN" | None (unknown, e.g. video with no geometry).
    offset_px: current-frame detection offset from boresight in pixels.
    predicted: estimate is currently coasting on IMM prediction (no measurement).
    pred_fresh: coasting prediction still within its validity budget.
    """
    track_label: str = "\u2014"  # "TGT-01" once an object is detected this run
    det_conf: Optional[float] = None
    track_age_s: Optional[float] = None
    last_detect_age_s: Optional[float] = None
    fov: Optional[str] = None
    offset_px: Optional[float] = None
    predicted: bool = False
    pred_fresh: bool = False


class DisplayTracker:
    """Computes (DisplayState, TrackTelemetry) from real backend conditions.

    Inputs per tick are backend facts: detector output, tracker state-machine
    counters, IMM innovation, FOV geometry, timestamps. All debounce counters
    live here so transitions are deterministic and testable.
    """

    def __init__(self, cfg=None):
        tr = (cfg or {}).get("tracker", {}) if isinstance(cfg, dict) else {}
        self.req_cand = 3
        self.req_lock = 5
        self.init_frames = 5
        self.lost_confirm = 3       # consecutive misses before LOST
        self.fov_confirm = 2        # consecutive ticks to enter/leave OFF-SCREEN
        self.nis_bad = 3.0          # sustained innovation above this => degraded
        self.nis_ok = 1.5           # sustained below this => recovered
        self.nis_bad_need = 5
        self.nis_ok_need = 10
        self.miss_window = 20       # trailing window for flapping-detection
        self.miss_ratio_bad = 6     # misses inside window => degraded
        self.offscreen_ttl = int(tr.get("reacq_timeout_frames", 30))
        self.give_up_misses = 60    # latched REACQUIRING decays to SCANNING past this
        self.det_gate = 0.45        # mirrors TrackingStateMachine confidence gate
        self.reset()

    def reset(self):
        self._miss_hist = deque(maxlen=self.miss_window)
        self._missed = 0
        self._consec_valid = 0
        self._nis_bad = 0
        self._nis_ok = 0
        self._fov_bad = 0
        self._fov_ok = 0
        self._offscreen = False
        self._latched = False       # a track locked at least once this run
        self._lock_start_t = None
        self._prev_sm_locked = False
        self._last_valid_t = None
        self._last_conf = None
        self._track_label = "\u2014"
        self._last_hard = DisplayStatus.SCANNING  # coast target for 1-2 frame gaps

    def update(self, frame_index, timestamp, det_valid, det_conf, sm_state,
               cand_frames, locked_frames, innovation, in_fov,
               est_pos=None):
        # type: (...) -> Tuple[DisplayState, TrackTelemetry]
        """One tick. in_fov: True/False from FOV geometry, or None if unknown."""
        det_valid = bool(det_valid)
        try:
            conf = float(det_conf) if det_valid else 0.0
        except Exception:
            conf = 0.0
        try:
            nis = float(innovation or 0.0)
        except Exception:
            nis = 0.0
        try:
            missed = int(getattr(self, "_missed", 0))
        except Exception:
            missed = 0
        # consecutive-miss counter maintained here (deterministic, testable)
        # consecutive-miss counter mirrors the state-machine gate: only a
        # strong (above-gate) detection resets it; weak/invalid frames age it.
        if det_valid and conf > self.det_gate:
            strong = True
            missed = 0
        elif det_valid:
            strong = False
            missed = getattr(self, "_missed", 0) + 1
        else:
            strong = False
            missed = getattr(self, "_missed", 0) + 1
        self._missed = missed
        self._miss_hist.append(0 if det_valid else 1)

        sm_locked = (sm_state == "LOCKED")
        if sm_locked and not self._prev_sm_locked:
            self._lock_start_t = float(timestamp)
            self._latched = True
        self._prev_sm_locked = sm_locked

        if det_valid:
            self._last_valid_t = float(timestamp)
            self._last_conf = conf
            if self._track_label == "\u2014":
                self._track_label = "TGT-01"
            self._fov_ok += 1
            self._fov_bad = 0
            if self._offscreen and self._fov_ok >= self.fov_confirm:
                self._offscreen = False
            # sustained clean run = healthy: restart the flapping window so a
            # recovered track is not penalized forever for an old outage
            self._consec_valid = getattr(self, "_consec_valid", 0) + 1
            if self._consec_valid >= 5:
                self._miss_hist.clear()
        else:
            self._fov_ok = 0
            self._consec_valid = 0

        # FOV confirmation counting (only meaningful while invalid; a valid
        # detection is, by construction, inside the frame)
        if not det_valid and in_fov is False:
            self._fov_bad += 1
        elif not det_valid and in_fov is True:
            self._fov_bad = 0

        # degradation evidence (only evaluated on locked tracks)
        degraded_vote = False
        if sm_locked and det_valid:
            if nis > self.nis_bad:
                self._nis_bad += 1
                self._nis_ok = 0
            elif nis < self.nis_ok:
                self._nis_ok += 1
                if self._nis_ok >= self.nis_ok_need:
                    self._nis_bad = 0
            else:
                self._nis_ok = 0  # ambiguous middle band: neither votes
            recent_misses = sum(self._miss_hist)
            if self._nis_bad >= self.nis_bad_need or recent_misses >= self.miss_ratio_bad:
                degraded_vote = True
        elif not det_valid:
            self._nis_ok = 0

        status, show_chip = self._resolve(
            frame_index, det_valid, strong, sm_state, cand_frames,
            locked_frames, missed, in_fov, degraded_vote)

        if status in (DisplayStatus.TRACKING, DisplayStatus.DEGRADED,
                      DisplayStatus.OFF_SCREEN, DisplayStatus.LOST,
                      DisplayStatus.REACQUIRING):
            self._last_hard = status

        state = DisplayState(status=status, show_no_target=show_chip)

        tele = TrackTelemetry(
            track_label=self._track_label,
            det_conf=self._last_conf,
            track_age_s=(float(timestamp) - self._lock_start_t
                         if self._lock_start_t is not None else None),
            last_detect_age_s=(float(timestamp) - self._last_valid_t
                               if self._last_valid_t is not None else None),
            fov=("IN FOV" if in_fov is True
                 else ("OFF-SCREEN" if in_fov is False else None)),
            offset_px=None,  # filled by caller (needs frame centre)
            predicted=(not det_valid and est_pos is not None),
            pred_fresh=(missed <= self.offscreen_ttl),
        )
        return state, tele

    # ------------------------------------------------------------------
    def _resolve(self, frame_index, det_valid, strong, sm_state, cand,
                 locked, missed, in_fov, degraded_vote):
        try:
            fi = int(frame_index)
        except Exception:
            fi = 10 ** 9
        if fi < self.init_frames:
            return DisplayStatus.INITIALIZING, False
        if sm_state == "FAILED":
            return DisplayStatus.SCANNING, False
        if strong:
            if sm_state == "LOCKED":
                if degraded_vote:
                    return DisplayStatus.DEGRADED, False
                return DisplayStatus.TRACKING, False
            if cand <= 1:
                return DisplayStatus.TARGET_DETECTED, False
            if cand < self.req_cand:
                return DisplayStatus.VERIFYING, False
            return DisplayStatus.ACQUIRING, False
        if det_valid:
            # weak detection below the state-machine gate: possible object,
            # unverified — unless already on a locked track.
            if sm_state == "LOCKED":
                return (DisplayStatus.DEGRADED if degraded_vote
                        else DisplayStatus.TRACKING), False
            return DisplayStatus.TARGET_DETECTED, False
        # ---- no detection this frame ----
        off = (in_fov is False)
        if off and missed <= self.offscreen_ttl and (
                self._latched or sm_state in ("LOCKED", "TEMP_LOST", "REACQUIRING")):
            if self._fov_bad >= self.fov_confirm or self._offscreen:
                self._offscreen = True
                return DisplayStatus.OFF_SCREEN, False
            if self._offscreen:
                return DisplayStatus.OFF_SCREEN, False
        else:
            self._offscreen = False
        if off and missed > self.offscreen_ttl:
            return DisplayStatus.LOST, False  # prediction expired
        if sm_state in ("LOCKED", "TEMP_LOST"):
            # hold the hard track through 1-2 frame gaps (anti-flicker);
            # confirm the loss only on sustained absence
            if missed < self.lost_confirm and self._last_hard in (
                    DisplayStatus.TRACKING, DisplayStatus.DEGRADED,
                    DisplayStatus.OFF_SCREEN):
                return self._last_hard, False
            return DisplayStatus.LOST, False
        if sm_state == "REACQUIRING":
            return DisplayStatus.REACQUIRING, False
        if sm_state in ("SEARCHING",):
            if self._latched and missed <= self.give_up_misses:
                return DisplayStatus.REACQUIRING, False
            return DisplayStatus.SCANNING, True
        if sm_state in ("CANDIDATE", "ACQUIRING"):
            return DisplayStatus.SCANNING, True
        return DisplayStatus.SCANNING, True
