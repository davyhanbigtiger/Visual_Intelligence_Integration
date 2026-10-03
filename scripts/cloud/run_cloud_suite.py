"""Client-side test suite for a rented GPU instance, run from the laptop through an SSH tunnel.

Prerequisites: scripts/prepare_cloud_testkit.py has built outputs/testkit-cloud, and
scripts/cloud/setup_server.sh has been run on the instance, with the tunnel open:
  ssh -N -L 11434:127.0.0.1:11434 -L 8080:127.0.0.1:8080 -i <dedicated_key> -p <port> <user>@<host>

Safety rules enforced in code, not just in the runbook:
* Only media from the testkit is ever sent (COCO images are re-verified against manifest.lock.json
  sha256, synthetic images must be listed in labels.json). There is no option to point at other files,
  so webcam frames or videos/test_video.avi cannot be uploaded by this script.
* Base URLs must be loopback (the SSH tunnel). A non-loopback host needs --allow-nonloopback.
* A test stops after 3 consecutive request errors so a broken server does not burn paid hours.

Tests (--tests): t0 probe/RTT, t1 latency by model x image size, t2 concurrency, t3 synthetic-counting
accuracy, t4 cold start (Ollama only). Raw records go to records.jsonl as they complete.
"""
import argparse
import base64
import concurrent.futures
import hashlib
import json
import statistics
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from benchmark_scene_latency import condition_order, summarize  # noqa: E402
from visualintel.engine import SCENE_PROMPT, resize_encoded_image  # noqa: E402
from visualintel.structured import FACTUAL_SCHEMA, validate_response  # noqa: E402

LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}
MAX_CONSECUTIVE_ERRORS = 3
DEFAULT_MODELS = "minicpm-v4.6,qwen3-vl:2b-instruct,qwen3-vl:4b-instruct,qwen3-vl:8b-instruct,minicpm-v4.5"
COUNT_COLORS = ["red", "green", "blue", "yellow", "black"]
COUNT_PROMPT = (
    "Count the filled circles in this image. Return JSON with count (an integer) and colors "
    "(a list with the color name of each circle, one entry per circle). "
    f"Color names must come from: {', '.join(COUNT_COLORS)}."
)
COUNT_SCHEMA = {
    "type": "object",
    "properties": {"count": {"type": "integer"},
                   "colors": {"type": "array", "items": {"type": "string"}}},
    "required": ["count", "colors"],
    "additionalProperties": False,
}


# ---- guards ------------------------------------------------------------------------------------------
def check_loopback(url: str, allow_nonloopback: bool = False) -> str:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError(f"Not a usable URL: {url}")
    if parsed.hostname not in LOOPBACK_HOSTS and not allow_nonloopback:
        raise ValueError(f"{url} is not loopback; use the SSH tunnel or pass --allow-nonloopback")
    return url.rstrip("/")


def sha256_bytes(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_kit(kit: Path) -> dict:
    """Return the only media this suite may send; raise if the kit is missing or has been altered."""
    lock_path = kit / "manifest.lock.json"
    labels_path = kit / "synthetic" / "labels.json"
    if not lock_path.exists() or not labels_path.exists():
        raise FileNotFoundError(f"{kit} is not a testkit (run scripts/prepare_cloud_testkit.py first)")
    lock = json.loads(lock_path.read_text(encoding="utf-8"))["files"]
    labels = json.loads(labels_path.read_text(encoding="utf-8"))["images"]
    images = []
    for path in sorted((kit / "images").glob("*.jpg")):
        known = lock.get(f"images/{path.name}")
        if not known:
            raise ValueError(f"{path.name} is not in manifest.lock.json; refusing to send unknown media")
        if sha256_bytes(path) != known["sha256"]:
            raise ValueError(f"{path.name} differs from its recorded sha256; refusing to send it")
        images.append(path)
    synthetic = []
    for name in sorted(labels):
        path = kit / "synthetic" / name
        if not path.exists():
            raise FileNotFoundError(path)
        synthetic.append((path, labels[name]))
    if len(images) < 13:
        raise ValueError(f"need at least 13 verified images (1 warm-up + 12 timed), found {len(images)}")
    return {"images": images, "synthetic": synthetic, "lock_sha256": sha256_bytes(lock_path)}


def to_jpeg(path: Path, side: int | None) -> bytes:
    frame = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if frame is None:
        raise ValueError(f"Cannot decode {path}")
    ok, encoded = cv2.imencode(".jpg", frame)
    if not ok:
        raise ValueError(f"Cannot encode {path}")
    jpeg = encoded.tobytes()
    return resize_encoded_image(jpeg, side) if side else jpeg


# ---- scoring -----------------------------------------------------------------------------------------
def parse_count_answer(text: str) -> tuple[int, list[str]]:
    data = json.loads(text)
    if not isinstance(data, dict) or type(data.get("count")) is not int or not isinstance(data.get("colors"), list):
        raise ValueError("count/colors missing or mistyped")
    return data["count"], [str(c).strip().lower() for c in data["colors"]]


def score_counting(label: dict, text: str) -> dict:
    try:
        count, colors = parse_count_answer(text)
    except Exception as error:
        return {"parsed": False, "count_ok": False, "colors_ok": False, "error": str(error)}
    truth = sorted(c for name, n in label["colors"].items() for c in [name] * n)
    return {"parsed": True, "count": count, "count_ok": count == label["circles"],
            "colors_ok": sorted(colors) == truth}


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, int(round(q * (len(ordered) - 1)))))]


def model_available(names: list[str], model: str) -> bool:
    return any(name == model or name == f"{model}:latest" for name in names)


# ---- transport ---------------------------------------------------------------------------------------
@dataclass
class Ctx:
    api: str
    base_url: str
    timeout: int
    records_path: Path
    price_per_hour: float | None = None


def post_json(url: str, payload: dict, timeout: int) -> dict:
    request = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                     headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def get_json(url: str, timeout: int) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def build_openai_payload(model: str, jpeg: bytes, prompt: str, schema: dict, max_tokens: int) -> dict:
    data_uri = "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii")
    return {
        "model": model, "temperature": 0, "seed": 42, "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": data_uri}}]}],
        "response_format": {"type": "json_schema", "json_schema": {"name": "answer", "schema": schema}},
    }


def validate_scene(text: str) -> None:
    validate_response(json.loads(text), FACTUAL_SCHEMA)


def validate_counting(text: str) -> None:
    parse_count_answer(text)


def request_model(ctx: Ctx, model: str, jpeg: bytes, prompt: str = SCENE_PROMPT, schema: dict = FACTUAL_SCHEMA,
                  validator=validate_scene, max_tokens: int = 96, keep_alive=None) -> dict:
    record = {"jpeg_bytes": len(jpeg)}
    started = time.perf_counter()
    try:
        if ctx.api == "ollama":
            payload = {"model": model, "prompt": prompt, "stream": False, "think": False,
                       "images": [base64.b64encode(jpeg).decode("ascii")], "format": schema,
                       "options": {"temperature": 0, "seed": 42, "num_predict": max_tokens}}
            if keep_alive is not None:
                payload["keep_alive"] = keep_alive
            result = post_json(f"{ctx.base_url}/api/generate", payload, ctx.timeout)
            record["wall_sec"] = round(time.perf_counter() - started, 3)
            for key, name in (("total_duration", "total_sec"), ("load_duration", "load_sec"),
                              ("prompt_eval_duration", "prompt_eval_sec"), ("eval_duration", "eval_sec")):
                if key in result:
                    record[name] = round(result[key] / 1e9, 3)
            for key in ("prompt_eval_count", "eval_count"):
                if key in result:
                    record[key] = result[key]
            text = result.get("response", "")
        else:
            result = post_json(f"{ctx.base_url}/v1/chat/completions",
                               build_openai_payload(model, jpeg, prompt, schema, max_tokens), ctx.timeout)
            record["wall_sec"] = round(time.perf_counter() - started, 3)
            timings = result.get("timings", {})
            if "prompt_ms" in timings and "predicted_ms" in timings:
                record["prompt_eval_sec"] = round(timings["prompt_ms"] / 1000, 3)
                record["eval_sec"] = round(timings["predicted_ms"] / 1000, 3)
                record["total_sec"] = round(record["prompt_eval_sec"] + record["eval_sec"], 3)
            usage = result.get("usage", {})
            record["prompt_eval_count"] = timings.get("prompt_n", usage.get("prompt_tokens"))
            record["eval_count"] = timings.get("predicted_n", usage.get("completion_tokens"))
            text = result["choices"][0]["message"]["content"] or ""
        if "total_sec" in record:
            record["net_overhead_sec"] = round(record["wall_sec"] - record["total_sec"], 3)
        record["response"] = text
        try:
            validator(text)
            record["valid"] = True
        except Exception as error:
            record["valid"] = False
            record["validation_error"] = str(error)
    except Exception as error:
        record["wall_sec"] = round(time.perf_counter() - started, 3)
        record["error"] = repr(error)
        record["valid"] = False
    return record


class ErrorBudget:
    """Fail fast: stop a test after N consecutive errors so a dead server does not burn paid time."""

    def __init__(self, limit: int = MAX_CONSECUTIVE_ERRORS):
        self.limit, self.streak = limit, 0

    def note(self, record: dict) -> None:
        self.streak = self.streak + 1 if "error" in record else 0
        if self.streak >= self.limit:
            raise RuntimeError(f"{self.limit} consecutive request errors; stopping this test "
                               f"(last: {record.get('error')})")


def emit(ctx: Ctx, test: str, record: dict, **fields) -> dict:
    full = {"test": test, **fields, **record}
    with ctx.records_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(full, ensure_ascii=False) + "\n")
    short = {k: full.get(k) for k in ("test", "model", "side", "level", "image", "wall_sec", "valid") if k in full}
    print(json.dumps(short, ensure_ascii=False), flush=True)
    return full


# ---- tests -------------------------------------------------------------------------------------------
def t0_probe(ctx: Ctx, models: list[str]) -> dict:
    path = "/api/version" if ctx.api == "ollama" else "/health"
    rtts = []
    for _ in range(20):
        started = time.perf_counter()
        info = get_json(ctx.base_url + path, 10)
        rtts.append((time.perf_counter() - started) * 1000)
    result = {"endpoint_info": info, "rtt_ms": summarize([round(v, 2) for v in rtts])}
    if ctx.api == "ollama":
        names = [m["name"] for m in get_json(ctx.base_url + "/api/tags", 10).get("models", [])]
        result["installed"] = names
        result["missing"] = [m for m in models if not model_available(names, m)]
    emit(ctx, "t0", {"probe": result})
    return result


def t1_latency(ctx: Ctx, kit: dict, models: list[str], sides: list[int], timed: int, repeats: int) -> dict:
    images = kit["images"][: timed + 1]
    out = {}
    for model_index, model in enumerate(models):
        budget = ErrorBudget()
        warm = emit(ctx, "t1", request_model(ctx, model, to_jpeg(images[0], sides[0])),
                    model=model, side=sides[0], kind="warmup", image=images[0].name)
        budget.note(warm)
        for side in condition_order(model_index, sides):
            rows = []
            for path in images[1:]:
                record = emit(ctx, "t1", request_model(ctx, model, to_jpeg(path, side)),
                              model=model, side=side, kind="timed", image=path.name)
                budget.note(record)
                rows.append(record)
            ok = [r for r in rows if "error" not in r]
            out[f"{model}@{side}"] = {
                "wall_sec": summarize([r["wall_sec"] for r in ok]),
                "prompt_eval_sec": summarize([r["prompt_eval_sec"] for r in ok if "prompt_eval_sec" in r]),
                "eval_sec": summarize([r["eval_sec"] for r in ok if "eval_sec" in r]),
                "net_overhead_sec": summarize([r["net_overhead_sec"] for r in ok if "net_overhead_sec" in r]),
                "prompt_eval_count": summarize([r["prompt_eval_count"] for r in ok if r.get("prompt_eval_count")]),
                "valid": f"{sum(bool(r['valid']) for r in rows)}/{len(rows)}",
                "errors": len(rows) - len(ok),
            }
        control = [emit(ctx, "t1", request_model(ctx, model, to_jpeg(images[1], sides[0])),
                        model=model, side=sides[0], kind="repeat-control", image=images[1].name)
                   for _ in range(repeats)]
        out[f"{model}@repeat-control"] = [r["wall_sec"] for r in control if "error" not in r]
    return out


def run_level(ctx: Ctx, model: str, level: int, jpegs: list[bytes]) -> tuple[dict, list[dict]]:
    started = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=level) as pool:
        records = list(pool.map(lambda jpeg: request_model(ctx, model, jpeg), jpegs))
    elapsed = time.perf_counter() - started
    ok = [r for r in records if "error" not in r]
    walls = [r["wall_sec"] for r in ok]
    result = {"requests": len(records), "ok": len(ok), "elapsed_sec": round(elapsed, 3),
              "throughput_rps": round(len(ok) / elapsed, 3) if elapsed else None,
              "latency_median_sec": round(statistics.median(walls), 3) if walls else None,
              "latency_p95_sec": round(percentile(walls, 0.95), 3) if walls else None,
              "valid": f"{sum(bool(r['valid']) for r in records)}/{len(records)}"}
    if ctx.price_per_hour and result["throughput_rps"]:
        result["usd_per_1000_requests"] = round(ctx.price_per_hour / 3600 / result["throughput_rps"] * 1000, 4)
    return result, records


def t2_concurrency(ctx: Ctx, kit: dict, model: str, levels: list[int], base_side: int) -> dict:
    out = {}
    budget = ErrorBudget()
    pool_images = kit["images"][1:]
    # Each level resizes to a slightly different side so no level can hit the previous level's image cache.
    for index, level in enumerate(levels):
        side = base_side - 8 * index
        count = min(max(8, 3 * level), len(pool_images))
        jpegs = [to_jpeg(path, side) for path in pool_images[:count]]
        result, records = run_level(ctx, model, level, jpegs)
        result["side"] = side
        for record in records:
            emit(ctx, "t2", record, model=model, level=level, side=side)
            budget.note(record)
        out[str(level)] = result
        print(json.dumps({"t2_level": level, **result}), flush=True)
    return out


def t3_counting(ctx: Ctx, kit: dict, models: list[str], sides: list[int | None]) -> dict:
    out = {}
    for model in models:
        budget = ErrorBudget()
        for side in sides:
            results = []
            for path, label in kit["synthetic"]:
                record = emit(ctx, "t3", request_model(ctx, model, to_jpeg(path, side), COUNT_PROMPT, COUNT_SCHEMA,
                                                       validate_counting, max_tokens=64),
                              model=model, side=side, image=path.name, truth=label)
                budget.note(record)
                if "error" not in record:
                    results.append(score_counting(label, record["response"]))
            out[f"{model}@{side or 'native'}"] = {
                "images": len(kit["synthetic"]), "answered": len(results),
                "count_ok": sum(r["count_ok"] for r in results),
                "colors_ok": sum(r["colors_ok"] for r in results)}
    return out


def t4_cold_start(ctx: Ctx, kit: dict, models: list[str], side: int, repeats: int) -> dict:
    if ctx.api != "ollama":
        return {"skipped": "cold start is measured through Ollama keep_alive; llama-server stays loaded"}
    out = {}
    jpeg = to_jpeg(kit["images"][1], side)
    for model in models:
        budget = ErrorBudget()
        rows = []
        for _ in range(repeats):
            try:  # unload: an empty generate with keep_alive 0 releases the model
                post_json(f"{ctx.base_url}/api/generate", {"model": model, "keep_alive": 0}, ctx.timeout)
            except Exception as error:
                print(f"unload failed for {model}: {error!r}", flush=True)
            record = emit(ctx, "t4", request_model(ctx, model, jpeg), model=model, side=side, kind="cold")
            budget.note(record)
            rows.append(record)
        ok = [r for r in rows if "error" not in r]
        out[model] = {"wall_sec": summarize([r["wall_sec"] for r in ok]),
                      "load_sec": summarize([r["load_sec"] for r in ok if "load_sec" in r])}
    return out


# ---- main --------------------------------------------------------------------------------------------
def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api", choices=["ollama", "openai"], default="ollama",
                        help="ollama: /api/generate on :11434; openai: llama-server /v1/chat/completions on :8080")
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--allow-nonloopback", action="store_true")
    parser.add_argument("--kit", type=Path, default=ROOT / "outputs" / "testkit-cloud")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--models", default=None,
                        help=f"comma separated; default for ollama: {DEFAULT_MODELS}; for openai: minicpm-v4.6")
    parser.add_argument("--tests", default="t0,t1,t2,t3,t4")
    parser.add_argument("--sides", type=int, nargs="+", default=[640, 448, 320])
    parser.add_argument("--timed", type=int, default=12)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--concurrency", type=int, nargs="+", default=[1, 2, 4, 8])
    parser.add_argument("--concurrency-model", default="minicpm-v4.6")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--price-per-hour", type=float, default=None,
                        help="instance price (USD/h) to turn throughput into USD per 1000 requests")
    args = parser.parse_args()

    base_url = check_loopback(args.base_url or ("http://127.0.0.1:11434" if args.api == "ollama"
                                                else "http://127.0.0.1:8080"), args.allow_nonloopback)
    models = [m for m in (args.models or (DEFAULT_MODELS if args.api == "ollama" else "minicpm-v4.6")).split(",") if m]
    tests = [t.strip() for t in args.tests.split(",") if t.strip()]
    kit = load_kit(args.kit)
    output = args.output or ROOT / "outputs" / f"cloud-run-{time.strftime('%Y%m%d-%H%M%S')}-{args.api}"
    output.mkdir(parents=True, exist_ok=False)
    ctx = Ctx(args.api, base_url, args.timeout, output / "records.jsonl", args.price_per_hour)
    summary = {"api": args.api, "base_url": base_url, "models_requested": models, "tests": tests,
               "kit_lock_sha256": kit["lock_sha256"], "started": time.strftime("%Y-%m-%d %H:%M:%S"),
               "price_per_hour": args.price_per_hour, "results": {}}

    probe = t0_probe(ctx, models)
    summary["results"]["t0"] = probe
    if probe.get("missing"):
        print(f"WARNING: models not installed on the server and skipped: {probe['missing']}", flush=True)
        models = [m for m in models if m not in probe["missing"]]
    if not models:
        print("No requested model is installed; nothing to test.", file=sys.stderr)
        return 2

    status = 0
    steps = {
        "t1": lambda: t1_latency(ctx, kit, models, args.sides, args.timed, args.repeats),
        "t2": lambda: t2_concurrency(ctx, kit, args.concurrency_model if args.concurrency_model in models
                                     else models[0], args.concurrency, args.sides[0]),
        "t3": lambda: t3_counting(ctx, kit, models, [None, 448]),
        "t4": lambda: t4_cold_start(ctx, kit, models, args.sides[0], args.repeats),
    }
    for name in [t for t in tests if t in steps]:
        print(f"=== {name} ===", flush=True)
        try:
            summary["results"][name] = steps[name]()
        except Exception as error:  # keep what we have; report instead of hiding
            summary["results"][name] = {"aborted": repr(error)}
            status = 1
            print(f"{name} aborted: {error!r}", file=sys.stderr, flush=True)
        (output / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    summary["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
    (output / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nresults: {output}")
    print("REMINDER: terminate the instance in the provider console now; verify the hourly cost shows $0.")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
