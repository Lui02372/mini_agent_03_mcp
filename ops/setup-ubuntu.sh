#!/usr/bin/env bash
set -Eeuo pipefail
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-v2
sudo systemctl enable --now docker
sudo install -d -o "$(id -un)" -g "$(id -gn)" -m 700 /opt/mini-agent-mcp /opt/mini-agent-mcp/shared /opt/mini-agent-mcp/releases
sudo docker compose version
