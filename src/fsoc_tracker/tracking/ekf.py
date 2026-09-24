import numpy as np

class SimpleEKF:
    """
    6-state EKF-lite: [alpha, beta, alpha_dot, beta_dot, alpha_ddot, beta_ddot]
    Measurement: pixel (u,v) via nonlinear tan projection.
    For practical stability we keep CV/CA/MN as process-noise variants.
    Simplified: use linear pixel measurement when near center, but keep tan for Jacobian.
    """
    def __init__(self, cfg, mode="CV"):
        cam_res = tuple(cfg["camera"]["resolution"])
        fov = tuple(cfg["camera"]["fov_deg"])
        self.res_w, self.res_h = cam_res
        self.fov_h, self.fov_v = fov
        # focal lengths in px per radian approx: f = (W/2)/tan(FOV/2)
        import math
        self.fx = (self.res_w/2) / math.tan(math.radians(self.fov_h)/2 + 1e-9)
        self.fy = (self.res_h/2) / math.tan(math.radians(self.fov_v)/2 + 1e-9)
        self.cx = self.res_w/2
        self.cy = self.res_h/2
        self.mode = mode
        self.dt = 1.0 / max(float(cfg["camera"]["fps"]), 1)
        # state and covariance
        self.x = np.zeros(6, dtype=float)  # alpha,beta,adot,bdot,addot,bddot (degrees)
        self.P = np.eye(6)*5.0
        self.P[2,2]= self.P[3,3]=10
        self.P[4,4]= self.P[5,5]=20
        # noises
        meas_noise = float(cfg["tracker"].get("meas_noise",4.0))
        self.R = np.eye(2)*(meas_noise**2)
        pn = float(cfg["tracker"].get("process_noise",0.8))
        scale = {"CV":0.6, "CA":1.2, "MN":3.0}.get(mode, 1.0)
        self.Q_base = pn * scale

    def _F(self, dt):
        # state transition: constant acceleration model
        F = np.eye(6)
        F[0,2]=dt; F[0,4]=0.5*dt*dt
        F[1,3]=dt; F[1,5]=0.5*dt*dt
        F[2,4]=dt
        F[3,5]=dt
        return F

    def _Q(self, dt):
        q = self.Q_base
        # process noise on acceleration
        Q = np.zeros((6,6))
        # continuous white noise acceleration model
        dt2 = dt*dt; dt3 = dt2*dt; dt4 = dt3*dt
        # position
        Q[0,0]= dt4/4 * q; Q[0,2]= dt3/2 * q; Q[0,4]= dt2/2 * q
        Q[1,1]= dt4/4 * q; Q[1,3]= dt3/2 * q; Q[1,5]= dt2/2 * q
        Q[2,0]= dt3/2 * q; Q[2,2]= dt2 * q;   Q[2,4]= dt * q
        Q[3,1]= dt3/2 * q; Q[3,3]= dt2 * q;   Q[3,5]= dt * q
        Q[4,0]= dt2/2 * q; Q[4,2]= dt * q;   Q[4,4]= 1 * q
        Q[5,1]= dt2/2 * q; Q[5,3]= dt * q;   Q[5,5]= 1 * q
        # symmetrize
        Q = (Q+Q.T)/2
        # ensure PD
        Q += np.eye(6)*1e-4
        return Q

    def predict(self, dt=None):
        if dt is None: dt = self.dt
        F = self._F(dt)
        Q = self._Q(dt)
        self.x = F @ self.x
        self.P = F @ self.P @ F.T + Q
        return self.x.copy()

    def _h(self, x):
        # nonlinear measurement: u = cx + fx*tan(alpha_rad), v = cy + fy*tan(beta_rad) ??? spec uses tan(alpha)
        import math
        alpha = math.radians(x[0]); beta = math.radians(x[1])
        u = self.cx + self.fx * math.tan(alpha)
        v = self.cy + self.fy * math.tan(beta) * (-1)  # invert? detector y increases downwards, beta positive up => v = cy - fy*tan(beta)
        # Actually we used above: v = cy - fy*tan(beta) to make tilt consistent. Fix:
        v = self.cy - self.fy * math.tan(beta)
        return np.array([u, v], dtype=float)

    def _H(self, x):
        import math
        alpha = math.radians(x[0]); beta = math.radians(x[1])
        # Jacobian dh/dx : only alpha and beta affect measurement
        # du/dalpha = fx * sec^2(alpha) * pi/180
        sec2_a = 1.0 / (math.cos(alpha)**2 + 1e-9)
        sec2_b = 1.0 / (math.cos(beta)**2 + 1e-9)
        du_da = self.fx * sec2_a * math.pi/180.0
        dv_db = -self.fy * sec2_b * math.pi/180.0
        H = np.zeros((2,6))
        H[0,0]= du_da
        H[1,1]= dv_db
        return H

    def update(self, z_px, confidence=0.9):
        # z_px: (u,v) measurement
        if z_px is None:
            # no update, inflate covariance slightly
            self.P += np.eye(6)*0.3
            return self.x.copy(), 0.0
        z = np.array(z_px, dtype=float)
        # adapt R by confidence
        R = self.R * (1.5 - 0.8*confidence)  # high conf -> smaller R
        zpred = self._h(self.x)
        H = self._H(self.x)
        y = z - zpred  # innovation
        S = H @ self.P @ H.T + R
        # gating: normalized innovation squared
        try:
            invS = np.linalg.inv(S)
        except:
            invS = np.linalg.pinv(S)
        nis = float(y @ invS @ y)
        # outlier gate: if huge, reject
        gate = float(self.cfg_gate_sigma()**2 * 2) if hasattr(self, 'cfg_gate_sigma') else 36.0
        # we store gate externally; for now threshold 25 (5 sigma)
        if nis > 28:
            # reject measurement, increase covariance slightly
            self.P += np.eye(6)*0.8
            return self.x.copy(), nis
        K = self.P @ H.T @ invS
        self.x = self.x + K @ y
        I = np.eye(6)
        self.P = (I - K @ H) @ self.P
        # ensure symmetry
        self.P = (self.P + self.P.T)/2
        return self.x.copy(), nis

    def cfg_gate_sigma(self):
        return 5.0

    def get_pixel_estimate(self):
        return self._h(self.x)

    def get_angle_estimate(self):
        return (float(self.x[0]), float(self.x[1]))

    def get_velocity(self):
        return (float(self.x[2]), float(self.x[3]))
