"""Tests for CORS preflight handling and configuration."""
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.config import Settings


@pytest.fixture
def client():
    return TestClient(app)


def test_cors_preflight_localhost_3000_post_registration(client):
    """Verify OPTIONS preflight from http://localhost:3000 for POST /api/v1/patients/register

    returns 200 OK with proper CORS allow headers.
    """
    response = client.options(
        "/api/v1/patients/register",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert response.headers.get("access-control-allow-credentials") == "true"
    allow_methods = response.headers.get("access-control-allow-methods", "")
    assert "POST" in allow_methods
    allow_headers = response.headers.get("access-control-allow-headers", "").lower()
    assert "content-type" in allow_headers


def test_cors_preflight_127_0_0_1_3000(client):
    """Verify OPTIONS preflight from http://127.0.0.1:3000 returns 200 OK."""
    response = client.options(
        "/api/v1/patients/register",
        headers={
            "Origin": "http://127.0.0.1:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://127.0.0.1:3000"
    assert response.headers.get("access-control-allow-credentials") == "true"


def test_cors_preflight_with_authorization_header(client):
    """Verify preflight requests requesting authorization header are accepted."""
    response = client.options(
        "/api/v1/patients/register",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization, content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"
    allow_headers = response.headers.get("access-control-allow-headers", "").lower()
    assert "authorization" in allow_headers
    assert "content-type" in allow_headers


def test_cors_preflight_private_network(client):
    """Verify Chromium private network access preflight header is supported."""
    response = client.options(
        "/api/v1/patients/register",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
            "Access-Control-Request-Private-Network": "true",
        },
    )

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-private-network") == "true"


def test_cors_disallowed_origin_rejected(client):
    """Verify untrusted origin is rejected with 400 Bad Request."""
    response = client.options(
        "/api/v1/patients/register",
        headers={
            "Origin": "http://malicious-site.example.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 400
    assert "Disallowed CORS" in response.text


def test_cors_origins_parsing_logic():
    """Verify comma-separated origins are parsed properly into individual trimmed entries."""
    s = Settings(ALLOWED_ORIGINS="http://localhost:3000,http://127.0.0.1:3000")
    origins = s.cors_origins
    assert origins == ["http://localhost:3000", "http://127.0.0.1:3000"]
    assert "http://localhost:3000,http://127.0.0.1:3000" not in origins

    # Test with spaces
    s2 = Settings(ALLOWED_ORIGINS=" http://localhost:3000 ,  http://127.0.0.1:3000  ")
    assert s2.cors_origins == ["http://localhost:3000", "http://127.0.0.1:3000"]

    # Test with surrounding quotes and trailing slashes
    s3 = Settings(ALLOWED_ORIGINS='"http://localhost:3000/,http://127.0.0.1:3000/"')
    assert s3.cors_origins == ["http://localhost:3000", "http://127.0.0.1:3000"]
