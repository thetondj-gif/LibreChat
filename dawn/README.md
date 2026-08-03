# DAWN Governed LibreChat Overlay

Status: **PREPARED FOR HOST CANARY — NOT AUTO-DEPLOYED**

This directory adds a reversible operator interface and governed model-routing layer to the LibreChat fork without modifying LibreChat application code.

## What this package does

```text
LibreChat UI ──► DAWN model gateway ──► LiteLLM ──► Ollama on the Mac mini
Hermes/DAWN ───► DAWN model gateway ──► LiteLLM ──► approved providers
```

The model gateway stops malformed requests before they reach Ollama. A request must specify `dawn-fast` or `dawn-local-reasoning`; otherwise it receives a structured `MODEL_REQUIRED` or `MODEL_NOT_APPROVED` response.

The initial deployment is deliberately local-only:

- LibreChat: `http://127.0.0.1:3080`
- LibreChat admin: `http://127.0.0.1:3081`
- DAWN OpenAI-compatible gateway: `http://127.0.0.1:9180/v1`
- LiteLLM: Compose-network only; no host port
- Ollama: existing host service at `http://127.0.0.1:11434`

No production DAWN service is stopped or rewritten by these files.

## Included controls

- Fixed, approved model aliases instead of a dynamically fetched model catalogue.
- Strict missing-model rejection by default.
- Optional, auditable compatibility default for one bounded repair canary.
- Loopback-only host bindings.
- Automatically generated gateway, LiteLLM and admin credentials.
- Apple Silicon-compatible MongoDB override.
- Disabled LibreChat title generation and automatic summarisation.
- No automatic fallback that could load a second Ollama model.
- Health, readiness and missing-model acceptance checks.
- A clean stop path using the same Compose project.

## Mac mini deployment sequence

From the root of this LibreChat checkout:

```bash
./dawn/scripts/bootstrap.sh
./dawn/scripts/start.sh
```

`bootstrap.sh` performs the following before any container is started:

1. Requires Docker Compose 2.24.4 or newer.
2. Creates `.env` from `.env.example` only when absent.
3. Creates `dawn/.env.dawn` with cryptographically random credentials only when absent.
4. Confirms Ollama is reachable.
5. Confirms `qwen3.5:9b` and `ministral-3:8b` are installed.
6. Validates the merged Compose configuration.

`start.sh` builds the small DAWN gateway image, starts the stack and runs the acceptance checks.

## Hermes connection

After the canary passes, configure the Hermes OpenAI-compatible provider with:

```text
Base URL: http://127.0.0.1:9180/v1
API key:  DAWN_GATEWAY_API_KEY from dawn/.env.dawn
Model:    dawn-fast
```

For bounded analysis tasks, Hermes may explicitly request:

```text
model=dawn-local-reasoning
```

Hermes must never leave the model field blank. The gateway will reject blank models before they reach Ollama.

## Temporary compatibility repair mode

Strict mode is the default and the intended end state. If the currently broken caller cannot be patched in the same session, edit only this line in `dawn/.env.dawn`:

```text
DAWN_COMPAT_DEFAULT_MODEL=dawn-fast
```

Restart only the gateway:

```bash
docker compose \
  --env-file .env \
  --env-file dawn/.env.dawn \
  -f docker-compose.yml \
  -f dawn/docker-compose.dawn.yml \
  up -d --build dawn-model-gateway
```

Every repaired request is logged with `compatibility_default_applied=true`. Remove the compatibility value after the caller is corrected and rerun `./dawn/scripts/verify.sh`.

## Acceptance criteria

The overlay is ready to connect to Hermes only when all conditions pass:

```bash
./dawn/scripts/verify.sh
```

Expected terminal verdict:

```text
DAWN_READY
```

The verification proves:

- gateway liveness;
- LiteLLM readiness through the gateway;
- LibreChat API availability;
- exact approved model catalogue;
- strict rejection of a missing model;
- loopback URLs for the operator interfaces.

A separate manual inference canary should then be run in LibreChat with each alias while Ollama and Langfuse are observed. Do not enable both models concurrently.

## Observability

The gateway emits structured JSON logs containing:

- request ID;
- path;
- requested alias;
- resolved alias;
- whether compatibility mode repaired the request;
- streaming mode;
- upstream status and bounded error text on failure.

LibreChat also forwards DAWN caller, user and conversation headers. These are intended for gateway/trace correlation and must not be forwarded to external providers unless the provider policy explicitly permits them.

## Rollback

```bash
./dawn/scripts/stop.sh
```

This stops containers in the LibreChat Compose project. It does not stop Ollama, Hermes, the DAWN dispatcher, Hindsight, Qdrant, Langfuse or the existing V2 rebuild services.

To preserve the generated credentials for a later retry, retain `dawn/.env.dawn`. To reset the overlay completely, remove that file only after the stack is stopped.

## Files

| File | Purpose |
|---|---|
| `docker-compose.dawn.yml` | Loopback-bound LibreChat override plus LiteLLM and the DAWN gateway |
| `librechat.yaml` | Restricted DAWN endpoint and operator interface configuration |
| `litellm-config.yaml` | Alias-to-Ollama routing |
| `model-policy.json` | Machine-readable initial model policy |
| `MODEL_ROUTING_POLICY.md` | Governance and expansion rules |
| `model-gateway/` | Strict OpenAI-compatible validation and proxy service |
| `scripts/bootstrap.sh` | Non-destructive preflight and secret generation |
| `scripts/start.sh` | Start plus acceptance verification |
| `scripts/verify.sh` | Health, readiness, model-list and missing-model tests |
| `scripts/stop.sh` | Reversible shutdown |

## Deliberately deferred

The following are not enabled in this preparation branch:

- public or LAN exposure;
- Cloudflare tunnel or external authentication;
- cloud model credentials;
- automatic provider fallback;
- LibreChat memory duplication;
- departmental MCP permissions;
- agents created through the LibreChat database;
- automatic changes to Hermes configuration;
- merge into the live DAWN V2 branch.

Those changes require host evidence after the isolated canary succeeds.
