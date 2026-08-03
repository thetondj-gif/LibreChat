#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
[[ -f "$ROOT_DIR/.env" ]] || { echo "Run: bash dawn/scripts/bootstrap.sh" >&2; exit 1; }
[[ -f "$ROOT_DIR/dawn/.env.dawn" ]] || { echo "Run: bash dawn/scripts/bootstrap.sh" >&2; exit 1; }

docker compose \
  --env-file "$ROOT_DIR/.env" \
  --env-file "$ROOT_DIR/dawn/.env.dawn" \
  -f "$ROOT_DIR/docker-compose.yml" \
  -f "$ROOT_DIR/dawn/docker-compose.dawn.yml" \
  up -d --build

bash "$ROOT_DIR/dawn/scripts/verify.sh"
