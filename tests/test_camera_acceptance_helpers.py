import importlib.util
from pathlib import Path

import numpy as np

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "camera_acceptance.py"
spec = importlib.util.spec_from_file_location("camera_acceptance", SCRIPT)
ca = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ca)


def _frame():
    return np.random.default_rng(1).integers(1, 256, size=(48, 64, 3), dtype=np.uint8)


def test_synthetic_inputs_have_expected_properties():
    frame = _frame()
    inputs = ca.make_synthetic_inputs(frame)
    assert set(inputs) == {"black", "dark_5pct", "blur_k61", "right_half_occluded", "noise", "white"}
    assert all(image.shape == frame.shape and image.dtype == np.uint8 for image in inputs.values())
    assert inputs["black"].max() == 0
    assert inputs["white"].min() == 255
    assert inputs["dark_5pct"].max() <= 13  # 255 * 0.05
    occluded = inputs["right_half_occluded"]
    assert occluded[:, 32:].max() == 0
    assert np.array_equal(occluded[:, :32], frame[:, :32])


def test_synthetic_inputs_do_not_mutate_the_original_frame():
    frame = _frame()
    before = frame.copy()
    ca.make_synthetic_inputs(frame)
    assert np.array_equal(frame, before)
