class PIDController:
    def __init__(self, kp=1.2, ki=0.05, kd=0.15, deadzone=2.0, integral_limit=8.0, derivative_filter=0.2):
        self.kp = kp; self.ki = ki; self.kd = kd
        self.deadzone = deadzone
        self.integral_limit = integral_limit
        self.deriv_alpha = derivative_filter
        self.integral = 0.0
        self.prev_error = 0.0
        self.prev_deriv = 0.0

    def reset(self):
        self.integral = 0.0; self.prev_error = 0.0; self.prev_deriv = 0.0

    def step(self, error_deg: float, dt: float) -> float:
        # deadzone in degrees? Convert from px deadzone. For now deadzone is in px but we get deg error.
        # We'll treat deadzone as degrees as well (approx). Let deadzone_deg = deadzone_px * FOV/W approx 0.01 deg per px.
        # To keep simple, if |error| < 0.015 deg (~2px) return 0
        dz = 0.015 * (self.deadzone/2.0)  # scale
        if abs(error_deg) < dz:
            # still update integral slightly? freeze
            return 0.0
        p = self.kp * error_deg
        self.integral += error_deg * dt
        # clamp integral
        if self.integral > self.integral_limit: self.integral = self.integral_limit
        if self.integral < -self.integral_limit: self.integral = -self.integral_limit
        i = self.ki * self.integral
        deriv = (error_deg - self.prev_error) / max(dt, 1e-6)
        # filter
        deriv_f = self.deriv_alpha * deriv + (1 - self.deriv_alpha) * self.prev_deriv
        d = self.kd * deriv_f
        self.prev_error = error_deg
        self.prev_deriv = deriv_f
        return p + i + d

    def freeze_integral(self):
        pass

    def update_gains(self, kp=None, ki=None, kd=None, deadzone=None, integral_limit=None):
        if kp is not None: self.kp = kp
        if ki is not None: self.ki = ki
        if kd is not None: self.kd = kd
        if deadzone is not None: self.deadzone = deadzone
        if integral_limit is not None: self.integral_limit = integral_limit
