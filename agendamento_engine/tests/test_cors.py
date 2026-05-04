"""
Testes de CORS para o Sprint 0.0a.

Estratégia:
  - Lógica de parse/validação testada diretamente (sem subir toda a app).
  - Comportamento do middleware testado com uma mini-app FastAPI isolada,
    usando as mesmas configurações que main.py aplica.
"""
import os

import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient


# ─── helpers ──────────────────────────────────────────────────────────────────

def _parse_origins(raw: str) -> list[str]:
    """Replica exatamente a lógica de main.py."""
    raw = raw.strip()
    if not raw:
        raise RuntimeError("ALLOWED_ORIGINS não está definido.")
    return [o.strip() for o in raw.split(",") if o.strip()]


def _make_app(origins: list[str]) -> TestClient:
    app = FastAPI()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return TestClient(app, raise_server_exceptions=False)


# ─── testes de parse ───────────────────────────────────────────────────────────

def test_parse_single_origin():
    assert _parse_origins("http://localhost:3000") == ["http://localhost:3000"]


def test_parse_multiple_origins():
    result = _parse_origins(
        "http://localhost:3000,https://app.example.com, https://painel.example.com"
    )
    assert result == [
        "http://localhost:3000",
        "https://app.example.com",
        "https://painel.example.com",
    ]


def test_parse_empty_string_raises():
    with pytest.raises(RuntimeError, match="ALLOWED_ORIGINS"):
        _parse_origins("")


def test_parse_whitespace_only_raises():
    with pytest.raises(RuntimeError, match="ALLOWED_ORIGINS"):
        _parse_origins("   ")


# ─── testes de comportamento do middleware ────────────────────────────────────

def test_allowed_origin_receives_cors_header():
    client = _make_app(["http://localhost:3000"])
    resp = client.get("/health", headers={"Origin": "http://localhost:3000"})
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_unlisted_origin_gets_no_cors_header():
    client = _make_app(["http://localhost:3000"])
    resp = client.get("/health", headers={"Origin": "http://evil.example.com"})
    assert "access-control-allow-origin" not in resp.headers


def test_preflight_unlisted_origin_returns_400():
    client = _make_app(["http://localhost:3000"])
    resp = client.options(
        "/health",
        headers={
            "Origin": "http://evil.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resp.status_code == 400


def test_multiple_origins_each_allowed():
    origins = ["http://localhost:3000", "https://app.example.com"]
    for origin in origins:
        client = _make_app(origins)
        resp = client.get("/health", headers={"Origin": origin})
        assert resp.headers.get("access-control-allow-origin") == origin


# ─── teste de startup (leitura do env) ───────────────────────────────────────

def test_startup_fails_without_env_var(monkeypatch):
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    raw = os.getenv("ALLOWED_ORIGINS", "")
    with pytest.raises(RuntimeError, match="ALLOWED_ORIGINS"):
        _parse_origins(raw)
