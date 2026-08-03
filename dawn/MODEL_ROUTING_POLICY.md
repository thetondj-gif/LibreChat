# DAWN Model Routing Policy v1

## Governing rule

Every inference request must name an approved DAWN model alias. Provider model names are implementation details and must not be sent by operators, LibreChat agents, Hermes tasks, or departmental services.

Approved aliases:

| Alias | Initial upstream | Purpose |
|---|---|---|
| `dawn-fast` | `ollama/qwen3.5:9b` | Routine chat, extraction, triage and low-latency work |
| `dawn-local-reasoning` | `ollama/ministral-3:8b` | Bounded local reasoning and analysis |

## Missing-model behaviour

Production and acceptance default to strict mode:

```text
DAWN_COMPAT_DEFAULT_MODEL=
```

A request without `model` is rejected by the gateway with HTTP 422 and code `MODEL_REQUIRED`. This prevents the current opaque Ollama error from escaping into operator sessions and identifies the caller that emitted the malformed request.

A temporary compatibility default may be enabled only for a bounded repair canary:

```text
DAWN_COMPAT_DEFAULT_MODEL=dawn-fast
```

The gateway logs `compatibility_default_applied=true` for every repaired request. Compatibility mode must be removed once the offending caller has been fixed.

## Routing constraints

1. LibreChat connects only to the DAWN gateway, never directly to Ollama.
2. Hermes and DAWN services use `http://127.0.0.1:9180/v1` with an approved alias.
3. LiteLLM is private to the Compose network and has no host-published port.
4. Ollama remains host-local at `127.0.0.1:11434`.
5. LibreChat, its admin panel and the DAWN gateway bind only to loopback.
6. Automatic fallback between the two local models is disabled because the Mac mini currently has one practical inference-concurrency slot.
7. LibreChat title generation and automatic summarisation are disabled to prevent secondary model calls.
8. Hindsight remains the canonical DAWN operational memory. LibreChat memory is not configured in this overlay.

## Expansion gate

Cloud models, additional local models and departmental aliases may be added only after:

- the model has an explicit purpose and owner;
- budget, context and timeout limits are defined;
- prompt and response data classification is documented;
- failure and fallback behaviour is tested;
- Langfuse records requested alias, resolved provider model and caller identity;
- the alias is added consistently to `model-policy.json`, `litellm-config.yaml`, `librechat.yaml` and the gateway allowlist.
