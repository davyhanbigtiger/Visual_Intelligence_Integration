import importlib.util
import json
from pathlib import Path

import cv2
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("compare", ROOT / "scripts" / "cloud" / "compare_local_remote.py")
compare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compare)

kit_spec = importlib.util.spec_from_file_location("prepare_cloud_testkit", ROOT / "scripts" / "prepare_cloud_testkit.py")
kit_mod = importlib.util.module_from_spec(kit_spec)
kit_spec.loader.exec_module(kit_mod)


def make_kit(tmp_path, name="clip.mp4", payload=b"public video bytes"):
    kit = tmp_path / "kit"
    (kit / "videos").mkdir(parents=True)
    video = kit / "videos" / name
    video.write_bytes(payload)
    lock = {"files": {f"videos/{name}": {"sha256": compare.sha256_bytes(video)}}}
    (kit / "manifest.lock.json").write_text(json.dumps(lock), encoding="utf-8")
    return kit, video


def test_public_video_is_accepted(tmp_path):
    kit, video = make_kit(tmp_path)
    compare.verify_public_video(video, kit)


def test_personal_or_unrecorded_video_is_refused_for_remote(tmp_path):
    kit, _ = make_kit(tmp_path)
    personal = tmp_path / "videos" / "test_video.avi"
    personal.parent.mkdir()
    personal.write_bytes(b"personal")
    with pytest.raises(ValueError, match="not a recorded public"):
        compare.verify_public_video(personal, kit)
    sneaky = kit / "videos" / "other.mp4"  # inside the kit folder but never recorded in the lock
    sneaky.write_bytes(b"x")
    with pytest.raises(ValueError, match="not a recorded public"):
        compare.verify_public_video(sneaky, kit)


def test_generated_synthetic_video_is_accepted_only_when_labelled(tmp_path):
    kit, _ = make_kit(tmp_path)
    (kit / "synthetic").mkdir()
    shapes = kit / "synthetic" / "moving-shapes.avi"
    shapes.write_bytes(b"generated")
    (kit / "synthetic" / "labels.json").write_text(
        json.dumps({"images": {}, "video": {"synthetic/moving-shapes.avi": {}}}), encoding="utf-8")
    compare.verify_public_video(shapes, kit)
    unlabelled = kit / "synthetic" / "webcam.avi"
    unlabelled.write_bytes(b"personal")
    with pytest.raises(ValueError, match="not a recorded public"):
        compare.verify_public_video(unlabelled, kit)


def test_tampered_video_and_missing_lock_are_refused(tmp_path):
    kit, video = make_kit(tmp_path)
    video.write_bytes(b"changed after the lock was written")
    with pytest.raises(ValueError, match="sha256"):
        compare.verify_public_video(video, kit)
    (kit / "manifest.lock.json").unlink()
    with pytest.raises(ValueError, match="no manifest"):
        compare.verify_public_video(video, kit)


def test_sample_frames_are_ordered_and_skip_the_ends(tmp_path):
    path = tmp_path / "shapes.avi"
    info = kit_mod.write_synthetic_video(path, seconds=4, fps=10)
    frames = compare.sample_frames(path, 5)
    stamps = [t for t, _ in frames]
    assert len(frames) == 5 and stamps == sorted(stamps)
    assert stamps[0] > 0 and stamps[-1] < (info["frames"] - 1) / 10
    assert all(cv2.imdecode(np.frombuffer(j, dtype=np.uint8), cv2.IMREAD_COLOR) is not None for _, j in frames)


def encode_blank(width, height):
    ok, enc = cv2.imencode(".jpg", np.full((height, width, 3), 100, dtype=np.uint8))
    return enc.tobytes()


def test_sizes_that_would_send_identical_pixels_are_collapsed_and_labelled():
    low_res = encode_blank(320, 180)  # smaller than every requested side: the engine never upscales
    kept, labels = compare.effective_sides(low_res, [640, 448])
    assert kept == [640] and labels == {640: "320×180"}
    hi_res = encode_blank(640, 480)
    kept, labels = compare.effective_sides(hi_res, [640, 448])
    assert kept == [640, 448] and labels[640] == "640×480" and labels[448] == "448×336"


def test_answer_text_handles_good_bad_and_failed_records():
    assert compare.answer_text({"response": json.dumps({"answer": "a room"})}) == "a room"
    assert compare.answer_text({"response": "garbage 1 2 3"}).startswith("[invalid JSON]")
    assert compare.answer_text({"error": "timeout"}) == "[error] timeout"


def test_html_report_escapes_model_text(tmp_path):
    frame = np.zeros((40, 60, 3), dtype=np.uint8)
    ok, enc = cv2.imencode(".jpg", frame)
    evil = "<script>alert(1)</script> & more"
    side = {"wall_sec": 1.0, "answer": evil, "valid": True}
    rows = [{"t": 1.0, "thumb": compare.thumbnail_b64(enc.tobytes(), 30), "local": {640: side}, "remote": {640: side}}]
    summary = {640: {"local_median": 6.0, "remote_median": 1.0, "speedup": 6.0, "local_fps": 0.17, "remote_fps": 1.0}}
    meta = {"source": "clip <b>", "frames": 1, "local_desc": "l", "remote_desc": "r", "rtt_ms": 390.0, "when": "now"}
    page = compare.render_html("t", meta, rows, [640], summary)
    assert "<script>alert(1)</script>" not in page and "&lt;script&gt;" in page
    assert "clip <b>" not in page
