"""Headless acceptance harness mirroring the `camera` demo's continuous mode.

Reproduces the demo's loop (take the newest frame, one outstanding analysis, wait 2 s, repeat)
using the production `analyze_frame`, records per-cycle timing and result age, and runs six
synthetic degraded inputs to check whether the model invents content for images that have none.
Frames are saved only under the --output directory (gitignored); nothing is uploaded anywhere.
"""
import argparse
import json
import statistics
import sys
import time
from pathlib import Path

import cv2
import numpy as np

from visualintel.camera import analyze_frame

BACKENDS = {"dshow": cv2.CAP_DSHOW, "msmf": cv2.CAP_MSMF, "auto": cv2.CAP_ANY}


def make_synthetic_inputs(frame: np.ndarray) -> dict[str, np.ndarray]:
    """Degraded variants. black/noise/white contain no scene; the others derive from a real frame."""
    height, width = frame.shape[:2]
    occluded = frame.copy()
    occluded[:, width // 2:] = 0
    return {
        "black": np.zeros_like(frame),
        "dark_5pct": (frame.astype(np.float32) * 0.05).astype(np.uint8),
        "blur_k61": cv2.GaussianBlur(frame, (61, 61), 0),
        "right_half_occluded": occluded,
        "noise": np.random.default_rng(0).integers(0, 256, size=frame.shape, dtype=np.uint8),
        "white": np.full_like(frame, 255),
    }


def open_camera(index: int, backend: str):
    for name in ([backend] + [b for b in ("dshow", "msmf") if b != backend]):
        cap = cv2.VideoCapture(index, BACKENDS[name])
        if cap.isOpened():
            return cap, name
        cap.release()
    return None, None


def flush_and_read(cap, flush: int):
    frame = None
    for _ in range(flush):
        ok, candidate = cap.read()
        if ok:
            frame = candidate
        time.sleep(0.03)
    return frame


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cycles", type=int, default=12)
    parser.add_argument("--index", type=int, default=0)
    parser.add_argument("--backend", choices=list(BACKENDS), default="dshow")
    parser.add_argument("--model", default="minicpm-v4.6")
    parser.add_argument("--max-side", type=int, default=640)
    parser.add_argument("--wait", type=float, default=2.0)
    parser.add_argument("--flush", type=int, default=8)
    parser.add_argument("--max-saved", type=int, default=12)
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "frames").mkdir()
    records_path = args.output / "records.jsonl"

    def log(record: dict) -> None:
        with records_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        print(json.dumps({k: v for k, v in record.items() if k != "answer"}, ensure_ascii=False), flush=True)

    cap, used = open_camera(args.index, args.backend)
    if cap is None:
        log({"kind": "camera", "error": "could not open camera with dshow or msmf"})
        return 2
    last_real = None
    try:
        for cycle in range(args.cycles):
            frame = flush_and_read(cap, args.flush)
            if frame is None:
                log({"kind": "live", "cycle": cycle, "error": "no frame read"})
                continue
            last_real = frame
            captured = time.monotonic()
            if cycle < args.max_saved:
                cv2.imwrite(str(args.output / "frames" / f"live-{cycle:02d}.jpg"), frame)
            record = {"kind": "live", "cycle": cycle, "backend": used}
            started = time.monotonic()
            try:
                record["answer"] = analyze_frame(frame, args.model, args.max_side)
                record["ok"] = True
            except Exception as error:
                record["ok"] = False
                record["error"] = repr(error)
            finished = time.monotonic()
            record["call_sec"] = round(finished - started, 3)
            record["result_age_sec"] = round(finished - captured, 3)
            log(record)
            time.sleep(args.wait)
        if last_real is not None:
            for name, image in make_synthetic_inputs(last_real).items():
                cv2.imwrite(str(args.output / "frames" / f"synthetic-{name}.jpg"), image)
                record = {"kind": "synthetic", "name": name}
                started = time.monotonic()
                try:
                    record["answer"] = analyze_frame(image, args.model, args.max_side)
                    record["ok"] = True
                except Exception as error:
                    record["ok"] = False
                    record["error"] = repr(error)
                record["call_sec"] = round(time.monotonic() - started, 3)
                log(record)
    finally:
        cap.release()
    released = not cap.isOpened()
    rows = [json.loads(line) for line in records_path.read_text(encoding="utf-8").splitlines()]
    calls = [r["call_sec"] for r in rows if r["kind"] == "live" and r.get("ok")]
    summary = {"camera_released": released, "live_ok": len(calls),
               "live_failed": sum(1 for r in rows if r["kind"] == "live" and not r.get("ok", False)),
               "call_sec_median": round(statistics.median(calls), 3) if calls else None,
               "call_sec_min": min(calls) if calls else None, "call_sec_max": max(calls) if calls else None}
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
