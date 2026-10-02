"""Evaluate the production scene prompt on local images, preserving raw calls."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import time

import cv2
import numpy as np

from visualintel.engine import (
    SCENE_PROMPT, _http_post_json, call_model, check_ollama_ready, resize_encoded_image,
)
from visualintel.structured import FACTUAL_SCHEMA


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("images", nargs="+")
    parser.add_argument("--output", required=True)
    parser.add_argument("--model", default="minicpm-v4.6")
    parser.add_argument("--max-image-side", type=int)
    args = parser.parse_args()
    if args.max_image_side is not None and args.max_image_side <= 0:
        parser.error("--max-image-side must be positive")
    check_ollama_ready(args.model)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    records = []
    options = {"temperature": 0, "seed": 42, "num_predict": 96}
    for index, filename in enumerate(args.images):
        source = Path(filename).read_bytes()
        image = resize_encoded_image(source, args.max_image_side)
        decoded = cv2.imdecode(np.frombuffer(image, dtype=np.uint8), cv2.IMREAD_COLOR)
        if decoded is None:
            raise ValueError(f"Cannot decode {filename}")
        attempts = []

        def capture(url, payload, timeout):
            started = time.perf_counter()
            try:
                response = _http_post_json(url, payload, timeout)
            except Exception as error:
                attempts.append({"elapsed_sec": time.perf_counter() - started, "error": str(error)})
                raise
            attempts.append({"elapsed_sec": time.perf_counter() - started,
                             "prompt": payload["prompt"], "raw_response": response})
            return response

        record = {"image": str(Path(filename).resolve()), "model": args.model,
                  "source_sha256": hashlib.sha256(source).hexdigest(),
                  "prepared_sha256": hashlib.sha256(image).hexdigest(),
                  "width": decoded.shape[1], "height": decoded.shape[0],
                  "max_image_side": args.max_image_side, "prompt": SCENE_PROMPT,
                  "options": options, "schema": FACTUAL_SCHEMA}
        started = time.perf_counter()
        try:
            raw = call_model([base64.b64encode(image).decode()], SCENE_PROMPT,
                             model=args.model, response_schema=FACTUAL_SCHEMA,
                             generation_options=options, post_fn=capture)
            record["answer"] = json.loads(raw)["answer"]
        except Exception as error:
            record["error"] = str(error)
        record["elapsed_sec"] = round(time.perf_counter() - started, 2)
        record["attempts"] = attempts
        with (output / f"{index:02d}-result.json").open("x", encoding="utf-8") as handle:
            json.dump(record, handle, ensure_ascii=False, indent=2)
        records.append(record)
        print(json.dumps({key: value for key, value in record.items()
                          if key in ("image", "answer", "error", "elapsed_sec")},
                         ensure_ascii=False), flush=True)
    with (output / "results.json").open("x", encoding="utf-8") as handle:
        json.dump(records, handle, ensure_ascii=False, indent=2)
    return int(any("error" in record for record in records))


if __name__ == "__main__":
    raise SystemExit(main())
