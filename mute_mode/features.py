# mute_mode/features.py
# -----------------------------------------------------------------------------
# Feature engineering for Mute Mode v2. Used by BOTH training and live
# inference so the two can never drift apart.
#
# Input : a raw landmark sequence from holistic.extract_video / HolisticExtractor
#         (pose (T,33,4), lh/rh (T,21,3), lh_ok/rh_ok/pose_ok (T,))
# Output: float32 array (SEQ_LEN, FEATURE_DIM_V2)
#
# Per frame features (FEATURE_DIM_V2 = 226):
#   14  upper body  : nose, shoulders, elbows, wrists (x, y) in the body frame
#   2 x 42 hand position : 21 keypoints (x, y) of each hand in the body frame
#                          -> where the hand is and how it moves
#   2 x 63 hand shape    : 21 keypoints (x, y, z) relative to that hand's wrist,
#                          scaled by hand size -> what the hand looks like
#   2   presence flags for the left and right hand
# The body frame is centred on the mid point of the shoulders and scaled by the
# shoulder width, so the features do not depend on camera distance or framing.
# -----------------------------------------------------------------------------

from typing import Dict, Optional

import numpy as np

SEQ_LEN = 32
UPPER_BODY = [0, 11, 12, 13, 14, 15, 16]  # nose, shoulders, elbows, wrists
FEATURE_DIM_V2 = len(UPPER_BODY) * 2 + 2 * 42 + 2 * 63 + 2  # 226

# Column groups (used for ablation studies in train_v2.py)
_P, _H = len(UPPER_BODY) * 2, 2 * 42
FEATURE_GROUPS = {
    "pose": list(range(0, _P)),
    "hand_position": list(range(_P, _P + _H)),
    "hand_shape": list(range(_P + _H, _P + _H + 126)),
    "presence": list(range(_P + _H + 126, FEATURE_DIM_V2)),
}
FEATURE_SETS = {
    "full": FEATURE_GROUPS["pose"] + FEATURE_GROUPS["hand_position"] + FEATURE_GROUPS["hand_shape"] + FEATURE_GROUPS["presence"],
    # what v1 used: wrist relative handshape only, no location or movement
    "shape_only": FEATURE_GROUPS["hand_shape"] + FEATURE_GROUPS["presence"],
    "no_pose": FEATURE_GROUPS["hand_position"] + FEATURE_GROUPS["hand_shape"] + FEATURE_GROUPS["presence"],
}

# Swapping left/right when mirroring
_POSE_MIRROR = np.arange(33)
for _a, _b in [(1, 4), (2, 5), (3, 6), (7, 8), (9, 10), (11, 12), (13, 14), (15, 16),
               (17, 18), (19, 20), (21, 22), (23, 24), (25, 26), (27, 28), (29, 30), (31, 32)]:
    _POSE_MIRROR[_a], _POSE_MIRROR[_b] = _b, _a


def _interp_missing(arr: np.ndarray, ok: np.ndarray, max_gap: int = 6) -> (np.ndarray, np.ndarray):
    """Linearly fills gaps of up to max_gap frames between two detections."""
    arr = arr.copy()
    ok = ok.copy()
    idx = np.flatnonzero(ok)
    if len(idx) < 2:
        return arr, ok
    for a, b in zip(idx[:-1], idx[1:]):
        gap = b - a - 1
        if 0 < gap <= max_gap:
            for k in range(1, gap + 1):
                t = k / (gap + 1)
                arr[a + k] = (1 - t) * arr[a] + t * arr[b]
                ok[a + k] = True
    return arr, ok


def _body_frame(seq: Dict[str, np.ndarray]):
    """Returns (centre (2,), scale float) from the shoulders, robust over the clip."""
    pose, pok = seq["pose"], seq["pose_ok"]
    if pok.any():
        ls, rs = pose[pok, 11, :2], pose[pok, 12, :2]
        centre = np.median((ls + rs) / 2.0, axis=0)
        scale = float(np.median(np.linalg.norm(ls - rs, axis=1)))
    else:
        centre, scale = None, 0.0
    if scale < 1e-3:
        # no usable pose: fall back to the spread of the hands
        pts = []
        for s in ("lh", "rh"):
            if seq[s + "_ok"].any():
                pts.append(seq[s][seq[s + "_ok"]][:, :, :2].reshape(-1, 2))
        if pts:
            pts = np.concatenate(pts)
            centre = pts.mean(0) if centre is None else centre
            scale = max(float(np.ptp(pts, axis=0).max()), 0.2)
        else:
            centre, scale = np.zeros(2, np.float32), 1.0
    return centre.astype(np.float32), scale


def resample_indices(n: int, length: int = SEQ_LEN, start: float = 0.0, end: Optional[float] = None) -> np.ndarray:
    end = n - 1 if end is None else end
    return np.clip(np.round(np.linspace(start, end, length)).astype(int), 0, n - 1)


def trim_to_activity(seq: Dict[str, np.ndarray], pad: int = 2) -> Dict[str, np.ndarray]:
    """Drops leading and trailing frames where no hand is visible."""
    any_hand = seq["lh_ok"] | seq["rh_ok"]
    idx = np.flatnonzero(any_hand)
    if len(idx) < 4:
        return seq
    a, b = max(idx[0] - pad, 0), min(idx[-1] + pad + 1, len(any_hand))
    return {k: (v[a:b] if isinstance(v, np.ndarray) and v.ndim >= 1 and len(v) == len(any_hand) else v)
            for k, v in seq.items()}


def augment(seq: Dict[str, np.ndarray], rng: np.random.Generator) -> Dict[str, np.ndarray]:
    """Random geometric and temporal augmentation in raw landmark space."""
    T = len(seq["lh_ok"])
    out = {k: (v.copy() if isinstance(v, np.ndarray) else v) for k, v in seq.items()}

    # temporal: random crop of 80 to 100 percent of the clip, plus speed change via resampling later
    keep = rng.uniform(0.8, 1.0)
    L = max(int(round(T * keep)), min(T, 8))
    s = rng.integers(0, T - L + 1)
    for k in ("pose", "lh", "rh", "lh_ok", "rh_ok", "pose_ok"):
        out[k] = out[k][s:s + L]

    # mirror: a left handed signer performs the mirror image of the same sign
    if rng.random() < 0.5:
        for k in ("pose", "lh", "rh"):
            out[k][..., 0] *= -1.0
        out["pose"] = out["pose"][:, _POSE_MIRROR]
        out["lh"], out["rh"] = out["rh"], out["lh"]
        out["lh_ok"], out["rh_ok"] = out["rh_ok"], out["lh_ok"]

    # 2D affine: rotation, anisotropic scale, shear, about the origin (body frame removes translation)
    ang = np.deg2rad(rng.uniform(-13, 13))
    sx, sy = rng.uniform(0.85, 1.15, size=2)
    sh = rng.uniform(-0.12, 0.12)
    R = np.array([[np.cos(ang), -np.sin(ang)], [np.sin(ang), np.cos(ang)]], np.float32)
    A = R @ np.array([[sx, sh], [0, sy]], np.float32)
    for k in ("pose", "lh", "rh"):
        xy = out[k][..., :2]
        out[k][..., :2] = xy @ A.T

    # per hand small shape jitter and random dropped detections
    for s_ in ("lh", "rh"):
        out[s_] = out[s_] + rng.normal(0, 0.003, out[s_].shape).astype(np.float32)
        if rng.random() < 0.3:
            drop = rng.random(len(out[s_ + "_ok"])) < 0.1
            out[s_ + "_ok"] = out[s_ + "_ok"] & ~drop
    return out


def sequence_features(seq: Dict[str, np.ndarray], length: int = SEQ_LEN,
                      rng: Optional[np.random.Generator] = None) -> np.ndarray:
    """Raw landmark sequence -> (length, FEATURE_DIM_V2) float32 array."""
    if rng is not None:
        seq = augment(seq, rng)
    T = len(seq["lh_ok"])
    lh, lh_ok = _interp_missing(seq["lh"], seq["lh_ok"])
    rh, rh_ok = _interp_missing(seq["rh"], seq["rh_ok"])
    centre, scale = _body_frame({**seq, "lh": lh, "rh": rh, "lh_ok": lh_ok, "rh_ok": rh_ok})

    pose = seq["pose"][:, UPPER_BODY, :2]
    pose_n = (pose - centre) / scale
    pose_n[~seq["pose_ok"]] = 0.0

    feats_hand = []
    for arr, ok in ((lh, lh_ok), (rh, rh_ok)):
        pos = (arr[:, :, :2] - centre) / scale  # (T,21,2)
        local = arr - arr[:, :1, :]
        size = np.linalg.norm(local[:, :, :2], axis=2).max(axis=1, keepdims=True)  # (T,1)
        size = np.where(size < 1e-6, 1.0, size)
        shape = local / size[:, :, None]
        pos[~ok] = 0.0
        shape[~ok] = 0.0
        feats_hand.append((pos.reshape(T, -1), shape.reshape(T, -1), ok.astype(np.float32)[:, None]))

    frame_feats = np.concatenate([
        pose_n.reshape(T, -1),
        feats_hand[0][0], feats_hand[1][0],
        feats_hand[0][1], feats_hand[1][1],
        feats_hand[0][2], feats_hand[1][2],
    ], axis=1).astype(np.float32)

    # uniform resampling to a fixed length (the random crop in augment() already varies speed)
    out = frame_feats[resample_indices(T, length)]
    np.clip(out, -6.0, 6.0, out=out)
    return out
