"""Scene-latency distribution benchmark for an Ollama-compatible /api/generate endpoint.

One production-style scene request per distinct image, across max-side conditions run in
rotated order, plus a repeated-image control that quantifies the image-cache effect. An image
is never reused within a condition. Raw records are appended to JSONL as they complete.
"""
import argparse
import base64
import json
import statistics
import sys
import time
from pathlib import Path

import cv2
import numpy as np

from visualintel.engine import SCENE_PROMPT, _http_post_json, resize_encoded_image
from visualintel.structured import FACTUAL_SCHEMA, validate_response

NS = 1e9


def split_rounds(items: list, n_rounds: int = 3) -> list[list]:
    """Contiguous near-equal split; earlier rounds take the remainder."""
    base, extra = divmod(len(items), n_rounds)
    groups, start = [], 0
    for index in range(n_rounds):
        size = base + (1 if index < extra else 0)
        groups.append(items[start:start + size])
        start += size
    return groups


def condition_order(round_index: int, sides: list[int]) -> list[int]:
    """Rotate the condition list so each condition visits every position across rounds."""
    shift = round_index % len(sides)
    return sides[shift:] + sides[:shift]


def summarize(values: list[float]) -> dict:
    if not values:
        return {"n": 0}
    result = {"n": len(values), "median": round(statistics.median(values), 3),
              "min": round(min(values), 3), "max": round(max(values), 3)}
    if len(values) >= 2:
        q1, _, q3 = statistics.quantiles(values, n=4, method="inclusive")
        result["iqr"] = round(q3 - q1, 3)
    return result


def evenly_spaced_indices(total: int, count: int) -> list[int]:
    return [round(i * (total - 1) / (count - 1)) for i in range(count)]


def load_video_frames(video: Path, count: int) -> list[bytes]:
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise FileNotFoundError(f"Cannot open video: {video}")
    try:
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        frames = []
        for index in evenly_spaced_indices(total, count):
            cap.set(cv2.CAP_PROP_POS_FRAMES, index)
            ok, frame = cap.read()
            if not ok:
                raise RuntimeError(f"Cannot decode frame {index}")
            ok, encoded = cv2.imencode(".jpg", frame)
            if not ok:
                raise RuntimeError(f"Cannot encode frame {index}")
            frames.append(encoded.tobytes())
        return frames
    finally:
        cap.release()


def request_once(base_url: str, model: str, jpeg: bytes, timeout: int,
                 num_thread: int | None = None) -> dict:
    payload = {
        "model": model, "prompt": SCENE_PROMPT, "stream": False, "think": False,
        "images": [base64.b64encode(jpeg).decode("ascii")],
        "format": FACTUAL_SCHEMA,
        "options": {"temperature": 0, "seed": 42, "num_predict": 96},
    }
    if num_thread is not None:
        payload["options"]["num_thread"] = num_thread
    record = {"jpeg_bytes": len(jpeg)}
    started = time.perf_counter()
    try:
        result = _http_post_json(f"{base_url}/api/generate", payload, timeout)
        record["wall_sec"] = round(time.perf_counter() - started, 3)
        for key in ("total_duration", "load_duration", "prompt_eval_duration", "eval_duration"):
            if key in result:
                record[key.replace("_duration", "_sec")] = round(result[key] / NS, 3)
        for key in ("prompt_eval_count", "eval_count", "done_reason"):
            if key in result:
                record[key] = result[key]
        record["response"] = result.get("response", "")
        try:
            validate_response(json.loads(record["response"]), FACTUAL_SCHEMA)
            record["valid"] = True
        except Exception as error:
            record["valid"] = False
            record["validation_error"] = str(error)
    except Exception as error:
        record["wall_sec"] = round(time.perf_counter() - started, 3)
        record["error"] = repr(error)
        record["valid"] = False
    return record


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", type=Path, default=Path("videos/test_video.avi"))
    parser.add_argument("--images", type=Path, nargs="+", default=None,
                        help="Use these image files (first is warm-up) instead of video frames; "
                             "required for any remote endpoint so personal frames never leave the machine")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base-url", default="http://localhost:11434")
    parser.add_argument("--model", default="minicpm-v4.6")
    parser.add_argument("--sides", type=int, nargs="+", default=[640, 480, 320])
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--timed-frames", type=int, default=12)
    parser.add_argument("--repeat-control", type=int, default=5)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--num-thread", type=int, default=None,
                        help="Explicit Ollama num_thread (default: let Ollama choose). Changing it "
                             "reloads the runner, which also clears the image cache")
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "frames").mkdir()
    if args.images:
        frames = [path.read_bytes() for path in args.images]
        if len(frames) < args.rounds + 1:
            parser.error("need at least rounds+1 images (one warm-up plus one per round)")
    else:
        frames = load_video_frames(args.video, args.timed_frames + 1)
    warmup, timed = frames[0], frames[1:]
    for index, jpeg in enumerate([warmup] + timed):
        (args.output / "frames" / f"{'warmup' if index == 0 else f'F{index - 1:02d}'}.jpg").write_bytes(jpeg)

    records_path = args.output / "records.jsonl"
    config = {"base_url": args.base_url, "model": args.model, "sides": args.sides,
              "rounds": args.rounds, "timed_inputs": len(timed), "repeat_control": args.repeat_control,
              "num_thread": args.num_thread, "started": time.strftime("%Y-%m-%d %H:%M:%S")}
    (args.output / "config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    records = []

    def run(kind: str, side: int | None, frame_index: int | None, jpeg: bytes, **extra) -> dict:
        prepared = resize_encoded_image(jpeg, side) if side else jpeg
        record = {"kind": kind, "side": side, "frame": frame_index, **extra}
        record.update(request_once(args.base_url, args.model, prepared, args.timeout, args.num_thread))
        with records_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        records.append(record)
        print(json.dumps({k: record.get(k) for k in ("kind", "side", "frame", "wall_sec",
                          "prompt_eval_count", "eval_count", "valid")}, ensure_ascii=False), flush=True)
        return record

    run("warmup", args.sides[0], None, warmup)
    groups = split_rounds(list(range(len(timed))), args.rounds)
    for round_index, frame_ids in enumerate(groups):
        for side in condition_order(round_index, args.sides):
            for frame_id in frame_ids:
                run("timed", side, frame_id, timed[frame_id], round=round_index)
    for repeat in range(args.repeat_control):
        run("repeat-control", args.sides[0], 0, timed[0], repeat=repeat)

    summary = {"config": config, "per_side": {}}
    for side in args.sides:
        rows = [r for r in records if r["kind"] == "timed" and r["side"] == side and "error" not in r]
        summary["per_side"][str(side)] = {
            "wall_sec": summarize([r["wall_sec"] for r in rows]),
            "prompt_eval_sec": summarize([r["prompt_eval_sec"] for r in rows if "prompt_eval_sec" in r]),
            "eval_sec": summarize([r["eval_sec"] for r in rows if "eval_sec" in r]),
            "prompt_eval_count": summarize([r["prompt_eval_count"] for r in rows if "prompt_eval_count" in r]),
            "eval_count": summarize([r["eval_count"] for r in rows if "eval_count" in r]),
            "jpeg_bytes": summarize([r["jpeg_bytes"] for r in rows]),
            "valid": f"{sum(r['valid'] for r in rows)}/{len(rows)}",
            "errors": sum(1 for r in records if r["kind"] == "timed" and r["side"] == side and "error" in r),
        }
    repeats = [r for r in records if r["kind"] == "repeat-control" and "error" not in r]
    summary["repeat_control_wall_sec"] = [r["wall_sec"] for r in repeats]
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return int(any("error" in r for r in records))


if __name__ == "__main__":
    raise SystemExit(main())
