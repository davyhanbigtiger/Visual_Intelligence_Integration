"""Run preconverted local SmolVLM with Optimum Intel in an isolated environment."""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys
import time


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("images", nargs="+")
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--device", choices=["CPU", "GPU"], default="CPU")
    parser.add_argument("--sides", type=int, nargs="+", default=[640, 320])
    parser.add_argument("--processor-max-edge", type=int,
                        help="Bound the processor resize, which may otherwise upscale small inputs")
    args = parser.parse_args()
    if any(side <= 0 for side in args.sides):
        parser.error("sides must be positive")
    if args.processor_max_edge is not None and args.processor_max_edge <= 0:
        parser.error("--processor-max-edge must be positive")
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    from PIL import Image
    import openvino as ov
    from optimum.intel import OVModelForVisualCausalLM
    from transformers import AutoProcessor

    core = ov.Core()
    metadata = {"device": args.device, "available_devices": core.available_devices,
                "model": str(Path(args.model).resolve()),
                "versions": {name: importlib.metadata.version(name) for name in
                             ("torch", "transformers", "optimum-intel", "openvino")}}
    started = time.perf_counter()
    model_path = str(Path(args.model).resolve())
    processor = AutoProcessor.from_pretrained(model_path, local_files_only=True, trust_remote_code=False)
    metadata["original_processor_size"] = processor.image_processor.size.copy()
    if args.processor_max_edge is not None:
        processor.image_processor.size = {"longest_edge": args.processor_max_edge}
    metadata["processor_size"] = processor.image_processor.size.copy()
    model = OVModelForVisualCausalLM.from_pretrained(model_path, device=args.device,
                                                   local_files_only=True, trust_remote_code=False)
    metadata["load_compile_sec"] = round(time.perf_counter() - started, 2)
    (output / "environment.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(json.dumps(metadata), flush=True)
    prompt = "Describe this image in one short sentence."
    records = []
    for side in args.sides:
        for index, filename in enumerate(args.images):
            record = {"image": str(Path(filename).resolve()), "max_side": side,
                      "source_sha256": hashlib.sha256(Path(filename).read_bytes()).hexdigest(),
                      "prompt": prompt, "first_request": not records, "max_new_tokens": 64,
                      "do_sample": False}
            started = time.perf_counter()
            try:
                with Image.open(filename) as original:
                    image = original.convert("RGB")
                image.thumbnail((side, side), Image.Resampling.LANCZOS)
                record["prepared_size"] = list(image.size)
                messages = [{"role": "user", "content": [{"type": "image"}, {"type": "text", "text": prompt}]}]
                text = processor.apply_chat_template(messages, add_generation_prompt=True)
                inputs = processor(text=text, images=[image], return_tensors="pt")
                record["input_tokens"] = int(inputs["input_ids"].shape[-1])
                record["pixel_values_shape"] = list(inputs["pixel_values"].shape)
                record["preprocess_sec"] = round(time.perf_counter() - started, 3)
                generated = model.generate(**inputs, max_new_tokens=64, do_sample=False)
                new_tokens = generated[:, inputs["input_ids"].shape[-1]:]
                record["generated_tokens"] = int(new_tokens.shape[-1])
                record["answer"] = processor.batch_decode(new_tokens, skip_special_tokens=True)[0]
                if record["generated_tokens"] == 64:
                    record["limit_reached"] = True
            except Exception as error:
                record["error"] = str(error)
            record["elapsed_sec"] = round(time.perf_counter() - started, 2)
            with (output / f"{side}-{index:02d}.json").open("x", encoding="utf-8") as handle:
                json.dump(record, handle, ensure_ascii=False, indent=2)
            records.append(record)
            print(json.dumps(record, ensure_ascii=False), flush=True)
    with (output / "results.json").open("x", encoding="utf-8") as handle:
        json.dump(records, handle, ensure_ascii=False, indent=2)
    return int(any("error" in record for record in records))


if __name__ == "__main__":
    raise SystemExit(main())
