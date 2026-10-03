"""Isolated CPU llama-server scene evaluation; stops only its own child process."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request

from visualintel.engine import SCENE_PROMPT, resize_encoded_image
from visualintel.structured import FACTUAL_SCHEMA, validate_response


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("images", nargs="+")
    parser.add_argument("--server", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--mmproj", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--port", type=int, default=18937)
    parser.add_argument("--sides", type=int, nargs="+", default=[640, 320])
    parser.add_argument("--structured", action="store_true")
    parser.add_argument("--server-arg", action="append", default=[],
                        help="Extra llama-server argument (repeatable), e.g. --server-arg=--image-max-tokens "
                             "--server-arg=128")
    parser.add_argument("--prompt", default="Describe this image in one short sentence.",
                        help="Prompt for non-structured runs (default unchanged)")
    parser.add_argument("--gpu", action="store_true",
                        help="Offload the model and the vision projector to the SYCL/OpenCL iGPU "
                             "(default: force CPU, unchanged)")
    parser.add_argument("--warmup", default=None,
                        help="Optional image sent once before timing; its result is discarded")
    args = parser.parse_args()
    if any(side <= 0 for side in args.sides):
        parser.error("sides must be positive")
    with socket.socket() as check:
        check.bind(("127.0.0.1", args.port))
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    placement = ["-ngl", "99"] if args.gpu else ["--device", "none", "-ngl", "0", "--no-mmproj-offload"]
    command = [str(Path(args.server).resolve()), "-m", str(Path(args.model).resolve()),
               "--mmproj", str(Path(args.mmproj).resolve()), *placement, "--host", "127.0.0.1",
               "--port", str(args.port), "-c", "2048", "--parallel", "1",
               "--no-cache-prompt", "--reasoning", "off"]
    if args.structured:
        command.append("--jinja")
    command.extend(args.server_arg)
    config = {"args": command,
              "model_sha256": hashlib.sha256(Path(args.model).read_bytes()).hexdigest(),
              "mmproj_sha256": hashlib.sha256(Path(args.mmproj).read_bytes()).hexdigest()}
    (output / "server-config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    env = os.environ.copy()
    env["ONEAPI_DEVICE_SELECTOR"] = "opencl:gpu"
    records = []
    with (output / "server.log").open("x", encoding="utf-8") as log:
        child = subprocess.Popen(command, stdout=log, stderr=log, env=env,
                                 creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            for _ in range(60):
                if child.poll() is not None:
                    raise RuntimeError(f"Test server exited: {child.returncode}")
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{args.port}/health", timeout=1) as response:
                        if response.status == 200:
                            break
                except Exception:
                    time.sleep(1)
            else:
                raise RuntimeError("Test server not ready")
            prompt = SCENE_PROMPT if args.structured else args.prompt

            def build_payload(image: bytes) -> dict:
                payload = {"messages": [{"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(image).decode()}},
                ]}], "temperature": 0, "seed": 42,
                    "max_tokens": 96 if args.structured else 64, "stream": False,
                    "cache_prompt": False}
                if args.structured:
                    payload["response_format"] = {"type": "json_object", "schema": FACTUAL_SCHEMA}
                return payload

            if args.warmup:
                warm = resize_encoded_image(Path(args.warmup).read_bytes(), args.sides[0])
                warm_request = urllib.request.Request(f"http://127.0.0.1:{args.port}/v1/chat/completions",
                    data=json.dumps(build_payload(warm)).encode(), headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(warm_request, timeout=180) as response:
                    response.read()
            for side in args.sides:
                for index, filename in enumerate(args.images):
                    source = Path(filename).read_bytes()
                    image = resize_encoded_image(source, side)
                    payload = build_payload(image)
                    record = {"image": str(Path(filename).resolve()), "max_side": side,
                              "source_sha256": hashlib.sha256(source).hexdigest(),
                              "prepared_sha256": hashlib.sha256(image).hexdigest(),
                              "prompt": prompt, "structured": args.structured}
                    started = time.perf_counter()
                    try:
                        request = urllib.request.Request(f"http://127.0.0.1:{args.port}/v1/chat/completions",
                            data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
                        with urllib.request.urlopen(request, timeout=180) as response:
                            raw = json.load(response)
                        record["raw_response"] = raw
                        record["answer"] = raw["choices"][0]["message"]["content"]
                        if raw["choices"][0]["finish_reason"] == "length":
                            raise ValueError("Output truncated")
                        if args.structured:
                            validate_response(json.loads(record["answer"]), FACTUAL_SCHEMA)
                    except Exception as error:
                        record["error"] = str(error)
                    record["elapsed_sec"] = round(time.perf_counter() - started, 2)
                    with (output / f"{side}-{index:02d}.json").open("x", encoding="utf-8") as handle:
                        json.dump(record, handle, ensure_ascii=False, indent=2)
                    records.append(record)
                    print(json.dumps({key: value for key, value in record.items()
                                      if key in ("image", "max_side", "answer", "error", "elapsed_sec")},
                                     ensure_ascii=False), flush=True)
        finally:
            child.terminate()
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
            with (output / "results.json").open("x", encoding="utf-8") as handle:
                json.dump(records, handle, ensure_ascii=False, indent=2)
    return int(any("error" in record for record in records))


if __name__ == "__main__":
    raise SystemExit(main())
