"""Record real local inference; semantic quality must be reviewed separately."""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time

from visualintel.engine import _http_get_json, _http_post_json, extract_frames, _UNDERSTAND_PROMPT, STRUCTURED_REPORT_PROMPT, resize_encoded_image
from visualintel.structured import REPORT_SCHEMA, FACTUAL_SCHEMA, ADVICE_SCHEMA, validate_response

REPORT_PROMPT = (
    "These video frames are in time order. Describe the visible actions briefly. "
    "Flag only visibly supported unusual events. Give a specific, hedged assessment "
    "and suggestion; if no route is visible, say so. Never invent metric distances, "
    "commands, or unseen actions. Return only JSON matching this schema: "
    + json.dumps(REPORT_SCHEMA)
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="minicpm-v4.6")
    parser.add_argument("--video", default="videos/test_video.avi")
    parser.add_argument("--output", required=True)
    parser.add_argument("--single-image-only", action="store_true")
    parser.add_argument("--improved-prompt", action="store_true")
    parser.add_argument("--extra-image", help="Optional public or user-provided image for scene generalization")
    parser.add_argument("--cases", nargs="+", help="Run only these named cases")
    parser.add_argument("--vendor-sampling", action="store_true", help="Use Qwen3-VL's published Instruct sampling parameters")
    parser.add_argument("--max-image-side", type=int, help="Optional image downsampling; changes visual detail")
    args = parser.parse_args()
    if args.vendor_sampling and not (args.model.startswith("qwen3-vl") and "instruct" in args.model):
        parser.error("Vendor Instruct sampling requires an explicit qwen3-vl:*instruct* tag")
    if args.max_image_side is not None and args.max_image_side <= 0:
        parser.error("--max-image-side must be positive")
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=False)
    cases = [
        ("early-caption", [0], "Describe only the visible person, clothing, objects and action. At most 45 words.", None, 128),
        ("late-factual-json", [120], 'What is the person holding? Answer briefly. Return JSON with only an "answer" string.', FACTUAL_SCHEMA, 128),
        ("hidden-beverage-json", [120], 'Can you determine the beverage inside the mug from this image? If the contents are not visible, say they cannot be determined. Do not guess. Return JSON with only an "answer" string.', FACTUAL_SCHEMA, 128),
    ]
    if not args.single_image_only:
        cases += [
            ("report-legacy", [0, 60, 120], _UNDERSTAND_PROMPT + "\nKeep all fields brief.", None, 384),
            ("report-json", [0, 60, 120], STRUCTURED_REPORT_PROMPT if args.improved_prompt else REPORT_PROMPT, REPORT_SCHEMA, 384),
            ("advice-json", [0, 60, 120], 'Does this scene provide enough evidence for a walking route? Give a brief hedged answer and guidance. Never invent a route or distance. Return JSON with "answer" and "guidance" strings.', ADVICE_SCHEMA, 192),
        ]
    if args.extra_image:
        cases += [
            ("room-caption", [], "Describe the visible objects and scene. Do not invent unseen events. At most 60 words.", None, 128),
            ("room-advice-json", [], 'What visible features might matter for someone moving through this room? Give a specific hedged observation, not a command. Do not declare the entire route safe or invent distances. Return JSON with "answer" and "guidance" strings.', ADVICE_SCHEMA, 256),
        ]
    if args.cases:
        if set(args.cases) - {case[0] for case in cases}:
            parser.error("Unknown case; check --single-image-only and --extra-image")
        cases = [case for case in cases if case[0] in args.cases]
    metadata = {"model": args.model, "video": args.video,
                "video_sha256": hashlib.sha256(Path(args.video).read_bytes()).hexdigest(),
                "started_utc": datetime.now(timezone.utc).isoformat(),
                "ollama_version": _http_get_json("http://localhost:11434/api/version", 5),
                "model_details": _http_post_json("http://localhost:11434/api/show", {"model": args.model}, 10),
                "method": "Sequential; first request may include cold load; later images can hit cache. Not a steady-state speed benchmark."}
    metadata["sampling_profile"] = "qwen3-vl-instruct" if args.vendor_sampling else "fixed-greedy"
    metadata["max_image_side"] = args.max_image_side
    if args.extra_image:
        metadata["extra_image"] = args.extra_image
        metadata["extra_image_sha256"] = hashlib.sha256(Path(args.extra_image).read_bytes()).hexdigest()
    # Avoid copying complete model templates into the metadata file.
    metadata["model_details"] = {k: v for k, v in metadata["model_details"].items() if k in ("details", "capabilities", "parameters")}
    (out / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    records = []
    for name, indices, prompt, schema, limit in cases:
        frames = [Path(args.extra_image).read_bytes()] if not indices else extract_frames(args.video, indices)
        frames = [resize_encoded_image(frame, args.max_image_side) for frame in frames]
        payload = {"model": args.model, "images": [base64.b64encode(f).decode("ascii") for f in frames],
                   "prompt": prompt, "stream": False, "think": False,
                   "options": {"temperature": 0, "seed": 42, "num_predict": limit}}
        if args.vendor_sampling:
            payload["options"].update({"temperature": 0.7, "top_p": 0.8, "top_k": 20,
                                       "repeat_penalty": 1.0, "presence_penalty": 1.5})
        if schema:
            payload["format"] = schema
        started = time.monotonic()
        record = {"case": name, "frame_indices": indices, "prompt": prompt,
                  "schema": schema, "options": payload["options"],
                  "prepared_image_sha256": [hashlib.sha256(frame).hexdigest() for frame in frames]}
        try:
            response = _http_post_json("http://localhost:11434/api/generate", payload, 300)
            record["api_response"] = response
            if schema:
                try:
                    if response.get("done_reason") == "length":
                        raise ValueError("Structured output reached token limit")
                    validate_response(json.loads(response["response"]), schema)
                    record["valid_contract"] = True
                except (ValueError, KeyError, TypeError) as error:
                    record["valid_contract"] = False
                    record["validation_error"] = str(error)
        except Exception as error:
            record["error"] = str(error)
        record["elapsed_sec"] = round(time.monotonic() - started, 2)
        (out / f"{name}.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        records.append(record)
        print(json.dumps({k: record[k] for k in ("case", "elapsed_sec", "valid_contract", "error") if k in record}), flush=True)
    (out / "results.json").write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
