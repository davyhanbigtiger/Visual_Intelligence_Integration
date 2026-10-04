"""Send the same video frames to a local server and to the remote GPU, and show what each answers and how long it takes.

Frames are interleaved (local, remote, local, remote ...) so both see the same moment of the video and the
same machine/network conditions. Both endpoints are OpenAI-compatible llama-server instances reached on
loopback addresses (the remote one through the SSH tunnel). Output: report.html (self-contained, thumbnails
embedded), results.json.

Privacy guard: if the remote endpoint is used, the video must be one of the public testkit videos recorded in
manifest.lock.json with a matching sha256. A personal video or a webcam can only be run with --local-only.
"""
import argparse
import base64
import html
import json
import statistics
import sys
import time
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_cloud_suite import Ctx, check_loopback, request_model, sha256_bytes  # noqa: E402
from visualintel.engine import resize_encoded_image  # noqa: E402


def verify_public_video(video: Path, kit: Path) -> None:
    """Refuse to send a video to a remote server unless the testkit lock vouches for these exact bytes."""
    lock_path = kit / "manifest.lock.json"
    if not lock_path.exists():
        raise ValueError(f"{kit} has no manifest.lock.json; refusing to send any video remotely")
    files = json.loads(lock_path.read_text(encoding="utf-8"))["files"]
    # The generated synthetic video is deterministic and carries its own labels; it is not in the download lock.
    labels_path = kit / "synthetic" / "labels.json"
    synthetic = json.loads(labels_path.read_text(encoding="utf-8")).get("video") or {} if labels_path.exists() else {}
    try:
        if video.resolve().parent == (kit / "synthetic").resolve() and f"synthetic/{video.name}" in synthetic:
            return
        inside = video.resolve().parent == (kit / "videos").resolve()
    except OSError:
        inside = False
    key = f"videos/{video.name}"
    if not inside or key not in files:
        raise ValueError(f"{video} is not a recorded public testkit video; use --local-only for other media")
    if sha256_bytes(video) != files[key]["sha256"]:
        raise ValueError(f"{video.name} differs from its recorded sha256; refusing to send it")


def sample_frames(video: Path, count: int) -> list[tuple[float, bytes]]:
    """Evenly spaced (timestamp_sec, jpeg) pairs, never the very first or last frame."""
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise FileNotFoundError(f"Cannot open video: {video}")
    try:
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        frames = []
        for i in range(count):
            index = round((i + 1) * (total - 1) / (count + 1))
            cap.set(cv2.CAP_PROP_POS_FRAMES, index)
            ok, frame = cap.read()
            if not ok:
                raise RuntimeError(f"Cannot decode frame {index}")
            ok, encoded = cv2.imencode(".jpg", frame)
            if not ok:
                raise RuntimeError(f"Cannot encode frame {index}")
            frames.append((index / fps, encoded.tobytes()))
        return frames
    finally:
        cap.release()


def answer_text(record: dict) -> str:
    if "error" in record:
        return f"[error] {record['error']}"
    try:
        return json.loads(record["response"])["answer"]
    except Exception:
        return f"[invalid JSON] {record.get('response', '')[:160]}"


def thumbnail_b64(jpeg: bytes, width: int = 280) -> str:
    frame = cv2.imdecode(__import__("numpy").frombuffer(jpeg, dtype="uint8"), cv2.IMREAD_COLOR)
    height = max(1, round(frame.shape[0] * width / frame.shape[1]))
    ok, small = cv2.imencode(".jpg", cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA))
    return base64.b64encode(small.tobytes()).decode("ascii")


def image_size_label(jpeg: bytes) -> str:
    frame = cv2.imdecode(__import__("numpy").frombuffer(jpeg, dtype="uint8"), cv2.IMREAD_COLOR)
    return f"{frame.shape[1]}×{frame.shape[0]}"


def effective_sides(first_frame: bytes, sides: list[int]) -> tuple[list[int], dict[int, str]]:
    """Drop size settings that would send the same pixels as an earlier one (the engine never upscales),
    and label each remaining setting with the real image size."""
    kept, labels, seen = [], {}, set()
    for side in sides:
        prepared = resize_encoded_image(first_frame, side)
        if prepared in seen:
            continue
        seen.add(prepared)
        kept.append(side)
        labels[side] = image_size_label(prepared)
    return kept, labels


def render_html(title: str, meta: dict, rows: list[dict], sides: list[int], summary: dict,
                labels: dict[int, str] | None = None) -> str:
    esc = html.escape
    labels = labels or {s: f"{s} 档" for s in sides}
    head = "".join(f"<th>本机 · {esc(labels[s])}</th><th>远程 T4 · {esc(labels[s])}</th>" for s in sides)
    body = []
    for row in rows:
        cells = "".join(
            f"<td><div class='lat'>{row['local'][s]['wall_sec']:.2f} 秒</div>{esc(row['local'][s]['answer'])}</td>"
            f"<td><div class='lat remote'>{row['remote'][s]['wall_sec']:.2f} 秒</div>{esc(row['remote'][s]['answer'])}</td>"
            for s in sides)
        body.append(f"<tr><td class='frame'><img src='data:image/jpeg;base64,{row['thumb']}' alt='frame'>"
                    f"<div>{row['t']:.1f} 秒</div></td>{cells}</tr>")
    stats = "".join(
        f"<li><b>{esc(labels[s])}</b>:本机中位 {summary[s]['local_median']:.2f} 秒,远程中位 {summary[s]['remote_median']:.2f} 秒,"
        f"约 {summary[s]['speedup']:.1f} 倍;单路连续处理上限约 本机 {summary[s]['local_fps']:.2f} 帧/秒、"
        f"远程 {summary[s]['remote_fps']:.2f} 帧/秒</li>" for s in sides)
    return f"""<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)}</title>
<style>
:root{{--bg:#fff;--fg:#1d2125;--mut:#5b6670;--line:#d9dee3;--acc:#0b6bcb;--rem:#0a7a4b}}
@media (prefers-color-scheme:dark){{:root{{--bg:#14171a;--fg:#e8ebee;--mut:#9aa5af;--line:#2d343a;--acc:#6db3ff;--rem:#52d19a}}}}
body{{margin:0;padding:16px;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif}}
h1{{font-size:20px;margin:0 0 4px}} .meta{{color:var(--mut);font-size:13px;margin-bottom:12px}}
table{{border-collapse:collapse;width:100%}} th,td{{border:1px solid var(--line);padding:8px;vertical-align:top;text-align:left}}
th{{font-size:13px;color:var(--mut)}} .frame{{width:290px}} .frame img{{width:100%;display:block;border-radius:4px}}
.lat{{font-weight:600;color:var(--acc)}} .lat.remote{{color:var(--rem)}} .wrap{{overflow-x:auto}}
</style></head><body>
<h1>{esc(title)}</h1>
<div class="meta">{esc(meta['source'])} · {meta['frames']} 帧 · 本机:{esc(meta['local_desc'])} · 远程:{esc(meta['remote_desc'])}
 · 往返(GET)中位 {meta['rtt_ms']:.0f} 毫秒 · 生成于 {esc(meta['when'])}</div>
<ul>{stats}</ul>
<div class="wrap"><table><thead><tr><th>画面</th>{head}</tr></thead><tbody>{''.join(body)}</tbody></table></div>
<p class="meta">延迟是客户端墙钟时间(含网络与图片上传)。描述为模型原文,未经人工校对。</p>
</body></html>"""


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--video", type=Path, default=ROOT / "outputs/testkit-cloud/videos/nasa-crew4-science.mp4")
    p.add_argument("--kit", type=Path, default=ROOT / "outputs/testkit-cloud")
    p.add_argument("--local-url", default="http://127.0.0.1:18937")
    p.add_argument("--remote-url", default="http://127.0.0.1:28080")
    p.add_argument("--local-desc", default="Iris Xe 核显 · llama.cpp(SYCL)")
    p.add_argument("--remote-desc", default="腾讯云东京 Tesla T4 · llama.cpp(CUDA)· SSH 隧道")
    p.add_argument("--frames", type=int, default=10)
    p.add_argument("--sides", type=int, nargs="+", default=[640, 448])
    p.add_argument("--local-only", action="store_true", help="skip the remote endpoint; allows any video")
    p.add_argument("--output", type=Path, default=None)
    args = p.parse_args()

    local_url = check_loopback(args.local_url)
    remote_url = None if args.local_only else check_loopback(args.remote_url)
    if remote_url:
        verify_public_video(args.video, args.kit)
    out = args.output or ROOT / "outputs" / f"compare-local-remote-{time.strftime('%Y%m%d-%H%M%S')}"
    out.mkdir(parents=True, exist_ok=False)
    ctx_local = Ctx("openai", local_url, 240, out / "records.jsonl")
    ctx_remote = Ctx("openai", remote_url, 240, out / "records.jsonl") if remote_url else None

    frames = sample_frames(args.video, args.frames + 1)
    warm, timed = frames[0][1], frames[1:]
    requested = list(args.sides)
    args.sides, labels = effective_sides(warm, requested)
    if args.sides != requested:
        print(f"note: sizes {sorted(set(requested) - set(args.sides))} would send the same pixels as "
              f"{args.sides} for this video (source is {image_size_label(warm)}); kept only {args.sides}", flush=True)
    for ctx in (ctx_local, ctx_remote):  # warm-up with a frame that is not part of the timed set
        if ctx:
            request_model(ctx, "minicpm-v4.6", resize_encoded_image(warm, args.sides[0]))

    rtts = []
    if remote_url:
        import urllib.request
        for _ in range(10):
            t = time.perf_counter()
            urllib.request.urlopen(remote_url + "/health", timeout=10).read()
            rtts.append((time.perf_counter() - t) * 1000)

    rows = []
    for t_sec, jpeg in timed:
        row = {"t": t_sec, "thumb": thumbnail_b64(jpeg), "local": {}, "remote": {}}
        for side in args.sides:
            prepared = resize_encoded_image(jpeg, side)
            for name, ctx in (("local", ctx_local), ("remote", ctx_remote)):
                if not ctx:
                    continue
                rec = request_model(ctx, "minicpm-v4.6", prepared)
                row[name][side] = {"wall_sec": rec["wall_sec"], "answer": answer_text(rec), "valid": rec["valid"]}
                with ctx.records_path.open("a", encoding="utf-8") as h:
                    h.write(json.dumps({"endpoint": name, "t": round(t_sec, 2), "side": side,
                                        "wall_sec": rec["wall_sec"], "valid": rec["valid"],
                                        "answer": row[name][side]["answer"]}, ensure_ascii=False) + "\n")
                print(f"t={t_sec:5.1f}s side={side} {name:6s} {rec['wall_sec']:6.2f}s valid={rec['valid']}", flush=True)
        rows.append(row)

    summary = {}
    if remote_url:
        for side in args.sides:
            lm = statistics.median(r["local"][side]["wall_sec"] for r in rows)
            rm = statistics.median(r["remote"][side]["wall_sec"] for r in rows)
            summary[side] = {"local_median": lm, "remote_median": rm, "speedup": lm / rm,
                             "local_fps": 1 / lm, "remote_fps": 1 / rm}
        meta = {"source": f"视频 {args.video.name}(公开测试集)", "frames": len(rows), "local_desc": args.local_desc,
                "remote_desc": args.remote_desc, "rtt_ms": statistics.median(rtts),
                "when": time.strftime("%Y-%m-%d %H:%M")}
        (out / "report.html").write_text(render_html("本机 vs 远程 T4:同一批视频帧", meta, rows, args.sides, summary, labels),
                                         encoding="utf-8")
    (out / "results.json").write_text(json.dumps(
        {"video": args.video.name, "sides": args.sides, "size_labels": labels, "summary": summary,
         "rows": [{k: v for k, v in r.items() if k != "thumb"} for r in rows]}, indent=2, ensure_ascii=False),
        encoding="utf-8")
    print(f"\nresults: {out}")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
