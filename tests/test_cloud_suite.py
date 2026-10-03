import importlib.util
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import cv2
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("run_cloud_suite", ROOT / "scripts" / "cloud" / "run_cloud_suite.py")
suite = importlib.util.module_from_spec(spec)
spec.loader.exec_module(suite)


class FakeServer:
    """Minimal Ollama + llama-server look-alike; records request bodies."""

    def __init__(self, delay: float = 0.0, fail: bool = False):
        outer = self
        self.bodies, self.delay, self.fail = [], delay, fail

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _send(self, payload, status=200):
                data = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                if self.path == "/api/version":
                    self._send({"version": "fake"})
                elif self.path == "/api/tags":
                    self._send({"models": [{"name": "minicpm-v4.6:latest"}]})
                elif self.path == "/health":
                    self._send({"status": "ok"})
                else:
                    self._send({}, 404)

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                outer.bodies.append((self.path, body))
                time.sleep(outer.delay)
                if outer.fail:
                    self._send({"error": "boom"}, 500)
                    return
                counting = "count" in json.dumps(body)
                text = json.dumps({"count": 2, "colors": ["Red", "blue"]}) if counting else json.dumps({"answer": "a room"})
                if self.path == "/api/generate":
                    self._send({"response": text, "total_duration": 500_000_000, "load_duration": 100_000_000,
                                "prompt_eval_duration": 300_000_000, "eval_duration": 100_000_000,
                                "prompt_eval_count": 294, "eval_count": 20})
                else:
                    self._send({"choices": [{"message": {"content": text}}],
                                "timings": {"prompt_n": 294, "prompt_ms": 300.0, "predicted_n": 20, "predicted_ms": 100.0}})

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture
def server():
    created = []

    def make(**kwargs):
        fake = FakeServer(**kwargs)
        created.append(fake)
        return fake

    yield make
    for fake in created:
        fake.close()


def make_kit(tmp_path, images=14, tamper=None):
    kit = tmp_path / "kit"
    for sub in ("images", "synthetic"):
        (kit / sub).mkdir(parents=True)
    lock = {"files": {}}
    rng = np.random.default_rng(0)
    for index in range(images):
        path = kit / "images" / f"coco-{index:03d}.jpg"
        cv2.imwrite(str(path), rng.integers(0, 255, (120, 160, 3), dtype=np.uint8))
        lock["files"][f"images/{path.name}"] = {"sha256": suite.sha256_bytes(path)}
    labels = {"images": {}}
    for index in range(2):
        name = f"synthetic-circles-{index + 1}.png"
        cv2.imwrite(str(kit / "synthetic" / name), np.full((120, 160, 3), 200, dtype=np.uint8))
        labels["images"][name] = {"circles": 2, "colors": {"red": 1, "blue": 1}}
    (kit / "synthetic" / "labels.json").write_text(json.dumps(labels), encoding="utf-8")
    (kit / "manifest.lock.json").write_text(json.dumps(lock), encoding="utf-8")
    if tamper:
        (kit / "images" / tamper).write_bytes(b"not the recorded file")
    return kit


def make_ctx(api, url, tmp_path, **kwargs):
    return suite.Ctx(api, url, 10, tmp_path / "records.jsonl", **kwargs)


def test_loopback_guard():
    assert suite.check_loopback("http://127.0.0.1:11434/") == "http://127.0.0.1:11434"
    assert suite.check_loopback("http://localhost:8080") == "http://localhost:8080"
    for bad in ("http://203.0.113.5:11434", "http://example.com", "file:///etc/passwd", "ftp://127.0.0.1"):
        with pytest.raises(ValueError):
            suite.check_loopback(bad)
    assert suite.check_loopback("http://203.0.113.5:11434", allow_nonloopback=True)


def test_kit_loads_only_verified_media(tmp_path):
    kit = suite.load_kit(make_kit(tmp_path))
    assert len(kit["images"]) == 14 and len(kit["synthetic"]) == 2
    with pytest.raises(FileNotFoundError):
        suite.load_kit(tmp_path / "nowhere")


def test_kit_refuses_tampered_or_unlisted_images(tmp_path):
    with pytest.raises(ValueError, match="sha256"):
        suite.load_kit(make_kit(tmp_path / "a", tamper="coco-003.jpg"))
    kit = make_kit(tmp_path / "b")
    cv2.imwrite(str(kit / "images" / "webcam-frame.jpg"), np.zeros((10, 10, 3), dtype=np.uint8))
    with pytest.raises(ValueError, match="not in manifest"):
        suite.load_kit(kit)


def test_kit_needs_enough_images(tmp_path):
    with pytest.raises(ValueError, match="at least 13"):
        suite.load_kit(make_kit(tmp_path, images=5))


def test_scoring_counts_and_colors_case_insensitively():
    label = {"circles": 2, "colors": {"red": 1, "blue": 1}}
    good = suite.score_counting(label, json.dumps({"count": 2, "colors": ["Blue", " red"]}))
    assert good["count_ok"] and good["colors_ok"]
    wrong = suite.score_counting(label, json.dumps({"count": 3, "colors": ["red", "blue", "red"]}))
    assert not wrong["count_ok"] and not wrong["colors_ok"]
    assert not suite.score_counting(label, "not json")["parsed"]
    assert not suite.score_counting(label, json.dumps({"count": "2", "colors": []}))["parsed"]


def test_percentile_and_model_available():
    assert suite.percentile([1, 2, 3, 4, 100], 0.95) == 100
    assert suite.percentile([5], 0.95) == 5
    assert suite.model_available(["minicpm-v4.6:latest"], "minicpm-v4.6")
    assert suite.model_available(["qwen3-vl:2b-instruct"], "qwen3-vl:2b-instruct")
    assert not suite.model_available(["minicpm-v4.6:latest"], "qwen3-vl:4b-instruct")


def test_openai_payload_shape():
    payload = suite.build_openai_payload("m", b"\xff\xd8abc", "prompt", suite.FACTUAL_SCHEMA, 96)
    content = payload["messages"][0]["content"]
    assert content[0] == {"type": "text", "text": "prompt"}
    assert content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert payload["response_format"]["json_schema"]["schema"] == suite.FACTUAL_SCHEMA
    assert payload["temperature"] == 0 and payload["max_tokens"] == 96


def test_ollama_request_records_server_timings_and_overhead(server, tmp_path):
    fake = server()
    record = suite.request_model(make_ctx("ollama", fake.url, tmp_path), "minicpm-v4.6", b"\xff\xd8jpeg")
    assert record["valid"] and record["prompt_eval_count"] == 294
    assert record["load_sec"] == 0.1 and record["total_sec"] == 0.5
    assert record["net_overhead_sec"] == pytest.approx(record["wall_sec"] - 0.5, abs=0.01)
    path, body = fake.bodies[0]
    assert path == "/api/generate" and body["think"] is False and body["format"] == suite.FACTUAL_SCHEMA


def test_openai_request_reads_llama_server_timings(server, tmp_path):
    fake = server()
    record = suite.request_model(make_ctx("openai", fake.url, tmp_path), "minicpm-v4.6", b"\xff\xd8jpeg")
    assert record["valid"] and record["prompt_eval_sec"] == 0.3 and record["eval_sec"] == 0.1
    assert fake.bodies[0][0] == "/v1/chat/completions"


def test_http_error_is_recorded_not_raised(server, tmp_path):
    record = suite.request_model(make_ctx("ollama", server(fail=True).url, tmp_path), "m", b"x")
    assert "error" in record and record["valid"] is False


def test_error_budget_stops_after_consecutive_errors():
    budget = suite.ErrorBudget(limit=3)
    budget.note({"error": "x"})
    budget.note({})  # a success resets the streak
    budget.note({"error": "x"})
    budget.note({"error": "x"})
    with pytest.raises(RuntimeError, match="consecutive"):
        budget.note({"error": "x"})


def test_probe_reports_missing_models(server, tmp_path):
    fake = server()
    result = suite.t0_probe(make_ctx("ollama", fake.url, tmp_path), ["minicpm-v4.6", "qwen3-vl:8b-instruct"])
    assert result["missing"] == ["qwen3-vl:8b-instruct"] and result["rtt_ms"]["n"] == 20


def test_concurrency_levels_and_unique_sides(server, tmp_path):
    fake = server(delay=0.05)
    ctx = make_ctx("ollama", fake.url, tmp_path, price_per_hour=0.36)
    kit = suite.load_kit(make_kit(tmp_path))
    result = suite.t2_concurrency(ctx, kit, "minicpm-v4.6", [1, 4], 640)
    assert result["1"]["ok"] == 8 and result["4"]["ok"] == 12
    assert result["1"]["side"] == 640 and result["4"]["side"] == 632  # levels never share cached pixels
    assert result["4"]["throughput_rps"] > result["1"]["throughput_rps"]
    assert result["1"]["usd_per_1000_requests"] > 0


def test_counting_test_scores_against_labels(server, tmp_path):
    fake = server()
    kit = suite.load_kit(make_kit(tmp_path))
    result = suite.t3_counting(make_ctx("ollama", fake.url, tmp_path), kit, ["minicpm-v4.6"], [None])
    assert result["minicpm-v4.6@native"] == {"images": 2, "answered": 2, "count_ok": 2, "colors_ok": 2}


def test_latency_test_runs_every_model_and_side(server, tmp_path):
    fake = server()
    kit = suite.load_kit(make_kit(tmp_path))
    result = suite.t1_latency(make_ctx("ollama", fake.url, tmp_path), kit, ["minicpm-v4.6"], [640, 448], 12, 2)
    assert result["minicpm-v4.6@640"]["valid"] == "12/12" and result["minicpm-v4.6@448"]["wall_sec"]["n"] == 12
    assert len(result["minicpm-v4.6@repeat-control"]) == 2
    lines = [json.loads(line) for line in (tmp_path / "records.jsonl").read_text().splitlines()]
    assert {line["kind"] for line in lines} == {"warmup", "timed", "repeat-control"}


def test_cold_start_is_ollama_only(server, tmp_path):
    kit = suite.load_kit(make_kit(tmp_path))
    skipped = suite.t4_cold_start(make_ctx("openai", "http://127.0.0.1:1", tmp_path), kit, ["m"], 640, 1)
    assert "skipped" in skipped
    fake = server()
    result = suite.t4_cold_start(make_ctx("ollama", fake.url, tmp_path), kit, ["minicpm-v4.6"], 640, 2)
    assert result["minicpm-v4.6"]["wall_sec"]["n"] == 2
    unloads = [b for p, b in fake.bodies if b.get("keep_alive") == 0 and "images" not in b]
    assert len(unloads) == 2
