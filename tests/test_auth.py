"""Tests for Chronos API authentication, session management, and role-based access control."""
import os
import pytest
from fastapi.testclient import TestClient

from chronos.api.app import app
from chronos.api.auth import hash_password, COOKIE_NAME, _FAILED_LOGINS


@pytest.fixture
def auth_env(monkeypatch):
    """Setup test users and environment."""
    viewer_hash = hash_password("viewer_secret_pass")
    secops_hash = hash_password("secops_secret_pass")
    monkeypatch.setenv("CHRONOS_USERS", f"viewer:{viewer_hash},secops:{secops_hash}")
    monkeypatch.setenv("CHRONOS_JWT_SECRET", "test-jwt-secret-for-pytest-execution-only")
    monkeypatch.setenv("CHRONOS_API_TOKEN", "test-legacy-bearer-token-secops")
    monkeypatch.setenv("CHRONOS_USE_SAMPLES", "0")
    _FAILED_LOGINS.clear()
    return {"viewer_pw": "viewer_secret_pass", "secops_pw": "secops_secret_pass"}


def test_health_public(auth_env):
    client = TestClient(app, base_url="https://testserver")
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert "arch" in data
    assert "nnpa" in data
    assert data["nnpa"] is False or isinstance(data["nnpa"], bool)
    assert "X25519MLKEM768" in data["tls_groups"]


def test_login_successful_sets_cookie(auth_env):
    client = TestClient(app, base_url="https://testserver")
    res = client.post("/api/auth/login", json={"username": "viewer", "password": auth_env["viewer_pw"]})
    assert res.status_code == 200
    assert res.json() == {"sub": "viewer", "role": "viewer"}
    assert COOKIE_NAME in res.cookies

    # Check /api/me with session cookie
    me_res = client.get("/api/auth/me")
    assert me_res.status_code == 200
    assert me_res.json() == {"sub": "viewer", "role": "viewer"}


def test_login_secops_role(auth_env):
    client = TestClient(app, base_url="https://testserver")
    res = client.post("/api/auth/login", json={"username": "secops", "password": auth_env["secops_pw"]})
    assert res.status_code == 200
    assert res.json() == {"sub": "secops", "role": "security_engineer"}

    me_res = client.get("/api/auth/me")
    assert me_res.status_code == 200
    assert me_res.json()["role"] == "security_engineer"


def test_login_invalid_password(auth_env):
    client = TestClient(app, base_url="https://testserver")
    res = client.post("/api/auth/login", json={"username": "viewer", "password": "wrong_password"})
    assert res.status_code == 401
    assert "invalid credentials" in res.json()["detail"]


def test_login_unknown_user(auth_env):
    client = TestClient(app, base_url="https://testserver")
    res = client.post("/api/auth/login", json={"username": "nonexistent", "password": "some_password"})
    assert res.status_code == 401
    assert "invalid credentials" in res.json()["detail"]


def test_login_rate_limiting(auth_env):
    client = TestClient(app, base_url="https://testserver")
    for _ in range(5):
        res = client.post("/api/auth/login", json={"username": "viewer", "password": "wrong_password"})
        assert res.status_code == 401
    
    # 6th attempt should be blocked by rate limiter (HTTP 429)
    res = client.post("/api/auth/login", json={"username": "viewer", "password": "wrong_password"})
    assert res.status_code == 429
    assert "too many" in res.json()["detail"].lower()


def test_logout_clears_cookie(auth_env):
    client = TestClient(app, base_url="https://testserver")
    client.post("/api/auth/login", json={"username": "viewer", "password": auth_env["viewer_pw"]})
    logout_res = client.post("/api/auth/logout")
    assert logout_res.status_code == 200
    
    # After logout, accessing protected endpoint without cookie fails
    client.cookies.clear()
    unauth = client.get("/api/auth/me")
    assert unauth.status_code == 401


def test_viewer_cannot_mutate_gets_403(auth_env, monkeypatch):
    monkeypatch.setenv("CHRONOS_USE_SAMPLES", "1")
    client = TestClient(app, base_url="https://testserver")
    client.post("/api/auth/login", json={"username": "viewer", "password": auth_env["viewer_pw"]})

    # Viewer CAN read GET endpoints
    assert client.get("/api/findings").status_code == 200
    assert client.get("/api/exposure").status_code == 200

    # Viewer CANNOT execute mutative endpoints (HTTP 403)
    assert client.post("/api/scan").status_code == 403
    assert client.post("/api/shelflife/run").status_code == 403
    assert client.post("/api/shelflife/patients/ssn/override", json={"category": "clinical", "reason": "test"}).status_code == 403
    assert client.post("/api/proposals", json={"finding_id": "F-001"}).status_code == 403
    assert client.post("/api/proposals/P-0001/approve").status_code == 403


def test_secops_can_mutate(auth_env, monkeypatch):
    monkeypatch.setenv("CHRONOS_USE_SAMPLES", "1")
    client = TestClient(app, base_url="https://testserver")
    client.post("/api/auth/login", json={"username": "secops", "password": auth_env["secops_pw"]})

    # Secops is allowed on mutative endpoints
    scan_res = client.post("/api/scan")
    assert scan_res.status_code != 403
    assert scan_res.status_code == 200


def test_legacy_bearer_token_authenticates_secops(auth_env, monkeypatch):
    monkeypatch.setenv("CHRONOS_USE_SAMPLES", "1")
    client = TestClient(app, base_url="https://testserver")
    headers = {"Authorization": f"Bearer {os.environ['CHRONOS_API_TOKEN']}"}

    me_res = client.get("/api/auth/me", headers=headers)
    assert me_res.status_code == 200
    assert me_res.json()["role"] == "security_engineer"
    assert me_res.json()["sub"] == "secops"

    # Can execute mutative action with bearer token
    scan_res = client.post("/api/scan", headers=headers)
    assert scan_res.status_code == 200


def test_session_cookie_is_secure_httponly_strict(auth_env):
    client = TestClient(app, base_url="https://testserver")
    res = client.post("/api/auth/login", json={"username": "viewer", "password": auth_env["viewer_pw"]})
    header = res.headers["set-cookie"].lower()
    assert "secure" in header and "httponly" in header and "samesite=strict" in header


def test_no_unauthenticated_access_in_sample_mode(auth_env, monkeypatch):
    """Sample mode used to grant secops to anyone; it must require a login like real mode."""
    monkeypatch.setenv("CHRONOS_USE_SAMPLES", "1")
    client = TestClient(app, base_url="https://testserver")
    assert client.get("/api/auth/me").status_code == 401
    assert client.post("/api/scan").status_code == 401


def test_missing_jwt_secret_fails_closed(auth_env, monkeypatch):
    monkeypatch.delenv("CHRONOS_JWT_SECRET")
    client = TestClient(app, base_url="https://testserver")
    res = client.post("/api/auth/login", json={"username": "viewer", "password": auth_env["viewer_pw"]})
    assert res.status_code == 503
    # a token forged with the old hard-coded fallback secret must not be accepted
    import jwt
    forged = jwt.encode({"sub": "secops", "role": "security_engineer", "exp": 9999999999},
                        "chronos-insecure-dev-secret-32-bytes-long!", algorithm="HS256")
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {forged}"}).status_code == 401


def test_dev_passwords_only_in_sample_mode(auth_env, monkeypatch):
    monkeypatch.setenv("CHRONOS_USERS", "")
    monkeypatch.setenv("CHRONOS_ALLOW_DEV_PASSWORDS", "1")
    client = TestClient(app, base_url="https://testserver")
    assert client.post("/api/auth/login", json={"username": "secops", "password": "secops"}).status_code == 401
    monkeypatch.setenv("CHRONOS_USE_SAMPLES", "1")
    assert client.post("/api/auth/login", json={"username": "secops", "password": "secops"}).status_code == 200
