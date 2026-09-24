import random
import numpy as np

def seed_all(seed: int):
    random.seed(seed)
    np.random.seed(seed)

def make_rng(seed: int):
    return np.random.default_rng(seed)
