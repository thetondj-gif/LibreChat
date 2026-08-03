#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DAWN_ENV="$ROOT_DIR/dawn/.env.dawn"
[[ -f "$DAWN_ENV" ]] || { echo "Missing $DAWN_ENV" >&2; exit 1; }
set -a
# shellcheck disable=SC1090
source "$DAWN_ENV"
set +a

retry() {
  local attempts="$1"; shift
  local delay="$1"; shift
  local n=1
  until "$@"; do
    if (( n >= attempts )); then return 1; fi
    sleep "$delay"
    n=$((n + 1))
  done
}

retry 30 2 curl --fail --silent "http://127.0.0.1:${DAWN_GATEWAY_PORT}/healthz" >/dev/null
retry 30 2 curl --fail --silent "http://127.0.0.1:${DAWN_GATEWAY_PORT}/readyz" >/dev/null
retry 30 2 curl --fail --silent "http://127.0.0.1:${DAWN_LIBRECHAT_PORT}/api/health" >/dev/null

models="$(curl --fail --silent \
  -H "Authorization: Bearer ${DAWN_GATEWAY_API_KEY}" \
  "http://127.0.0.1:${DAWN_GATEWAY_PORT}/v1/models")"
python3 - "$models" <<'PY'
import json, sys
payload = json.loads(sys.argv[1])
ids = {m['id'] for m in payload['data']}
expected = {'dawn-fast', 'dawn-local-reasoning'}
assert ids == expected, (ids, expected)
print('Approved aliases:', ', '.join(sorted(ids)))
PY

status_code="$(curl --silent --output /tmp/dawn-missing-model.json --write-out '%{http_code}' \
  -H "Authorization: Bearer ${DAWN_GATEWAY_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"health probe"}]}' \
  "http://127.0.0.1:${DAWN_GATEWAY_PORT}/v1/chat/completions")"
if [[ "$status_code" != "422" && -z "${DAWN_COMPAT_DEFAULT_MODEL:-}" ]]; then
  echo "Missing-model guard failed: expected 422, received $status_code" >&2
  cat /tmp/dawn-missing-model.json >&2
  exit 1
fi

printf 'DAWN_READY\nLibreChat: http://127.0.0.1:%s\nAdmin: http://127.0.0.1:%s\nGateway: http://127.0.0.1:%s\n' \
  "$DAWN_LIBRECHAT_PORT" "$DAWN_ADMIN_PORT" "$DAWN_GATEWAY_PORT"
