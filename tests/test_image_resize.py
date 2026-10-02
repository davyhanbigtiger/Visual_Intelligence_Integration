import cv2
import numpy as np
import pytest

from visualintel.engine import ModelCallError, resize_encoded_image


def encoded_image(width=640, height=480):
    image = np.zeros((height, width, 3), dtype=np.uint8)
    image[:, :width // 2] = (0, 0, 255)
    ok, buf = cv2.imencode(".jpg", image)
    assert ok
    return buf.tobytes()


def test_resize_preserves_aspect_ratio_and_visual_regions():
    raw = resize_encoded_image(encoded_image(), 320)
    image = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
    assert image.shape == (240, 320, 3)
    assert image[120, 40, 2] > 240
    assert image[120, 280].max() < 10


def test_no_upscale_or_reencoding_when_unnecessary():
    raw = encoded_image(160, 120)
    assert resize_encoded_image(raw, 320) == raw
    assert resize_encoded_image(raw) == raw


def test_bad_image_and_bad_limit_are_rejected():
    with pytest.raises(ModelCallError):
        resize_encoded_image(b"broken", 320)
    with pytest.raises(ValueError):
        resize_encoded_image(encoded_image(), 0)
