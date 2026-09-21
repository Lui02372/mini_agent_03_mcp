#!/usr/bin/env bash
set -Eeuo pipefail
release_id=${1:?release id required}
[[ "$release_id" =~ ^[a-zA-Z0-9_-]+$ ]] || exit 2
root=/opt/mini-agent-mcp
release="$root/releases/$release_id"
exec 9>"$root/deploy.lock"
flock -n 9 || { echo "Another deployment is running"; exit 1; }
cd "$release"
export APP_IMAGE="mini-agent-mcp:$release_id"
env_file="$release/env/.env.docker"
if [[ ! -s "$env_file" ]]; then
  install -m 600 "$root/shared/.env.docker" "$env_file"
fi
[[ -s "$env_file" ]] || { echo "Missing runtime env"; exit 1; }
compose=(sudo --preserve-env=APP_IMAGE docker compose --env-file "$env_file" -f "$release/env/compose.yml")
"${compose[@]}" config --quiet
if [[ "${2:-}" == "--build" ]]; then
  "${compose[@]}" build backend
else
  sudo docker image inspect "$APP_IMAGE" >/dev/null
fi
if ! "${compose[@]}" run --rm --no-deps backend python ops/check_services.py --data; then
  if grep -qx 'REQUIRE_DATA_SERVICES=true' "$env_file"; then
    echo "External data service check failed; deployment stopped."
    exit 1
  fi
  echo "WARNING: external DB/Redis unavailable. This MCP demo has no storage feature."
fi
previous=$(readlink -f "$root/current" || true)
rollback() {
  echo "Deployment failed; attempting rollback"
  "${compose[@]}" ps
  if [[ -n "$previous" && -f "$previous/env/compose.yml" && "$previous" != "$release" ]]; then
    export APP_IMAGE="mini-agent-mcp:$(basename "$previous")"
    sudo --preserve-env=APP_IMAGE docker compose --env-file "$previous/env/.env.docker" -f "$previous/env/compose.yml" up -d --no-build --wait --wait-timeout 180
  fi
}
trap rollback ERR
"${compose[@]}" up -d --no-build --wait --wait-timeout 180
"${compose[@]}" exec -T backend python ops/check_services.py
ln -sfn "$release" "$root/current"
trap - ERR
"${compose[@]}" ps
