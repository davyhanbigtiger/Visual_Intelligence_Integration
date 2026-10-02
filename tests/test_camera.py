import base64
import json

import cv2
import numpy as np
import pytest

from visualintel import camera


def test_camera_frame_is_resized_and_uses_scene_schema(monkeypatch):
    def call(images, prompt, **kwargs):
        frame = cv2.imdecode(np.frombuffer(base64.b64decode(images[0]), dtype=np.uint8), cv2.IMREAD_COLOR)
        assert frame.shape[:2] == (360, 640)
        assert kwargs["model"] == "minicpm-v4.6"
        assert kwargs["response_schema"] == camera.FACTUAL_SCHEMA
        assert kwargs["generation_options"]["num_predict"] == 96
        return json.dumps({"answer": "A person in a room."})
    monkeypatch.setattr(camera, "call_model", call)
    assert camera.analyze_frame(np.zeros((720, 1280, 3), dtype=np.uint8)) == "A person in a room."


def test_camera_released_when_window_creation_fails(monkeypatch):
    class Capture:
        released = False
        def isOpened(self):
            return True
        def release(self):
            self.released = True
    cap = Capture()
    monkeypatch.setattr(camera, "check_ollama_ready", lambda **kwargs: None)
    monkeypatch.setattr(camera.cv2, "VideoCapture", lambda *args: cap)
    def fail():
        raise RuntimeError("window unavailable")
    monkeypatch.setattr(camera.tk, "Tk", fail)
    with pytest.raises(RuntimeError, match="window unavailable"):
        camera.run_camera()
    assert cap.released
