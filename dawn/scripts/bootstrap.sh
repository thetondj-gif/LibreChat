#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DAWN_ENV="$ROOT_DIR/dawn/.env.dawn"
ROOT_ENV="$ROOT_DIR/.env"

fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
info() { printf 'DAWN: %s\n' "$*"; }

command -v docker >/dev/null 2>&1 || fail "Docker is not installed."
docker compose version >/dev/null 2>&1 || fail "Docker Compose v2 is not available."
command -v openssl >/dev/null 2>&1 || fail "openssl is required to generate credentials."
command -v curl >/dev/null 2>&1 || fail "curl is required for preflight checks."
command -v python3 >/dev/null 2>&1 || fail "python3 is required for validation."

compose_version="$(docker compose version --short | sed 's/^v//')"
python3 - "$compose_version" <<'PY' || fail "Docker Compose 2.24.4 or newer is required for !override port containment."
import re, sys
parts = [int(x) for x in re.findall(r'\d+', sys.argv[1])[:3]]
parts += [0] * (3 - len(parts))
raise SystemExit(0 if tuple(parts) >= (2, 24, 4) else 1)
PY

if [[ ! -f "$ROOT_ENV" ]]; then
  cp "$ROOT_DIR/.env.example" "$ROOT_ENV"
  info "Created root .env from .env.example."
fi

if [[ ! -f "$DAWN_ENV" ]]; then
  umask 077
  cat > "$DAWN_ENV" <<ENV
DAWN_LIBRECHAT_PORT=3080
DAWN_ADMIN_PORT=3081
DAWN_GATEWAY_PORT=9180
DAWN_ALLOW_REGISTRATION=true
DAWN_COMPAT_DEFAULT_MODEL=
DAWN_GATEWAY_API_KEY=$(openssl rand -hex 32)
DAWN_LITELLM_MASTER_KEY=$(openssl rand -hex 32)
ADMIN_PANEL_SESSION_SECRET=$(openssl rand -hex 32)
ENV
  info "Generated dawn/.env.dawn with mode 600."
else
  info "Using existing dawn/.env.dawn; no credentials were replaced."
fi
chmod 600 "$DAWN_ENV"

ollama_json="$(curl --fail --silent --show-error http://127.0.0.1:11434/api/tags)" \
  || fail "Ollama is not reachable at http://127.0.0.1:11434."
python3 - "$ollama_json" <<'PY' || fail "Required Ollama models are missing. Pull qwen3.5:9b and ministral-3:8b before deployment."
import json, sys
payload = json.loads(sys.argv[1])
names = {m.get('name') for m in payload.get('models', [])}
required = {'qwen3.5:9b', 'ministral-3:8b'}
missing = sorted(required - names)
if missing:
    print('Missing:', ', '.join(missing))
    raise SystemExit(1)
print('Ollama models present:', ', '.join(sorted(required)))
PY

compose=(
  docker compose
  --env-file "$ROOT_ENV"
  --env-file "$DAWN_ENV"
  -f "$ROOT_DIR/docker-compose.yml"
  -f "$ROOT_DIR/dawn/docker-compose.dawn.yml"
)

"${compose[@]}" config --quiet
info "Compose configuration validated."
info "Prepared. Start with: dawn/scripts/start.sh"
