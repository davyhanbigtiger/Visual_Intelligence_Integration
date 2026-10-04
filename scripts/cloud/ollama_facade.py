"""Ollama-protocol facade in front of an OpenAI-compatible llama-server (for example the T4 reached through
an SSH tunnel), so unmodified Ollama clients -- the `visualintel` CLI and camera demo -- can use it.

    python scripts/cloud/ollama_facade.py --upstream http://127.0.0.1:28080 --port 21435
    $env:VISUALINTEL_OLLAMA_URL = "http://127.0.0.1:21435"

Translates GET /api/tags and /api/version, and POST /api/generate (prompt, images, format schema, options
temperature / seed / num_predict) into /v1/chat/completions, and the answer back into Ollama's shape.

* Listens on loopback only, and the upstream must be loopback too (use the SSH tunnel).
* Keeps one persistent connection per worker thread to the upstream. Through an SSH tunnel every new connection
  costs an extra round trip before any data flows, so reuse is the cheapest latency win.
* Nothing is stored or logged apart from one status line per request (no prompts, no images, no answers).
"""
import argparse
import http.client
import json
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}
MAX_BODY_BYTES = 32 * 1024 * 1024


def check_loopback(url: str) -> urllib.parse.ParseResult:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "http" or parsed.hostname not in LOOPBACK_HOSTS:
        raise ValueError(f"upstream must be an http loopback URL (through the SSH tunnel), got {url}")
    return parsed


def to_openai_payload(body: dict, default_model: str) -> dict:
    content = [{"type": "text", "text": body.get("prompt", "")}]
    for image in body.get("images") or []:
        content.append({"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + image}})
    options = body.get("options") or {}
    payload = {"model": body.get("model") or default_model, "stream": False,
               "messages": [{"role": "user", "content": content}]}
    if "temperature" in options:
        payload["temperature"] = options["temperature"]
    if "seed" in options:
        payload["seed"] = options["seed"]
    if "num_predict" in options:
        payload["max_tokens"] = options["num_predict"]
    fmt = body.get("format")
    if isinstance(fmt, dict):
        payload["response_format"] = {"type": "json_schema", "json_schema": {"name": "answer", "schema": fmt}}
    elif fmt == "json":
        payload["response_format"] = {"type": "json_object"}
    return payload


def to_ollama_response(result: dict, model: str, wall_ns: int) -> dict:
    choice = result["choices"][0]
    timings = result.get("timings", {})
    usage = result.get("usage", {})
    return {
        "model": model,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "response": choice["message"].get("content") or "",
        "done": True,
        "done_reason": "length" if choice.get("finish_reason") == "length" else "stop",
        "total_duration": wall_ns,
        "prompt_eval_count": timings.get("prompt_n", usage.get("prompt_tokens")),
        "eval_count": timings.get("predicted_n", usage.get("completion_tokens")),
        "prompt_eval_duration": int(timings.get("prompt_ms", 0) * 1e6),
        "eval_duration": int(timings.get("predicted_ms", 0) * 1e6),
    }


class Upstream:
    """Small pool of persistent HTTP/1.1 connections shared by all worker threads.

    A per-thread connection would not help: clients such as urllib open a new connection for every request, so the
    server spawns a new thread each time. A pool lets consecutive requests reuse an idle connection to the
    upstream. One retry on a fresh connection covers a connection the other side has silently closed.
    """

    MAX_IDLE = 8

    def __init__(self, parsed: urllib.parse.ParseResult, timeout: int):
        self.host, self.port, self.timeout = parsed.hostname, parsed.port or 80, timeout
        self.idle: list[http.client.HTTPConnection] = []
        self.lock = threading.Lock()

    def _new(self) -> http.client.HTTPConnection:
        return http.client.HTTPConnection(self.host, self.port, timeout=self.timeout)

    def _release(self, conn: http.client.HTTPConnection) -> None:
        with self.lock:
            if len(self.idle) < self.MAX_IDLE:
                self.idle.append(conn)
                return
        conn.close()

    def request(self, method: str, path: str, payload: dict | None = None) -> tuple[int, dict]:
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Content-Type": "application/json"} if data else {}
        for attempt in (0, 1):
            with self.lock:
                conn = self.idle.pop() if (attempt == 0 and self.idle) else None
            conn = conn or self._new()
            try:
                conn.request(method, path, body=data, headers=headers)
                response = conn.getresponse()
                raw = response.read()
                status, result = response.status, (json.loads(raw) if raw else {})
            except (http.client.HTTPException, OSError):
                conn.close()
                if attempt == 1:
                    raise
                continue
            self._release(conn)
            return status, result
        raise RuntimeError("unreachable")


def make_handler(upstream: Upstream, model_name: str):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):  # one status line, never the request content
            sys.stderr.write(f"{self.command} {self.path} -> {args[1] if len(args) > 1 else ''}\n")

        def _send(self, status: int, payload: dict) -> None:
            data = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path == "/api/tags":
                self._send(200, {"models": [{"name": f"{model_name}:latest", "model": f"{model_name}:latest"}]})
            elif self.path == "/api/version":
                self._send(200, {"version": "facade-for-llama-server"})
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self):
            if self.path != "/api/generate":
                self._send(404, {"error": "not found"})
                return
            length = int(self.headers.get("Content-Length", 0))
            if length <= 0 or length > MAX_BODY_BYTES:
                self._send(413, {"error": "request body missing or too large"})
                return
            try:
                body = json.loads(self.rfile.read(length))
                started = time.perf_counter_ns()
                status, result = upstream.request("POST", "/v1/chat/completions",
                                                  to_openai_payload(body, model_name))
                if status != 200:
                    self._send(502, {"error": f"upstream returned HTTP {status}: {str(result)[:200]}"})
                    return
                self._send(200, to_ollama_response(result, body.get("model") or model_name,
                                                   time.perf_counter_ns() - started))
            except Exception as error:
                self._send(502, {"error": f"upstream failure: {error!r}"})

    return Handler


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--upstream", default="http://127.0.0.1:28080")
    parser.add_argument("--port", type=int, default=21435)
    parser.add_argument("--model-name", default="minicpm-v4.6")
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args()
    upstream = Upstream(check_loopback(args.upstream), args.timeout)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(upstream, args.model_name))
    print(f"facade on http://127.0.0.1:{args.port} -> {args.upstream}  (Ctrl+C to stop)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
