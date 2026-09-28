"""IMM over 3 EKF modes — canonical implementation (moved verbatim from tracking/imm.py)."""
import numpy as np

from .ekf import SimpleEKF


class IMM:
    def __init__(self, cfg):
        self.cfg = cfg
        self.models = {
            "CV": SimpleEKF(cfg, mode="CV"),
            "CA": SimpleEKF(cfg, mode="CA"),
            "MN": SimpleEKF(cfg, mode="MN"),
        }
        self.model_names = ["CV", "CA", "MN"]
        # transition matrix
        self.trans = np.array([
            [0.90, 0.08, 0.02],
            [0.08, 0.90, 0.02],
            [0.05, 0.10, 0.85],
        ], dtype=float)
        self.probs = np.array([0.6, 0.25, 0.15], dtype=float)
        self.fused_x = np.zeros(6)
        self.fused_P = np.eye(6) * 5
        self.last_nis = 0.0

    def predict(self, dt=None):
        # mix step
        cbar = self.trans.T @ self.probs  # predicted prob?
        # Actually mixing: mu_{i|j} = trans[i,j]*prob[i]/cbar[j]
        cbar = self.trans.T.dot(self.probs)  # but trans row is from, col to? Use standard.
        # For simplicity skip rigorous mixing and just predict each model independently
        for m in self.models.values():
            m.predict(dt)
        # fused prediction as weighted sum
        self._fuse()
        return self.fused_x.copy()

    def update(self, z_px, confidence=0.9):
        likelihoods = []
        nis_list = []
        for name in self.model_names:
            ekf = self.models[name]
            _, nis = ekf.update(z_px, confidence)
            # likelihood from nis: exp(-0.5*nis)
            like = float(np.exp(-0.5 * min(nis, 20)) + 1e-9)
            likelihoods.append(like)
            nis_list.append(nis)
        likelihoods = np.array(likelihoods)
        # update model probs: prob * likelihood * transition?
        # simplified: prob proportional to prob * likelihood
        # include transition mixing
        # prior = trans^T * probs  (predicted)
        prior = self.trans.T.dot(self.probs) if z_px is not None else self.probs
        # but self.trans is row from, so prior[j] = sum_i trans[i,j]*prob[i]
        posterior_unnorm = prior * likelihoods if z_px is not None else prior
        s = posterior_unnorm.sum()
        if s < 1e-12:
            self.probs = np.array([0.33, 0.33, 0.34])
        else:
            self.probs = posterior_unnorm / s
            # clamp min prob
            self.probs = np.maximum(self.probs, 0.02)
            self.probs /= self.probs.sum()
        self._fuse()
        self.last_nis = float(np.mean(nis_list)) if nis_list else 0.0
        return self.fused_x.copy()

    def _fuse(self):
        # weighted average of states
        xs = np.stack([self.models[n].x for n in self.model_names], axis=0)
        # covariance mixture: P = sum_i mu_i*(P_i + (x_i - x_fused)(...))
        fused = np.average(xs, axis=0, weights=self.probs)
        # plausibility clamp: coasting on bad velocity during long outages
        # must not drift outside the physical envelope (cf. X10 divergence).
        try:
            fused[0] = float(np.clip(fused[0], -12.0, 12.0))
            fused[1] = float(np.clip(fused[1], -12.0, 12.0))
            fused[2] = float(np.clip(fused[2], -15.0, 15.0))
            fused[3] = float(np.clip(fused[3], -15.0, 15.0))
            fused[4] = float(np.clip(fused[4], -60.0, 60.0))
            fused[5] = float(np.clip(fused[5], -60.0, 60.0))
        except Exception:
            pass
        self.fused_x = fused
        # fused covariance approx weighted sum
        Ps = [self.models[n].P for n in self.model_names]
        P_fused = np.zeros((6, 6))
        for i, name in enumerate(self.model_names):
            diff = (self.models[name].x - fused).reshape(6, 1)
            P_fused += self.probs[i] * (Ps[i] + diff @ diff.T)
        try:
            d = np.clip(np.diag(P_fused), 1e-6, 400.0)
            np.fill_diagonal(P_fused, d)
        except Exception:
            pass
        self.fused_P = P_fused

    def reseed(self, z_px):
        """Hard re-acquisition: anchor every model at the measurement with
        fresh initial covariance (cf. X8 sweep-past encounter).

        After a long outage the prior is pure accumulated process noise; a
        Bayesian update against it produces an overconfident wrong velocity
        (huge cross-covariance gain) that all later measurements then fail
        to gate into. Re-seeding is the standard acquisition-vs-track split:
        detect-then-initialize, not detect-then-update-a-fiction.
        """
        import math
        try:
            u, v = float(z_px[0]), float(z_px[1])
            cv = self.models["CV"]
            alpha = math.degrees(math.atan((u - cv.cx) / max(cv.fx, 1e-9)))
            beta = math.degrees(math.atan((cv.cy - v) / max(cv.fy, 1e-9)))
        except Exception:
            alpha, beta = 0.0, 0.0
        for m in self.models.values():
            m.x = np.array([alpha, beta, 0.0, 0.0, 0.0, 0.0], dtype=float)
            m.P = np.eye(6) * 5.0
            m.P[2, 2] = m.P[3, 3] = 10.0
            m.P[4, 4] = m.P[5, 5] = 20.0
            m._last_nis = 0.0
        self.probs = np.array([0.6, 0.25, 0.15], dtype=float)
        self._fuse()
        self.last_nis = 0.0
        return self.fused_x.copy()

    def update_config(self, cfg):
        self.cfg = cfg
        for m in self.models.values():
            try:
                m.update_config(cfg)
            except Exception:
                try:
                    m.cfg = cfg
                except Exception:
                    pass

    def get_pixel(self):
        # use fused state to project
        # delegate to CV model's projection (same fx)
        return self.models["CV"]._h(self.fused_x)

    def get_angle(self):
        return (float(self.fused_x[0]), float(self.fused_x[1]))

    def get_velocity(self):
        return (float(self.fused_x[2]), float(self.fused_x[3]))

    def reset(self):
        for m in self.models.values():
            m.x = np.zeros(6); m.P = np.eye(6) * 5
        self.probs = np.array([0.6, 0.25, 0.15])
        self.fused_x = np.zeros(6)
        self.fused_P = np.eye(6) * 5
