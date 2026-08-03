from __future__ import annotations

import importlib
import json

import pytest
from fastapi import HTTPException


@pytest.fixture()
def gateway(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DAWN_GATEWAY_API_KEY", "g" * 32)
    monkeypatch.setenv("DAWN_LITELLM_MASTER_KEY", "l" * 32)
    monkeypatch.setenv(
        "DAWN_MODEL_ALIASES_JSON",
        json.dumps({"dawn-fast": "dawn-fast", "dawn-local-reasoning": "dawn-local-reasoning"}),
    )
    monkeypatch.delenv("DAWN_COMPAT_DEFAULT_MODEL", raising=False)
    import app

    return importlib.reload(app)


def test_missing_model_is_rejected(gateway):
    with pytest.raises(HTTPException) as exc:
        gateway._validate_and_resolve_model({"messages": []})
    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "MODEL_REQUIRED"


def test_unknown_model_is_rejected(gateway):
    with pytest.raises(HTTPException) as exc:
        gateway._validate_and_resolve_model({"model": "raw-ollama-model"})
    assert exc.value.detail["code"] == "MODEL_NOT_APPROVED"


def test_approved_alias_is_preserved(gateway):
    payload = {"model": "dawn-fast"}
    requested, resolved, compatibility = gateway._validate_and_resolve_model(payload)
    assert requested == "dawn-fast"
    assert resolved == "dawn-fast"
    assert compatibility is False
    assert payload["model"] == "dawn-fast"


def test_compatibility_default_is_explicit(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DAWN_GATEWAY_API_KEY", "g" * 32)
    monkeypatch.setenv("DAWN_LITELLM_MASTER_KEY", "l" * 32)
    monkeypatch.setenv("DAWN_MODEL_ALIASES_JSON", json.dumps({"dawn-fast": "dawn-fast"}))
    monkeypatch.setenv("DAWN_COMPAT_DEFAULT_MODEL", "dawn-fast")
    import app

    gateway = importlib.reload(app)
    payload: dict[str, object] = {}
    requested, resolved, compatibility = gateway._validate_and_resolve_model(payload)
    assert (requested, resolved, compatibility) == ("dawn-fast", "dawn-fast", True)
    assert payload["model"] == "dawn-fast"
