"""Tests for Mute Mode v2 features, classifier and live segmentation (no camera, no MediaPipe)."""

import numpy as np
import pytest

from mute_mode.features import FEATURE_DIM_V2, SEQ_LEN, augment, sequence_features, trim_to_activity
from mute_mode.holistic import empty_frame, stack_frames


def synthetic_seq(T=40, right_only=True, seed=0):
    rng = np.random.default_rng(seed)
    frames = []
    for t in range(T):
        f = empty_frame()
        f["pose"][:, :2] = rng.normal(0.5, 0.01, (33, 2))
        f["pose"][11, :2] = (0.6, 0.6)   # signer's left shoulder (image right)
        f["pose"][12, :2] = (0.4, 0.6)   # signer's right shoulder
        f["pose_ok"] = True
        hand = rng.normal(0, 0.02, (21, 3)).astype(np.float32)
        hand[:, :2] += (0.45 + 0.005 * t, 0.4)
        if 5 <= t < T - 5:
            f["rh"], f["rh_ok"] = hand, True
            if not right_only:
                f["lh"], f["lh_ok"] = hand + 0.1, True
        frames.append(f)
    return stack_frames(frames)


def test_feature_shape_and_body_normalisation():
    x = sequence_features(synthetic_seq())
    assert x.shape == (SEQ_LEN, FEATURE_DIM_V2)
    assert np.isfinite(x).all()
    # shoulders sit at (+-0.5, 0) in the body frame (centre = mid shoulders, unit = shoulder width)
    assert abs(abs(x[0, 2]) - 0.5) < 1e-4 and abs(x[0, 3]) < 1e-4


def test_scale_and_translation_invariance():
    seq = synthetic_seq()
    moved = {k: (v.copy() if isinstance(v, np.ndarray) else v) for k, v in seq.items()}
    for k in ("pose", "lh", "rh"):
        moved[k][..., :2] = moved[k][..., :2] * 1.7 + 0.3
        moved[k][..., 2] = moved[k][..., 2] * 1.7  # depth scales with the image too
    a, b = sequence_features(seq), sequence_features(moved)
    assert np.allclose(a, b, atol=1e-4)


def test_trim_removes_handless_edges():
    seq = trim_to_activity(synthetic_seq(T=40), pad=0)
    assert len(seq["rh_ok"]) == 30 and seq["rh_ok"].all()


def test_augment_mirror_swaps_hands():
    seq = synthetic_seq()
    rng = np.random.default_rng(1)
    for _ in range(20):
        out = augment(seq, rng)
        assert out["lh_ok"].any() != out["rh_ok"].any() or out["rh_ok"].any()
        x = sequence_features(out)
        assert x.shape == (SEQ_LEN, FEATURE_DIM_V2) and np.isfinite(x).all()


def test_classifier_v2_forward_and_size():
    torch = pytest.importorskip("torch")  # CI installs only numpy/pytest/ruff
    from mute_mode.classifier_v2 import SignClassifierV2
    m = SignClassifierV2(num_classes=100)
    assert m(torch.zeros(4, SEQ_LEN, FEATURE_DIM_V2)).shape == (4, 100)
    assert m.get_parameter_count() < 400_000  # stays comfortably edge sized


def test_classifier_v2_save_load_roundtrip(tmp_path):
    torch = pytest.importorskip("torch")
    from mute_mode.classifier_v2 import SignClassifierV2, load_v2, save_v2
    vocab = [f"w{i}" for i in range(5)]
    m = SignClassifierV2(num_classes=5).eval()
    p = tmp_path / "m.pth"
    save_v2(m, str(p), vocab, {"note": "t"})
    m2, v2, meta = load_v2(str(p))
    x = torch.randn(1, SEQ_LEN, FEATURE_DIM_V2)
    assert torch.allclose(m(x), m2(x)) and v2 == vocab and meta["note"] == "t"


class ScriptedExtractor:
    """Pretends to be HolisticExtractor: hands visible during given frame indices."""

    def __init__(self, active):
        self.active, self.i = set(active), 0

    def extract(self, frame, ts=None):
        f = empty_frame()
        f["pose_ok"] = True
        f["pose"][11, :2], f["pose"][12, :2] = (0.6, 0.6), (0.4, 0.6)
        if self.i in self.active:
            f["rh"][:, :2] = 0.45
            f["rh"][1:, 0] += np.linspace(0.01, 0.1, 20)
            f["rh_ok"] = True
        self.i += 1
        return f

    def close(self):
        pass


def test_live_recognizer_segments_one_sign(tmp_path):
    pytest.importorskip("torch")
    from mute_mode.classifier_v2 import SignClassifierV2, save_v2
    from mute_mode.recognizer import LiveSignRecognizer
    p = tmp_path / "m.pth"
    save_v2(SignClassifierV2(num_classes=3), str(p), ["a", "b", "c"])
    rec = LiveSignRecognizer(str(p), extractor=ScriptedExtractor(range(10, 40)), conf_threshold=0.0)
    preds = [rec.process_frame(None, timestamp_s=i / 25.0) for i in range(70)]
    preds = [q for q in preds if q]
    assert len(preds) == 1
    assert preds[0]["label"] in ("a", "b", "c") and 28 <= preds[0]["frames"] <= 36
