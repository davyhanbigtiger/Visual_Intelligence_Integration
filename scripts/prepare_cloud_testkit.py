"""Prepare test media for cloud GPU runs so a rented instance is not billed while we fetch files.

Public images/videos come from the pinned sources in scripts/testkit_sources.json; deterministic
synthetic images and a synthetic video come with machine-checkable ground truth. Everything is
written under --out (default outputs/testkit-cloud, gitignored); only the sources manifest is
committed, never the media. None of this media is personal: do not add camera frames here.
"""
import argparse
import hashlib
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import cv2
import numpy as np

DEFAULT_MAX_BYTES = 30 * 1024 * 1024
PALETTE = {"red": (0, 0, 255), "green": (0, 160, 0), "blue": (255, 0, 0),
           "yellow": (0, 220, 255), "black": (20, 20, 20)}
BACKGROUND = (235, 235, 235)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_url(url: str) -> str:
    """Upgrade http to https; refuse any other scheme or a missing host."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError(f"Refusing non-web URL: {url}")
    return urllib.parse.urlunparse(parsed._replace(scheme="https"))


def download(url: str, dest: Path, max_bytes: int) -> dict:
    url = normalize_url(url)
    request = urllib.request.Request(url, headers={"User-Agent": "visualintel-testkit/0.1"})
    partial = dest.with_suffix(dest.suffix + ".part")
    total = 0
    digest = hashlib.sha256()
    try:
        with urllib.request.urlopen(request, timeout=60) as response, partial.open("wb") as handle:
            while True:
                chunk = response.read(1 << 20)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise ValueError(f"{url} exceeds the {max_bytes} byte cap")
                digest.update(chunk)
                handle.write(chunk)
        partial.replace(dest)
    except Exception:
        partial.unlink(missing_ok=True)
        raise
    return {"bytes": total, "sha256": digest.hexdigest()}


def make_synthetic_image(index: int, seed: int) -> tuple[np.ndarray, dict]:
    """640x480 canvas with index+1 non-overlapping filled circles of known colors."""
    rng = np.random.default_rng(seed + index)
    canvas = np.full((480, 640, 3), BACKGROUND, dtype=np.uint8)
    count = index + 1
    cells = rng.permutation(12)[:count]  # 4x3 grid cells guarantee no overlap
    names = list(PALETTE)
    colors = []
    for cell in cells:
        name = names[int(rng.integers(len(names)))]
        colors.append(name)
        cx, cy = (int(cell) % 4) * 160 + 80, (int(cell) // 4) * 160 + 80
        cv2.circle(canvas, (cx, cy), 50, PALETTE[name], -1)
    return canvas, {"circles": count, "colors": {c: colors.count(c) for c in sorted(set(colors))}}


def write_synthetic_video(path: Path, seconds: int = 10, fps: int = 15) -> dict:
    """Red circle moves left to right; blue square moves top to bottom."""
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"XVID"), float(fps), (640, 480))
    frames = seconds * fps
    for n in range(frames):
        t = n / (frames - 1)
        canvas = np.full((480, 640, 3), BACKGROUND, dtype=np.uint8)
        cv2.circle(canvas, (int(60 + t * 520), 160), 30, PALETTE["red"], -1)
        cx, cy = 480, int(40 + t * 400)
        cv2.rectangle(canvas, (cx - 30, cy - 30), (cx + 30, cy + 30), PALETTE["blue"], -1)
        writer.write(canvas)
    writer.release()
    return {"frames": frames, "fps": fps, "objects": [
        {"shape": "circle", "color": "red", "motion": "left_to_right"},
        {"shape": "square", "color": "blue", "motion": "top_to_bottom"}]}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", type=Path, default=Path("scripts/testkit_sources.json"))
    parser.add_argument("--out", type=Path, default=Path("outputs/testkit-cloud"))
    parser.add_argument("--no-download", action="store_true", help="Only build the synthetic media")
    args = parser.parse_args()

    spec = json.loads(args.sources.read_text(encoding="utf-8"))
    cap = int(spec.get("max_file_mb", 30)) * 1024 * 1024
    for sub in ("images", "videos", "synthetic"):
        (args.out / sub).mkdir(parents=True, exist_ok=True)
    lock_path = args.out / "manifest.lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8")) if lock_path.exists() else {"files": {}}
    problems = 0

    if not args.no_download:
        for kind in ("images", "videos"):
            for item in spec[kind]:
                dest = args.out / kind / item["name"]
                key = f"{kind}/{item['name']}"
                known = lock["files"].get(key)
                if dest.exists() and known:
                    if sha256_file(dest) != known["sha256"]:
                        print(f"MISMATCH {key}: file differs from the recorded sha256; not overwriting")
                        problems += 1
                    continue
                try:
                    info = download(item["url"], dest, cap)
                except Exception as error:
                    print(f"FAILED {key}: {error}")
                    problems += 1
                    continue
                lock["files"][key] = {"url": item["url"], "source": item["source"], **info}
                print(f"ok {key} {info['bytes'] / 1e6:.2f} MB")

    labels = {"images": {}, "video": None}
    for index in range(int(spec["synthetic"]["images"])):
        image, label = make_synthetic_image(index, int(spec["synthetic"]["seed"]))
        name = f"synthetic-circles-{index + 1}.png"
        cv2.imwrite(str(args.out / "synthetic" / name), image)
        labels["images"][name] = label
    labels["video"] = {"synthetic/moving-shapes.avi":
                       write_synthetic_video(args.out / "synthetic" / "moving-shapes.avi")}
    (args.out / "synthetic" / "labels.json").write_text(json.dumps(labels, indent=2), encoding="utf-8")

    lock["generated"] = time.strftime("%Y-%m-%d %H:%M:%S")
    lock_path.write_text(json.dumps(lock, indent=2), encoding="utf-8")
    sizes = [p.stat().st_size for p in args.out.rglob("*") if p.is_file()]
    print(f"testkit at {args.out}: {len(sizes)} files, {sum(sizes) / 1e6:.1f} MB, problems={problems}")
    return 2 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
