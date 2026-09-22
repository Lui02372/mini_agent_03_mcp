#!/usr/bin/env bash
set -euo pipefail
# CPU-only install on the application EC2. Keep GPU packages off this small host.
command -v zstd >/dev/null || sudo apt-get install -y zstd
if ! command -v ollama >/dev/null; then
  curl -fsSL https://ollama.com/download/ollama-linux-amd64.tar.zst | zstd -d | sudo tar -xf - -C /usr/local --exclude='*/cuda*' --exclude='*/vulkan*' --exclude='*/rocm*' --exclude='*/mlx*'
fi
id ollama >/dev/null 2>&1 || sudo useradd -r -s /bin/false -U -m -d /usr/share/ollama ollama
sudo install -m 644 "$(dirname "$0")/ollama.service" /etc/systemd/system/ollama.service
sudo systemctl daemon-reload
sudo systemctl enable --now ollama
sleep 3
OLLAMA_HOST=172.17.0.1:11434 ollama pull qwen3:1.7b
OLLAMA_HOST=172.17.0.1:11434 ollama pull gemma3:1b
OLLAMA_HOST=172.17.0.1:11434 ollama list
