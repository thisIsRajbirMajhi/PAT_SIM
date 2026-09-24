from ..common.enums import TrackingState

class TrackingStateMachine:
    def __init__(self, cfg):
        self.state = TrackingState.SEARCHING
        self.missed = 0
        self.locked_frames = 0
        self.candidate_frames = 0
        self.t_lost_frames = int(cfg["tracker"].get("lost_timeout_frames", 15))
        self.reacq_frames = int(cfg["tracker"].get("reacq_timeout_frames", 30))
        self.required_lock_frames = 5  # need N consecutive to declare LOCKED
        self.required_candidate = 3

    def update(self, detection_valid: bool, confidence: float) -> TrackingState:
        if detection_valid and confidence > 0.45:
            self.missed = 0
            self.candidate_frames += 1
            self.locked_frames += 1
            if self.state in (TrackingState.SEARCHING, TrackingState.CANDIDATE, TrackingState.TEMP_LOST, TrackingState.REACQUIRING):
                if self.candidate_frames >= self.required_candidate:
                    # go to acquiring then locked
                    if self.locked_frames >= self.required_lock_frames:
                        self.state = TrackingState.LOCKED
                    else:
                        self.state = TrackingState.ACQUIRING
                else:
                    self.state = TrackingState.CANDIDATE
            elif self.state == TrackingState.ACQUIRING:
                if self.locked_frames >= self.required_lock_frames:
                    self.state = TrackingState.LOCKED
            elif self.state == TrackingState.LOCKED:
                pass  # stay locked
            else:
                if self.locked_frames >= self.required_lock_frames:
                    self.state = TrackingState.LOCKED
        else:
            self.missed += 1
            self.candidate_frames = max(0, self.candidate_frames-1)
            self.locked_frames = max(0, self.locked_frames-1)
            if self.missed <= 3:
                # keep previous but if was locked go temp lost
                if self.state == TrackingState.LOCKED:
                    self.state = TrackingState.TEMP_LOST
            elif self.missed <= self.t_lost_frames:
                self.state = TrackingState.TEMP_LOST if self.state==TrackingState.LOCKED else TrackingState.REACQUIRING if self.missed>6 else self.state
                if self.state not in (TrackingState.TEMP_LOST, TrackingState.REACQUIRING):
                    self.state = TrackingState.TEMP_LOST
            elif self.missed <= self.reacq_frames:
                self.state = TrackingState.REACQUIRING
            else:
                self.state = TrackingState.SEARCHING
                if self.missed > self.reacq_frames + 30:
                    self.state = TrackingState.FAILED

        return self.state

    def reset(self):
        self.state = TrackingState.SEARCHING
        self.missed = 0
        self.locked_frames = 0
        self.candidate_frames = 0

    def is_locked(self):
        return self.state == TrackingState.LOCKED
