#!/usr/bin/env bash
# Stop the model servers started by setup_server.sh (processes only; no files are removed).
# This does NOT stop billing: terminate the instance in the provider console.
set -u
WORK="${WORK:-$HOME/vi}"
# setup_server.sh starts Ollama with a relative path, so match the path-independent tail of the command line.
pkill -f "ollama/bin/ollama serve" 2>/dev/null && echo "stopped ollama" || echo "ollama not running"
pkill -f "llama-server .*--port 8080" 2>/dev/null && echo "stopped llama-server" || echo "llama-server not running"
