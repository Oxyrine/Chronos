"""Runnable API shell. C can mount these routers in the final dashboard server.

The tunnel-only deployment uses a generated owner bearer token. C's JWT login
can replace the dependency without changing any router or worker permissions.
"""
import hmac
import os
import platform

from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from chronos.api.deps import current_user
from chronos.api.routers import agent, risk, scan, shelflife, verify

app = FastAPI(title="Chronos", version="0.1.0")
bearer = HTTPBearer(auto_error=False)


def owner(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> dict:
    expected = os.environ.get("CHRONOS_API_TOKEN", "")
    if not expected or credentials is None or not hmac.compare_digest(credentials.credentials, expected):
        raise HTTPException(401, "owner bearer token required", headers={"WWW-Authenticate": "Bearer"})
    return {"sub": "secops", "role": "security_engineer"}


app.dependency_overrides[current_user] = owner
for module in (scan, shelflife, risk, agent, verify):
    app.include_router(module.router, prefix="/api", dependencies=[Depends(owner)])


@app.get("/health")
def health():
    return {"status": "ok", "arch": platform.machine()}
