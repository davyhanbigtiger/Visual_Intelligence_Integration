import base64
import importlib.util
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import cv2
import numpy as np
import pytest

from visualintel import engine
from visualintel.structured import FACTUAL_SCHEMA

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("ollama_facade", ROOT / "scripts" / "cloud" / "ollama_facade.py")
facade = importlib.util.module_from_spec(spec)
spec.loader.exec_module(facade)


class FakeLlamaServer:
    """OpenAI-compatible upstream with HTTP/1.1 keep-alive; remembers bodies and client ports."""

    def __init__(self, status=200, content=None, finish="stop"):
        outer = self
        self.bodies, self.ports = [], set()
        self.status, self.finish = status, finish
        self.content = content if content is not None else json.dumps({"answer": "a room"})

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                outer.bodies.append((self.path, body))
                outer.ports.add(self.client_address[1])
                payload = ({"choices": [{"message": {"content": outer.content}, "finish_reason": outer.finish}],
                            "timings": {"prompt_n": 288, "prompt_ms": 300.0, "predicted_n": 20, "predicted_ms": 100.0}}
                           if outer.status == 200 else {"error": "upstream broke"})
                data = json.dumps(payload).encode()
                self.send_response(outer.status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()


def start_facade(upstream_url):
    upstream = facade.Upstream(facade.check_loopback(upstream_url), 10)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), facade.make_handler(upstream, "minicpm-v4.6"))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{httpd.server_address[1]}", httpd


@pytest.fixture
def stack():
    started = []

    def make(**kwargs):
        fake = FakeLlamaServer(**kwargs)
        url, httpd = start_facade(fake.url)
        started.append((fake, httpd))
        return fake, url

    yield make
    for fake, httpd in started:
        httpd.shutdown()
        httpd.server_close()
        fake.httpd.shutdown()
        fake.httpd.server_close()


def jpeg_b64():
    ok, enc = cv2.imencode(".jpg", np.full((40, 60, 3), 120, dtype=np.uint8))
    return base64.b64encode(enc.tobytes()).decode("ascii")


def test_upstream_must_be_http_loopback():
    assert facade.check_loopback("http://127.0.0.1:28080").port == 28080
    for bad in ("http://203.0.113.5:8080", "https://127.0.0.1:8080", "http://example.com", "file:///x"):
        with pytest.raises(ValueError):
            facade.check_loopback(bad)


def test_payload_translation_covers_images_options_and_schema():
    body = {"model": "m", "prompt": "describe", "images": ["AAA", "BBB"], "format": FACTUAL_SCHEMA,
            "options": {"temperature": 0, "seed": 42, "num_predict": 96}, "think": False, "stream": False}
    payload = facade.to_openai_payload(body, "default")
    parts = payload["messages"][0]["content"]
    assert parts[0] == {"type": "text", "text": "describe"}
    assert [p["image_url"]["url"] for p in parts[1:]] == ["data:image/jpeg;base64,AAA", "data:image/jpeg;base64,BBB"]
    assert payload["temperature"] == 0 and payload["seed"] == 42 and payload["max_tokens"] == 96
    assert payload["response_format"]["json_schema"]["schema"] == FACTUAL_SCHEMA


def test_length_finish_reason_is_reported_as_ollama_length():
    result = {"choices": [{"message": {"content": "{"}, "finish_reason": "length"}]}
    assert facade.to_ollama_response(result, "m", 1)["done_reason"] == "length"


def test_real_engine_functions_work_through_the_facade(stack, monkeypatch):
    fake, url = stack()
    monkeypatch.setenv("VISUALINTEL_OLLAMA_URL", url)
    engine.check_ollama_ready("minicpm-v4.6")  # /api/tags through the facade
    text = engine.call_model([jpeg_b64()], engine.SCENE_PROMPT, response_schema=FACTUAL_SCHEMA,
                             generation_options={"temperature": 0, "seed": 42, "num_predict": 96})
    assert json.loads(text) == {"answer": "a room"}
    path, body = fake.bodies[0]
    assert path == "/v1/chat/completions" and body["max_tokens"] == 96


def test_upstream_connection_is_reused_across_requests(stack, monkeypatch):
    fake, url = stack()
    monkeypatch.setenv("VISUALINTEL_OLLAMA_URL", url)
    for _ in range(4):
        engine.call_model([jpeg_b64()], "p", response_schema=FACTUAL_SCHEMA)
    assert len(fake.bodies) == 4 and len(fake.ports) == 1  # one TCP connection for four requests


def test_upstream_failure_surfaces_as_model_call_error(stack, monkeypatch):
    fake, url = stack(status=500)
    monkeypatch.setenv("VISUALINTEL_OLLAMA_URL", url)
    with pytest.raises(engine.ModelCallError):
        engine.call_model([jpeg_b64()], "p", response_schema=FACTUAL_SCHEMA)


def test_truncated_structured_output_is_rejected_like_ollama(stack, monkeypatch):
    fake, url = stack(content='{"answer": "cut off', finish="length")
    monkeypatch.setenv("VISUALINTEL_OLLAMA_URL", url)
    with pytest.raises(engine.ModelCallError):
        engine.call_model([jpeg_b64()], "p", response_schema=FACTUAL_SCHEMA)
    assert len(fake.bodies) == 2  # the engine's own single retry still applies


# ---- endpoint override in the engine -------------------------------------------------------------------
def test_default_endpoint_is_unchanged_without_the_variable(monkeypatch):
    monkeypatch.delenv("VISUALINTEL_OLLAMA_URL", raising=False)
    assert engine.default_base_url() == "http://localhost:11434"


def test_override_accepts_loopback_only_by_default(monkeypatch):
    monkeypatch.setenv("VISUALINTEL_OLLAMA_URL", "http://127.0.0.1:21435/")
    assert engine.default_base_url() == "http://127.0.0.1:21435"
    monkeypatch.setenv("VISUALINTEL_OLLAMA_URL", "http://203.0.113.5:11434")
    with pytest.raises(engine.EngineNotReadyError, match="not loopback"):
        engine.default_base_url()
    monkeypatch.setenv("VISUALINTEL_ALLOW_NONLOOPBACK", "1")
    assert engine.default_base_url() == "http://203.0.113.5:11434"


def test_override_rejects_non_http_values(monkeypatch):
    for bad in ("file:///etc/passwd", "ftp://127.0.0.1", "127.0.0.1:11434"):
        monkeypatch.setenv("VISUALINTEL_OLLAMA_URL", bad)
        with pytest.raises(engine.EngineNotReadyError):
            engine.default_base_url()


def test_explicit_base_url_still_wins_over_the_variable(monkeypatch):
    monkeypatch.setenv("VISUALINTEL_OLLAMA_URL", "http://127.0.0.1:21435")
    seen = {}

    def fake_post(url, payload, timeout):
        seen["url"] = url
        return {"response": json.dumps({"answer": "x"}), "done_reason": "stop"}

    engine.call_model([jpeg_b64()], "p", base_url="http://localhost:9999", post_fn=fake_post,
                      response_schema=FACTUAL_SCHEMA)
    assert seen["url"] == "http://localhost:9999/api/generate"
