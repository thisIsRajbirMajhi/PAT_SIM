import numpy as np
import cv2
import random

def apply_gaussian(img, std, rng):
    if std <= 0: return img
    noise = rng.normal(0, std, img.shape).astype(np.float32)
    out = img.astype(np.float32) + noise
    return np.clip(out, 0, 255).astype(np.uint8)

def apply_salt_pepper(img, prob, rng):
    if prob <= 0: return img
    out = img.copy()
    h,w = img.shape
    num = int(prob * h * w)
    # salt
    ys = rng.integers(0, h, size=num)
    xs = rng.integers(0, w, size=num)
    vals = rng.integers(0, 2, size=num)  # 0 pepper 1 salt
    out[ys[vals==1], xs[vals==1]] = 255
    out[ys[vals==0], xs[vals==0]] = 0
    return out

def apply_poisson(img, rng):
    # scale to simulate photon noise: convert to float, apply poisson approx
    # Use numpy poisson on scaled image
    # Prevent overflow: use moderate scaling
    scaled = img.astype(np.float32) / 255.0 * 30.0
    noisy = rng.poisson(scaled).astype(np.float32)
    noisy = noisy / 30.0 * 255.0
    return np.clip(noisy, 0, 255).astype(np.uint8)

def apply_jitter(img, jitter_px, rng):
    if jitter_px <= 0: return img
    dx = int(rng.integers(-int(jitter_px), int(jitter_px)+1))
    dy = int(rng.integers(-int(jitter_px), int(jitter_px)+1))
    if dx==0 and dy==0: return img
    h,w = img.shape
    M = np.float32([[1,0,dx],[0,1,dy]])
    return cv2.warpAffine(img, M, (w,h), borderMode=cv2.BORDER_REFLECT_101)

def apply_atmosphere(img, atmo_type, strength):
    if atmo_type == "clear" or strength <= 0:
        return img
    out = img.astype(np.float32)
    if atmo_type == "haze":
        # reduce contrast, add veil
        out = out * (1 - 0.5*strength) + 60*strength
        out = cv2.GaussianBlur(out.astype(np.uint8), (5,5), 0).astype(np.float32) * 0.15 + out*0.85
    elif atmo_type == "fog":
        out = out * (1 - 0.65*strength) + 90*strength
        out = cv2.GaussianBlur(out.astype(np.uint8), (7,7), 0).astype(np.float32)*0.25 + out*0.75
    elif atmo_type == "rain":
        # contrast reduction + streaks
        out = out * (1 - 0.3*strength)
        # add vertical streaks
        h,w = img.shape
        streak = np.zeros_like(img, dtype=np.uint8)
        import cv2 as cv2i
        for _ in range(int(120*strength)):
            x = np.random.randint(0,w)
            y = np.random.randint(0,h-20)
            cv2i.line(streak, (x,y), (x+2, y+12), 180, 1)
        out = cv2.addWeighted(out.astype(np.uint8), 1, streak, 0.25*strength, 0).astype(np.float32)
    elif atmo_type == "low_light":
        out = out * (0.45 + 0.55*(1-strength))  # darken
        out = np.clip(out, 0, 255)
    return np.clip(out, 0, 255).astype(np.uint8)
