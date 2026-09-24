class PIDController:
    """
    Dead-zone proportional + filtered derivative PID with
    symmetric integral clamping and conditional anti-windup.
    Input/output in degrees (or deg/s) — deadzone is px→deg converted via HFOV/W.
    Implements §6: dead zone, proportional recentre, derivative damping,
    saturation (handled by caller), slew-rate limiting (caller), anti-windup.
    """
    def __init__(self, kp=1.2, ki=0.05, kd=0.15, deadzone=2.0, integral_limit=8.0, derivative_filter=0.2):
        self.kp = kp; self.ki = ki; self.kd = kd
        self.deadzone = deadzone          # px (spec: 2 px)
        self.integral_limit = integral_limit  # deg·s (clamp)
        self.deriv_alpha = derivative_filter  # 0..1 (low-pass)
        self.integral = 0.0
        self.prev_error = 0.0
        self.prev_deriv = 0.0

    def reset(self):
        self.integral = 0.0; self.prev_error = 0.0; self.prev_deriv = 0.0

    def step(self, error_deg: float, dt: float) -> float:
        # px → deg: 1 px = HFOV/W = 4/640 = 0.00625°, so 2 px = 0.0125°
        # Use 0.00625*deadzone as threshold (not 0.015*deadzone/2)
        dz = 0.00625 * self.deadzone
        in_dead = abs(error_deg) < dz
        if in_dead:
            # Inside dead zone: output 0, but update prev_error to avoid derivative kick on exit,
            # and gently decay integral (no wind-up while at setpoint)
            self.prev_error = error_deg
            # exponential decay of integral while in deadzone (prevents drift)
            self.integral *= 0.98
            # still filter derivative toward 0
            self.prev_deriv *= (1 - self.deriv_alpha)
            return 0.0

        p = self.kp * error_deg

        # Conditional integration: only integrate if not saturated in direction of error
        # Caller will clamp output; we do tentative integration then let caller decide anti-windup.
        # Here we integrate unconditionally but clamp — caller may undo via back-calculation.
        self.integral += error_deg * dt
        # symmetric clamp
        if self.integral > self.integral_limit:
            self.integral = self.integral_limit
        if self.integral < -self.integral_limit:
            self.integral = -self.integral_limit
        i = self.ki * self.integral

        deriv = (error_deg - self.prev_error) / max(dt, 1e-6)
        deriv_f = self.deriv_alpha * deriv + (1 - self.deriv_alpha) * self.prev_deriv
        d = self.kd * deriv_f

        self.prev_error = error_deg
        self.prev_deriv = deriv_f
        return p + i + d

    def back_calculate_anti_windup(self, unsat_output: float, sat_output: float, dt: float):
        """Back-calculation anti-windup: adjust integral by (sat-unsat)/Ki if Ki>0."""
        if self.ki == 0 or dt == 0:
            return
        # difference due to saturation
        diff = sat_output - unsat_output
        # adjust integral opposite to diff (simple back-calculation with gain 1)
        # integral is in deg·s, diff is in deg/s, so divide by Ki and scale by dt
        # Use small gain: integral += (diff / Ki) * 0.1
        # Only if diff and integral have same sign (wind-up direction)
        if diff != 0 and (diff > 0) == (self.integral > 0):
            self.integral += (diff / self.ki) * 0.15 * dt
            # re-clamp
            if self.integral > self.integral_limit:
                self.integral = self.integral_limit
            if self.integral < -self.integral_limit:
                self.integral = -self.integral_limit

    def decay_integral(self, factor=0.96):
        self.integral *= factor

    def freeze_integral(self):
        pass

    def update_gains(self, kp=None, ki=None, kd=None, deadzone=None, integral_limit=None):
        if kp is not None: self.kp = kp
        if ki is not None: self.ki = ki
        if kd is not None: self.kd = kd
        if deadzone is not None: self.deadzone = deadzone
        if integral_limit is not None: self.integral_limit = integral_limit
