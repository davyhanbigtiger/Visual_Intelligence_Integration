#!/usr/bin/env bash
# Prepare a rented Linux + NVIDIA GPU instance for the VisualIntelligence latency / quality tests.
#
# Run this ON the instance, as a normal or root user. It is idempotent: re-running skips files whose
# sha256 already matches. Everything is installed under $WORK (no system-wide changes) and every
# service binds to 127.0.0.1 only -- reach it through an SSH tunnel, never a public port.
# The instance is treated as an UNTRUSTED machine: put no tokens, keys or personal data on it.
#
# STATUS: written against pinned release metadata (sizes + sha256 fetched 2026-10-03) but NOT yet run
# on a real server. Watch the first run's output instead of leaving it unattended.
#
# Billing reminder: the instance keeps costing money until it is TERMINATED in the provider console.
set -euo pipefail

WORK="${WORK:-$HOME/vi}"
MODELS="${MODELS:-minicpm-v4.6 qwen3-vl:2b-instruct qwen3-vl:4b-instruct qwen3-vl:8b-instruct minicpm-v4.5}"
WITH_30B="${WITH_30B:-0}"       # 1 = also pull qwen3-vl:30b-a3b-instruct (~20 GB; needs >= 24 GB VRAM)
WITH_BF16="${WITH_BF16:-0}"     # 1 = also fetch MiniCPM-V 4.6 bf16 GGUFs (~2.6 GB) to test precision
LLAMA_CUDA="${LLAMA_CUDA:-12.8}"  # 12.8 or 13.4; pick the one <= the CUDA version nvidia-smi reports
MIN_FREE_GB="${MIN_FREE_GB:-45}"

# ---- pinned sources (GitHub release API / Hugging Face LFS metadata, 2026-10-03) --------------------
OLLAMA_VERSION="v0.35.1"
OLLAMA_TAR="ollama-linux-amd64.tar.zst"
# Download locations can be overridden (e.g. a mirror when github.com / huggingface.co are slow or blocked
# from the instance's region). Files are still verified against the pinned sha256 below, so a mirror
# cannot silently substitute different bytes. Ollama model pulls (registry.ollama.ai) are NOT sha-pinned here.
OLLAMA_URL="${OLLAMA_URL:-https://github.com/ollama/ollama/releases/download/${OLLAMA_VERSION}/${OLLAMA_TAR}}"
OLLAMA_SHA256="9fcd79ac4575b2bd31b992eee18b1000c8ad126b451627c8f8cd091714cfbb10"   # 1439.7 MB

LLAMA_TAG="b11146"
if [ "$LLAMA_CUDA" = "13.4" ]; then
  LLAMA_TAR="llama-${LLAMA_TAG}-bin-ubuntu-cuda-13.4-x64.tar.gz"
  LLAMA_SHA256="1603d9c00a4b6eac8298c5c7868cdb080a3ac31948ab1e457441d71ce274dd7e"   # 149.3 MB
  CUDART_TAR="cudart-llama-${LLAMA_TAG}-bin-ubuntu-cuda-13.4-x64.tar.gz"
  CUDART_SHA256="7c2af505f8b26ecd3707ab7723fa985fee1df233b7c1d60e5e17724b536d15bb"  # 440.2 MB
else
  LLAMA_TAR="llama-${LLAMA_TAG}-bin-ubuntu-cuda-12.8-x64.tar.gz"
  LLAMA_SHA256="c2ab9e19838513ff69d1af8d999ad717dd3c7ee4714ac04c7ed5ab9077c50e4e"   # 168.9 MB
  CUDART_TAR="cudart-llama-${LLAMA_TAG}-bin-ubuntu-cuda-12.8-x64.tar.gz"
  CUDART_SHA256="1466daea60aad1144819e151b2bae19d54556cf1da6c129c4f55a5ded2637c25"  # 594.4 MB
fi
LLAMA_BASE="${LLAMA_BASE:-https://github.com/ggml-org/llama.cpp/releases/download/${LLAMA_TAG}}"
HF_BASE="${HF_BASE:-https://huggingface.co/ggml-org/MiniCPM-V-4.6-GGUF/resolve/main}"
GGUF_MAIN="MiniCPM-V-4.6-Q4_K_M.gguf";        GGUF_MAIN_SHA="b1a5aa76b5ef039c2e579272ea33d4bbed7e79b49bb3ff1efdb23316d6af5199"  # 529.1 MB
GGUF_PROJ="mmproj-MiniCPM-V-4.6-Q8_0.gguf";   GGUF_PROJ_SHA="3d8249cdd0e1cb699644eb021fbcc04320aad89fa5dc9234ef94db0846556581"  # 728.0 MB
GGUF_BF16="MiniCPM-V-4.6-bf16.gguf";          GGUF_BF16_SHA="ba06adb9373cfa2ad34ef5b6b5fadc725df730b551d84675db6c5d576370b646"  # 1516.3 MB
GGUF_PROJ_BF16="mmproj-MiniCPM-V-4.6-bf16.gguf"; GGUF_PROJ_BF16_SHA="296d4c329dce9a801ca17c3091a869fd2b15fe456088137c96efe85dd277abfe"  # 1110.1 MB

step() { printf '\n=== %s ===\n' "$*"; }
fetch() {  # fetch URL DEST SHA256 : download if missing or mismatching, then verify
  local url="$1" dest="$2" want="$3"
  if [ -f "$dest" ] && [ "$(sha256sum "$dest" | cut -d' ' -f1)" = "$want" ]; then echo "ok (cached) $(basename "$dest")"; return; fi
  echo "downloading $(basename "$dest") ..."
  curl -fL --retry 3 --retry-delay 5 -o "$dest.part" "$url"
  local got; got="$(sha256sum "$dest.part" | cut -d' ' -f1)"
  if [ "$got" != "$want" ]; then echo "SHA256 MISMATCH for $dest: want $want got $got" >&2; rm -f "$dest.part"; exit 3; fi
  mv "$dest.part" "$dest"; echo "verified $(basename "$dest")"
}

mkdir -p "$WORK"/{downloads,ollama,ollama-models,llama,gguf,logs,results}
cd "$WORK"

step "preflight"
command -v curl >/dev/null || { echo "curl is required" >&2; exit 1; }
command -v nvidia-smi >/dev/null || { echo "nvidia-smi not found: this is not a working NVIDIA GPU instance" >&2; exit 1; }
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv
nvidia-smi | grep -m1 "CUDA Version" || true
FREE_GB="$(df -BG --output=avail "$WORK" | tail -1 | tr -dc '0-9')"
echo "free disk under $WORK: ${FREE_GB} GB (need >= ${MIN_FREE_GB})"
[ "$FREE_GB" -ge "$MIN_FREE_GB" ] || { echo "not enough disk; set a larger volume or MIN_FREE_GB lower" >&2; exit 1; }
if ! tar --help 2>&1 | grep -q zstd && ! command -v zstd >/dev/null; then
  echo "zstd is needed to unpack the Ollama archive: apt-get install -y zstd (root) or ask for an image with zstd" >&2; exit 1
fi
for host in github.com huggingface.co registry.ollama.ai; do
  curl -fsI --max-time 15 "https://$host" >/dev/null && echo "reachable: $host" || echo "WARNING: cannot reach $host"
done

step "Ollama ${OLLAMA_VERSION}"
fetch "$OLLAMA_URL" "downloads/$OLLAMA_TAR" "$OLLAMA_SHA256"
if [ ! -x ollama/bin/ollama ]; then tar --zstd -xf "downloads/$OLLAMA_TAR" -C ollama; fi
if ! curl -fs --max-time 3 http://127.0.0.1:11434/api/version >/dev/null; then
  OLLAMA_HOST=127.0.0.1:11434 OLLAMA_MODELS="$WORK/ollama-models" OLLAMA_NUM_PARALLEL="${OLLAMA_NUM_PARALLEL:-4}" \
    nohup ollama/bin/ollama serve >logs/ollama.log 2>&1 &
  disown
  for _ in $(seq 1 60); do curl -fs --max-time 2 http://127.0.0.1:11434/api/version >/dev/null && break; sleep 1; done
fi
curl -fs http://127.0.0.1:11434/api/version; echo
[ "$WITH_30B" = "1" ] && MODELS="$MODELS qwen3-vl:30b-a3b-instruct"
for model in $MODELS; do
  step "ollama pull $model"
  OLLAMA_HOST=127.0.0.1:11434 ollama/bin/ollama pull "$model"
done

step "llama.cpp ${LLAMA_TAG} (CUDA ${LLAMA_CUDA})"
fetch "$LLAMA_BASE/$LLAMA_TAR" "downloads/$LLAMA_TAR" "$LLAMA_SHA256"
[ -n "$(find llama -name llama-server -type f 2>/dev/null | head -1)" ] || tar -xzf "downloads/$LLAMA_TAR" -C llama
LLAMA_SERVER="$(find llama -name llama-server -type f | head -1)"
chmod +x "$LLAMA_SERVER"
LIBDIR="$(dirname "$WORK/$LLAMA_SERVER")"
if LD_LIBRARY_PATH="$LIBDIR" ldd "$LLAMA_SERVER" 2>/dev/null | grep -q "not found"; then
  echo "CUDA runtime libraries missing: fetching the matching cudart bundle"
  fetch "$LLAMA_BASE/$CUDART_TAR" "downloads/$CUDART_TAR" "$CUDART_SHA256"
  tar -xzf "downloads/$CUDART_TAR" -C "$(dirname "$LLAMA_SERVER")"
fi
export LD_LIBRARY_PATH="$LIBDIR:${LD_LIBRARY_PATH:-}"

step "MiniCPM-V 4.6 GGUF"
fetch "$HF_BASE/$GGUF_MAIN" "gguf/$GGUF_MAIN" "$GGUF_MAIN_SHA"
fetch "$HF_BASE/$GGUF_PROJ" "gguf/$GGUF_PROJ" "$GGUF_PROJ_SHA"
if [ "$WITH_BF16" = "1" ]; then
  fetch "$HF_BASE/$GGUF_BF16" "gguf/$GGUF_BF16" "$GGUF_BF16_SHA"
  fetch "$HF_BASE/$GGUF_PROJ_BF16" "gguf/$GGUF_PROJ_BF16" "$GGUF_PROJ_BF16_SHA"
fi
if ! curl -fs --max-time 3 http://127.0.0.1:8080/health >/dev/null; then
  nohup "$LLAMA_SERVER" -m "gguf/$GGUF_MAIN" --mmproj "gguf/$GGUF_PROJ" -ngl 99 --host 127.0.0.1 --port 8080 \
        --parallel 4 -c 8192 --reasoning off --jinja >logs/llama-server.log 2>&1 &
  disown
  for _ in $(seq 1 120); do curl -fs --max-time 2 http://127.0.0.1:8080/health >/dev/null && break; sleep 1; done
fi
# Not fatal: the prebuilt CUDA binary may not match this GPU/driver (e.g. an older Turing T4). Ollama is
# already up, so keep going and use the Ollama-only test path; the log says why llama-server failed.
if curl -fs http://127.0.0.1:8080/health; then echo
else
  echo "WARNING: llama-server is not healthy; see $WORK/logs/llama-server.log. Continuing with Ollama only." >&2
  tail -n 20 logs/llama-server.log >&2 || true
fi

step "audit record"
{
  echo "{"
  echo "  \"date\": \"$(date -Is)\","
  echo "  \"gpu\": \"$(nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader | head -1)\","
  echo "  \"ollama\": \"$(OLLAMA_HOST=127.0.0.1:11434 ollama/bin/ollama --version 2>&1 | tail -1)\","
  echo "  \"llama_server\": \"$("$LLAMA_SERVER" --version 2>&1 | grep -m1 version || true)\","
  echo "  \"models\": \"$MODELS\","
  echo "  \"kernel\": \"$(uname -sr)\""
  echo "}"
} | tee results/server_info.json

cat <<EOF

READY. From the laptop open the tunnel (keep it running):
  ssh -N -L 11434:127.0.0.1:11434 -L 8080:127.0.0.1:8080 -i <dedicated_key> -p <port> <user>@<host>
Then run the suite on the laptop with scripts/cloud/run_cloud_suite.py.
REMINDER: terminate the instance in the provider console when finished -- stopping a shell does not stop billing.
EOF
