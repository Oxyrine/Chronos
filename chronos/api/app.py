"""Runnable API shell with production JWT authentication, role guards, and metrics.

Supports both httpOnly session cookies for the SPA dashboard and the legacy
owner bearer token for automated CLI scripts.
"""
import hmac
import os
import platform

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from chronos.api import auth
from chronos.api.auth import COOKIE_NAME, decode_token
from chronos.api.deps import current_user
from chronos.api.routers import agent, meta, risk, scan, shelflife, verify

app = FastAPI(title="Chronos", version="0.1.0")
bearer = HTTPBearer(auto_error=False)


def resolve_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer)
) -> dict:
    """Resolve user from chronos_session cookie or Bearer token."""
    # 1. Cookie-based authentication (SPA dashboard)
    cookie_token = request.cookies.get(COOKIE_NAME)
    if cookie_token:
        try:
            payload = decode_token(cookie_token)
            return {"sub": payload.get("sub", "anonymous"), "role": payload.get("role", "viewer")}
        except HTTPException:
            pass  # Fall back to bearer check

    # 2. Bearer token authentication (CLI scripts & automation)
    if credentials and credentials.credentials:
        expected = os.environ.get("CHRONOS_API_TOKEN", "")
        if expected and hmac.compare_digest(credentials.credentials, expected):
            return {"sub": "secops", "role": "security_engineer"}
        
        # Allow passing JWT in Authorization: Bearer <jwt> as well
        try:
            payload = decode_token(credentials.credentials)
            return {"sub": payload.get("sub", "anonymous"), "role": payload.get("role", "viewer")}
        except HTTPException:
            pass

    raise HTTPException(401, "authentication required", headers={"WWW-Authenticate": "Bearer"})


def require_role_guard(
    request: Request,
    user: dict = Depends(resolve_current_user)
) -> dict:
    """Guard mutative endpoints while allowing public auth endpoints and read-only viewers."""
    # Exempt login and logout from the mutation guard
    path = request.url.path
    if path in ("/api/auth/login", "/api/auth/logout"):
        return user

    if request.method not in ("GET", "HEAD", "OPTIONS"):
        if user.get("role") != "security_engineer":
            raise HTTPException(403, "security_engineer role required for mutative operations")

    return user


app.dependency_overrides[current_user] = resolve_current_user

# Mount auth routes (login/logout do not depend on require_role_guard)
app.include_router(auth.router, prefix="/api")

# Mount business routes protected by the role guard and authentication
for module in (scan, shelflife, risk, agent, verify, meta):
    app.include_router(module.router, prefix="/api", dependencies=[Depends(require_role_guard)])


@app.get("/health")
def health():
    nnpa_detected = False
    try:
        with open("/proc/cpuinfo", "r", encoding="utf-8") as f:
            nnpa_detected = "nnpa" in f.read().lower()
    except Exception:
        nnpa_detected = False

    return {
        "status": "ok",
        "arch": platform.machine(),
        "nnpa": nnpa_detected,
        "tls_groups": ["X25519MLKEM768", "X25519"]
    }
