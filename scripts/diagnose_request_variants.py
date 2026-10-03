"""Isolate which part of a request makes Ollama slow: prompt style, JSON-schema constraint, or machine state.

Variants run against the same loaded model on distinct, never-reused frames:
  A  old-style  : short yes/no question, num_predict=5, no JSON format   (the 2026-09-29 test shape)
  B  scene      : production SCENE_PROMPT, temperature 0 / seed 42 / num_predict 96, no JSON format
  C  production : B plus format=FACTUAL_SCHEMA
Blocks run A, B, C, A (the second A checks for drift from thermal state or order).
"""
import argparse
import base64
import json
import statistics
import sys
import time
from pathlib import Path

import cv2

from visualintel.engine import SCENE_PROMPT, _http_post_json
from visualintel.structured import FACTUAL_SCHEMA

NS = 1e9
BLOCKS = [("A", [8, 22, 37, 52]), ("B", [66, 81, 96, 111]), ("C", [126, 141, 155, 170]), ("A2", [3, 12, 28, 43])]
WARMUP_INDEX = 2


def payload_for(variant: str, jpeg: bytes, model: str) -> dict:
    payload = {"model": model, "stream": False, "think": False,
               "images": [base64.b64encode(jpeg).decode("ascii")]}
    if variant.startswith("A"):
        payload["prompt"] = "Answer yes or no: is there a person here?"
        payload["options"] = {"num_predict": 5}
    else:
        payload["prompt"] = SCENE_PROMPT
        payload["options"] = {"temperature": 0, "seed": 42, "num_predict": 96}
        if variant == "C":
            payload["format"] = FACTUAL_SCHEMA
    return payload


def read_frame(cap, index: int) -> bytes:
    cap.set(cv2.CAP_PROP_POS_FRAMES, index)
    ok, frame = cap.read()
    if not ok:
        raise RuntimeError(f"cannot read frame {index}")
    ok, encoded = cv2.imencode(".jpg", frame)
    return encoded.tobytes()


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", type=Path, default=Path("videos/test_video.avi"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default="minicpm-v4.6")
    parser.add_argument("--base-url", default="http://localhost:11434")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    cap = cv2.VideoCapture(str(args.video))
    records = []

    def call(variant: str, index: int, kind: str) -> None:
        jpeg = read_frame(cap, index)
        started = time.perf_counter()
        result = _http_post_json(f"{args.base_url}/api/generate", payload_for(variant, jpeg, args.model), 180)
        record = {"variant": variant, "kind": kind, "frame": index,
                  "wall_sec": round(time.perf_counter() - started, 3),
                  "prompt_eval_sec": round(result.get("prompt_eval_duration", 0) / NS, 3),
                  "eval_sec": round(result.get("eval_duration", 0) / NS, 3),
                  "load_sec": round(result.get("load_duration", 0) / NS, 3),
                  "prompt_eval_count": result.get("prompt_eval_count"), "eval_count": result.get("eval_count"),
                  "response": result.get("response", "")[:200]}
        records.append(record)
        with (args.output / "records.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        print(json.dumps({k: record[k] for k in ("variant", "kind", "frame", "wall_sec", "prompt_eval_sec",
                                                    "prompt_eval_count", "eval_count")}), flush=True)

    call("A", WARMUP_INDEX, "warmup")
    for variant, indices in BLOCKS:
        for index in indices:
            call(variant, index, "timed")
    cap.release()
    summary = {}
    for variant, _ in BLOCKS:
        rows = [r for r in records if r["variant"] == variant and r["kind"] == "timed"]
        summary[variant] = {"wall_median": round(statistics.median(r["wall_sec"] for r in rows), 3),
                            "wall_min": min(r["wall_sec"] for r in rows),
                            "wall_max": max(r["wall_sec"] for r in rows),
                            "prompt_eval_median": round(statistics.median(r["prompt_eval_sec"] for r in rows), 3),
                            "prompt_eval_count": sorted({r["prompt_eval_count"] for r in rows})}
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
