#!/usr/bin/env bash
# Restart the instance's llama-server with extra arguments, for parameter sweeps (AGENTS.md section 31).
# Usage on the server:  bash restart_llama.sh --parallel 1 -c 2048
# Base arguments (model, projector, full GPU offload, loopback-only host, port 8080) are fixed here; anything you
# pass is appended. Nothing is deleted: the previous log is kept as llama-server.log.prev.
set -euo pipefail
WORK="${WORK:-$HOME/vi}"
pkill -f "llama-server .*--port 8080" 2>/dev/null || true
sleep 2
LLAMA_SERVER="$(find "$WORK/llama" -name llama-server -type f | head -1)"
export LD_LIBRARY_PATH="$(dirname "$LLAMA_SERVER"):${LD_LIBRARY_PATH:-}"
[ -f "$WORK/logs/llama-server.log" ] && cp "$WORK/logs/llama-server.log" "$WORK/logs/llama-server.log.prev"
nohup "$LLAMA_SERVER" -m "$WORK/gguf/MiniCPM-V-4.6-Q4_K_M.gguf" --mmproj "$WORK/gguf/mmproj-MiniCPM-V-4.6-Q8_0.gguf" \
      -ngl 99 --host 127.0.0.1 --port 8080 --reasoning off --jinja "$@" >"$WORK/logs/llama-server.log" 2>&1 &
disown
for _ in $(seq 1 120); do curl -fs --max-time 2 http://127.0.0.1:8080/health >/dev/null && break; sleep 1; done
curl -fs http://127.0.0.1:8080/health && echo " args: $*"
grep -qiE "found [0-9]+ CUDA devices|loaded CUDA backend|CUDA0" "$WORK/logs/llama-server.log" \
  && echo "GPU: CUDA device present in the server log" \
  || echo "WARNING: no CUDA device in the server log -- timings would be CPU numbers" >&2
