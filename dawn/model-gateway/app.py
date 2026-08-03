from __future__ import annotations

import hmac
import json
import logging
import os
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

import httpx
from fastapi import FastAPI, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse, Response, StreamingResponse

LOG = logging.getLogger("dawn.model_gateway")
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(message)s",
)

HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
}

DEFAULT_ALIASES = {
    "dawn-fast": "dawn-fast",
    "dawn-local-reasoning": "dawn-local-reasoning",
}


@dataclass(frozen=True)
class Settings:
    upstream_base_url: str
    gateway_api_key: str
    upstream_api_key: str
    aliases: dict[str, str]
    compatibility_default_model: str | None
    request_timeout_seconds: float

    @classmethod
    def from_env(cls) -> "Settings":
        aliases_raw = os.getenv("DAWN_MODEL_ALIASES_JSON", json.dumps(DEFAULT_ALIASES))
        try:
            aliases = json.loads(aliases_raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError("DAWN_MODEL_ALIASES_JSON must be valid JSON") from exc
        if not isinstance(aliases, dict) or not aliases:
            raise RuntimeError("DAWN_MODEL_ALIASES_JSON must be a non-empty object")
        if any(not isinstance(k, str) or not isinstance(v, str) for k, v in aliases.items()):
            raise RuntimeError("Every model alias and target must be a string")

        gateway_api_key = os.getenv("DAWN_GATEWAY_API_KEY", "").strip()
        upstream_api_key = os.getenv("DAWN_LITELLM_MASTER_KEY", "").strip()
        if len(gateway_api_key) < 24:
            raise RuntimeError("DAWN_GATEWAY_API_KEY must contain at least 24 characters")
        if len(upstream_api_key) < 24:
            raise RuntimeError("DAWN_LITELLM_MASTER_KEY must contain at least 24 characters")

        compatibility_default = os.getenv("DAWN_COMPAT_DEFAULT_MODEL", "").strip() or None
        if compatibility_default and compatibility_default not in aliases:
            raise RuntimeError("DAWN_COMPAT_DEFAULT_MODEL must be one of the configured aliases")

        return cls(
            upstream_base_url=os.getenv(
                "DAWN_UPSTREAM_BASE_URL", "http://litellm:4000"
            ).rstrip("/"),
            gateway_api_key=gateway_api_key,
            upstream_api_key=upstream_api_key,
            aliases=aliases,
            compatibility_default_model=compatibility_default,
            request_timeout_seconds=float(os.getenv("DAWN_REQUEST_TIMEOUT_SECONDS", "300")),
        )


settings = Settings.from_env()
client = httpx.AsyncClient(timeout=httpx.Timeout(settings.request_timeout_seconds))


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await client.aclose()


app = FastAPI(title="DAWN Governed Model Gateway", version="1.0.0", lifespan=lifespan)


def _log(event: str, **fields: Any) -> None:
    LOG.info(json.dumps({"event": event, **fields}, separators=(",", ":"), default=str))


def _authenticate(authorization: str | None) -> None:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTH_REQUIRED", "message": "Bearer token required"},
        )
    supplied = authorization.removeprefix("Bearer ").strip()
    if not hmac.compare_digest(supplied, settings.gateway_api_key):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "AUTH_INVALID", "message": "Invalid gateway credential"},
        )


def _validate_and_resolve_model(payload: dict[str, Any]) -> tuple[str, str, bool]:
    requested = payload.get("model")
    compatibility_applied = False

    if not isinstance(requested, str) or not requested.strip():
        if settings.compatibility_default_model is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "code": "MODEL_REQUIRED",
                    "message": (
                        "The caller omitted model. Supply one approved DAWN alias: "
                        + ", ".join(sorted(settings.aliases))
                    ),
                },
            )
        requested = settings.compatibility_default_model
        payload["model"] = requested
        compatibility_applied = True

    requested = requested.strip()
    resolved = settings.aliases.get(requested)
    if resolved is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "MODEL_NOT_APPROVED",
                "message": f"Model '{requested}' is not an approved DAWN alias",
                "approved_models": sorted(settings.aliases),
            },
        )

    payload["model"] = resolved
    return requested, resolved, compatibility_applied


def _forward_headers(request: Request, request_id: str, requested: str, resolved: str) -> dict[str, str]:
    headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in HOP_BY_HOP_HEADERS and key.lower() != "authorization"
    }
    headers.update(
        {
            "Authorization": f"Bearer {settings.upstream_api_key}",
            "Content-Type": "application/json",
            "X-DAWN-Request-ID": request_id,
            "X-DAWN-Requested-Model": requested,
            "X-DAWN-Resolved-Model": resolved,
        }
    )
    return headers


def _response_headers(headers: httpx.Headers, request_id: str) -> dict[str, str]:
    result = {
        key: value
        for key, value in headers.items()
        if key.lower() not in HOP_BY_HOP_HEADERS and key.lower() != "content-encoding"
    }
    result["X-DAWN-Request-ID"] = request_id
    return result


@app.get("/healthz")
async def healthz() -> dict[str, Any]:
    return {"ok": True, "service": "dawn-model-gateway", "aliases": sorted(settings.aliases)}


@app.get("/readyz")
async def readyz() -> JSONResponse:
    try:
        response = await client.get(
            f"{settings.upstream_base_url}/health/liveliness",
            headers={"Authorization": f"Bearer {settings.upstream_api_key}"},
            timeout=10,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"upstream returned {response.status_code}")
    except Exception as exc:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"ok": False, "upstream": str(exc)},
        )
    return JSONResponse(content={"ok": True, "upstream": "litellm"})


@app.get("/v1/models")
async def models(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _authenticate(authorization)
    created = int(time.time())
    return {
        "object": "list",
        "data": [
            {"id": alias, "object": "model", "created": created, "owned_by": "dawn"}
            for alias in sorted(settings.aliases)
        ],
    }


async def _iterate_and_close(response: httpx.Response) -> AsyncIterator[bytes]:
    try:
        async for chunk in response.aiter_raw():
            yield chunk
    finally:
        await response.aclose()


@app.api_route("/v1/{path:path}", methods=["POST"])
async def proxy_v1(
    path: str,
    request: Request,
    authorization: str | None = Header(default=None),
) -> Response:
    _authenticate(authorization)
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())

    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_JSON", "message": "Request body must be valid JSON"},
        ) from exc
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_BODY", "message": "Request body must be a JSON object"},
        )

    requested, resolved, compatibility_applied = _validate_and_resolve_model(payload)
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    headers = _forward_headers(request, request_id, requested, resolved)
    upstream_url = f"{settings.upstream_base_url}/v1/{path}"
    stream = bool(payload.get("stream"))

    _log(
        "request_routed",
        request_id=request_id,
        path=path,
        requested_model=requested,
        resolved_model=resolved,
        compatibility_default_applied=compatibility_applied,
        stream=stream,
    )

    if stream:
        try:
            upstream_request = client.build_request("POST", upstream_url, headers=headers, content=body)
            upstream = await client.send(upstream_request, stream=True)
        except httpx.RequestError as exc:
            _log("upstream_unreachable", request_id=request_id, error=str(exc))
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={"code": "UPSTREAM_UNREACHABLE", "message": str(exc)},
            ) from exc
        if upstream.status_code >= 400:
            error_body = await upstream.aread()
            await upstream.aclose()
            _log(
                "upstream_error",
                request_id=request_id,
                status=upstream.status_code,
                body=error_body.decode("utf-8", errors="replace")[:2000],
            )
            return Response(
                content=error_body,
                status_code=upstream.status_code,
                headers=_response_headers(upstream.headers, request_id),
                media_type=upstream.headers.get("content-type"),
            )
        return StreamingResponse(
            _iterate_and_close(upstream),
            status_code=upstream.status_code,
            media_type=upstream.headers.get("content-type", "text/event-stream"),
            headers=_response_headers(upstream.headers, request_id),
        )

    try:
        upstream = await client.post(upstream_url, headers=headers, content=body)
    except httpx.RequestError as exc:
        _log("upstream_unreachable", request_id=request_id, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "UPSTREAM_UNREACHABLE", "message": str(exc)},
        ) from exc

    response_headers = _response_headers(upstream.headers, request_id)
    if upstream.status_code >= 400:
        _log(
            "upstream_error",
            request_id=request_id,
            status=upstream.status_code,
            body=upstream.text[:2000],
        )
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=response_headers,
        media_type=upstream.headers.get("content-type"),
    )
