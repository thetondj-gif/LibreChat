#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
docker compose \
  --env-file "$ROOT_DIR/.env" \
  --env-file "$ROOT_DIR/dawn/.env.dawn" \
  -f "$ROOT_DIR/docker-compose.yml" \
  -f "$ROOT_DIR/dawn/docker-compose.dawn.yml" \
  down
