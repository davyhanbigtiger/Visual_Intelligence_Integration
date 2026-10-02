import argparse
import concurrent.futures
import math
import sys
from pathlib import Path

import cv2

from visualintel.engine import (
    EngineNotReadyError,
    ModelCallError,
    analyze_chunk,
    answer_question,
    check_ollama_ready,
    describe_scene,
)
from visualintel.report import build_report, save_report
from visualintel.sampling import ChunkPlan, plan_chunks, plan_single_chunk_over_video

DEFAULT_MODEL = "minicpm-v4.6"


def _video_fps_and_frame_count(video_path: str) -> tuple[float, int]:
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise FileNotFoundError(f"Cannot open video: {video_path}")
    try:
        fps = cap.get(cv2.CAP_PROP_FPS)
        count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        if not math.isfinite(fps) or fps <= 0 or not math.isfinite(count) or count <= 0:
            raise ValueError(f"Invalid video metadata: {video_path}")
        total_frames = int(count)
    finally:
        cap.release()
    return fps, total_frames


MAX_CONCURRENT_CHUNKS = 4  # measured sweet spot via llama-server/SYCL on this
# machine's iGPU (see docs/benchmark-matrix.md "并发实验结论": 4 concurrent
# requests gave a 5.05x throughput win over sequential, 8 was *worse* than 4
# due to GPU contention). This run targets Ollama per the approved spec —
# the optimal concurrency for Ollama's CPU-bound vision encoder path hasn't
# been separately measured and may differ; 4 is a reasonable starting point,
# not verified optimal for this specific backend.


def cmd_report(video_path: str, output_dir: str, model: str = DEFAULT_MODEL,
               max_chunks: int = 20, workers: int = MAX_CONCURRENT_CHUNKS) -> int:
    fps, total_frames = _video_fps_and_frame_count(video_path)
    check_ollama_ready(model=model)
    if any((Path(output_dir) / name).exists() for name in ("report.json", "report.md")):
        raise FileExistsError(f"Report already exists in {output_dir}; choose a new --output-dir")
    if max_chunks == 20:
        chunks, truncated = plan_chunks(total_frames, fps)
    else:
        chunks, truncated = plan_chunks(total_frames, fps, max_chunks=max_chunks)
    if not chunks:
        print(f"ERROR: no frames could be sampled from {video_path}", file=sys.stderr)
        return 1

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        results = list(ex.map(lambda c: analyze_chunk(video_path, c, model=model), chunks))
    duration_sec = total_frames / fps if fps else 0.0
    report = build_report(video_path, duration_sec, truncated, results)
    json_path, md_path = save_report(report, output_dir)
    print(f"Report written to {json_path} and {md_path}")
    failed = sum(c.status == "failed" for c in results)
    if failed:
        print(f"ERROR: {failed}/{len(results)} chunks failed; see report for details", file=sys.stderr)
        return 3
    return 0


def cmd_ask(video_path: str, question: str, model: str = DEFAULT_MODEL,
            question_mode: str = "auto") -> int:
    fps, total_frames = _video_fps_and_frame_count(video_path)
    check_ollama_ready(model=model)
    chunk = plan_single_chunk_over_video(total_frames, fps)
    if not chunk.frame_indices:
        print(f"ERROR: no frames could be sampled from {video_path}", file=sys.stderr)
        return 1

    answer = answer_question(video_path, chunk, question, model=model, question_mode=question_mode)
    print(answer)
    return 0


def cmd_scene(video_path: str, model: str = DEFAULT_MODEL, at: float | None = None) -> int:
    fps, total_frames = _video_fps_and_frame_count(video_path)
    if at is not None and (not math.isfinite(at) or at < 0 or at >= total_frames / fps):
        raise ValueError("--at must be a finite time within the video, in seconds")
    index = (total_frames - 1) // 2 if at is None else min(int(at * fps), total_frames - 1)
    check_ollama_ready(model=model)
    timestamp = index / fps
    print(f"Sampled instant: {timestamp:.2f}s (one frame; not a whole-video summary)")
    print(describe_scene(video_path, ChunkPlan(0, [index], timestamp, timestamp), model=model))
    return 0


def _positive_int(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return number


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="visualintel")
    sub = parser.add_subparsers(dest="command", required=True)

    camera_p = sub.add_parser("camera", help="Local live camera preview and scene analysis")
    camera_p.add_argument("--index", type=int, default=0)
    camera_p.add_argument("--model", default=DEFAULT_MODEL)
    camera_p.add_argument("--max-image-side", type=_positive_int, default=640)
    camera_p.add_argument("--backend", choices=("dshow", "msmf", "auto"), default="dshow")

    scene_p = sub.add_parser("scene", help="Brief environment overview from one sampled frame")
    scene_p.add_argument("video")
    scene_p.add_argument("--model", default=DEFAULT_MODEL)
    scene_p.add_argument("--at", type=float, default=None, help="Time in seconds; default is video midpoint")

    report_p = sub.add_parser("report", help="Generate an understanding report for a video")
    report_p.add_argument("video", help="Path to the video file")
    report_p.add_argument("--output-dir", default=None, help="Where to write report.json/report.md")
    report_p.add_argument("--model", default=DEFAULT_MODEL)
    report_p.add_argument("--max-chunks", type=_positive_int, default=20)
    report_p.add_argument("--workers", type=_positive_int, default=MAX_CONCURRENT_CHUNKS)

    ask_p = sub.add_parser("ask", help="Ask a question about a video")
    ask_p.add_argument("video")
    ask_p.add_argument("question")
    ask_p.add_argument("--model", default=DEFAULT_MODEL)
    ask_p.add_argument("--question-mode", choices=("auto", "factual", "advice"), default="auto",
                       help="Override automatic factual/advice question classification")

    args = parser.parse_args(argv)

    try:
        if args.command == "camera":
            if args.index < 0:
                raise ValueError("--index must be nonnegative")
            from visualintel.camera import run_camera
            return run_camera(args.index, args.model, args.max_image_side, args.backend)
        if args.command == "scene":
            return cmd_scene(args.video, model=args.model, at=args.at)
        if args.command == "report":
            output_dir = args.output_dir or str(Path("outputs") / Path(args.video).stem)
            return cmd_report(args.video, output_dir, model=args.model,
                              max_chunks=args.max_chunks, workers=args.workers)
        elif args.command == "ask":
            return cmd_ask(args.video, args.question, model=args.model, question_mode=args.question_mode)
    except EngineNotReadyError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    except ModelCallError as e:
        print(f"ERROR: model call failed: {e}", file=sys.stderr)
        return 3
    except (OSError, ValueError, cv2.error) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":
    sys.exit(main())
