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
        self.model_names = ["CV","CA","MN"]
        # transition matrix
        self.trans = np.array([
            [0.90, 0.08, 0.02],
            [0.08, 0.90, 0.02],
            [0.05, 0.10, 0.85],
        ], dtype=float)
        self.probs = np.array([0.6, 0.25, 0.15], dtype=float)
        self.fused_x = np.zeros(6)
        self.fused_P = np.eye(6)*5
        self.last_nis = 0.0

    def predict(self, dt=None):
        # mix step
        cbar = self.trans.T @ self.probs  # predicted prob?
        # Actually mixing: mu_{i|j} = trans[i,j]*prob[i]/cbar[j]
        cbar = self.trans.T.dot(self.probs) # but trans row is from, col to? Use standard.
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
            self.probs = np.array([0.33,0.33,0.34])
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
        self.fused_x = fused
        # fused covariance approx weighted sum
        Ps = [self.models[n].P for n in self.model_names]
        P_fused = np.zeros((6,6))
        for i, name in enumerate(self.model_names):
            diff = (self.models[name].x - fused).reshape(6,1)
            P_fused += self.probs[i] * (Ps[i] + diff @ diff.T)
        self.fused_P = P_fused

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
            m.x = np.zeros(6); m.P = np.eye(6)*5
        self.probs = np.array([0.6,0.25,0.15])
        self.fused_x = np.zeros(6)
        self.fused_P = np.eye(6)*5
