import cv2
import numpy as np
import pytest


@pytest.fixture
def tiny_video(tmp_path):
    """A tiny synthetic 10-frame video with a distinct solid color per
    frame, so tests can assert on exactly which frames were extracted.
    """
    path = tmp_path / "tiny.avi"
    fourcc = cv2.VideoWriter_fourcc(*"XVID")
    writer = cv2.VideoWriter(str(path), fourcc, 10.0, (16, 16))
    for i in range(10):
        frame = np.full((16, 16, 3), fill_value=i * 20, dtype=np.uint8)
        writer.write(frame)
    writer.release()
    return str(path)
