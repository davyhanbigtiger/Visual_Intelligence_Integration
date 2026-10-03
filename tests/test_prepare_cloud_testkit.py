import importlib.util
import json
from pathlib import Path

import cv2
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("prepare_cloud_testkit", ROOT / "scripts" / "prepare_cloud_testkit.py")
kit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kit)


def test_normalize_url_upgrades_http_and_rejects_other_schemes():
    assert kit.normalize_url("http://example.com/a.mp4") == "https://example.com/a.mp4"
    assert kit.normalize_url("https://example.com/a.mp4") == "https://example.com/a.mp4"
    for bad in ("file:///etc/passwd", "ftp://example.com/x", "javascript:alert(1)", "https://", "data:text/plain,hi"):
        with pytest.raises(ValueError):
            kit.normalize_url(bad)


def test_sha256_file_matches_known_value(tmp_path):
    path = tmp_path / "abc.bin"
    path.write_bytes(b"abc")
    assert kit.sha256_file(path) == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_synthetic_images_are_deterministic_and_labelled_correctly():
    first, label = kit.make_synthetic_image(3, seed=7)
    again, _ = kit.make_synthetic_image(3, seed=7)
    other, _ = kit.make_synthetic_image(3, seed=8)
    assert np.array_equal(first, again)
    assert not np.array_equal(first, other)
    assert label["circles"] == 4 and sum(label["colors"].values()) == 4
    foreground = np.any(first != np.array(kit.BACKGROUND, dtype=np.uint8), axis=2).astype(np.uint8)
    components, _ = cv2.connectedComponents(foreground)
    assert components - 1 == label["circles"]  # background component excluded


def test_synthetic_video_has_expected_frames_and_motion(tmp_path):
    path = tmp_path / "shapes.avi"
    info = kit.write_synthetic_video(path, seconds=2, fps=15)
    assert info["frames"] == 30
    cap = cv2.VideoCapture(str(path))
    xs = []
    for _ in range(info["frames"]):
        ok, frame = cap.read()
        assert ok
        mask = (frame[:, :, 2] > 180) & (frame[:, :, 0] < 90) & (frame[:, :, 1] < 90)
        ys, xs_found = np.nonzero(mask)
        xs.append(xs_found.mean())
    cap.release()
    assert xs[-1] - xs[0] > 300  # the red circle really travels left to right


def test_committed_sources_manifest_is_wellformed():
    data = json.loads((ROOT / "scripts" / "testkit_sources.json").read_text(encoding="utf-8"))
    names = [item["name"] for item in data["images"] + data["videos"]]
    assert len(names) == len(set(names))
    assert len(data["images"]) >= 13  # enough distinct inputs for 12 timed + 1 warm-up
    for item in data["images"] + data["videos"]:
        assert kit.normalize_url(item["url"]).startswith("https://")
        assert item["source"] and item["license_note"]
