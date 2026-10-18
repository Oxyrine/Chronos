"""Authentication, role resolution, and session management for Chronos API."""
import hashlib
import hmac
import os
import secrets
import time
from datetime import datetime, timezone
from typing import Dict, List, Tuple

import jwt
from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from chronos.api.deps import current_user
from chronos.common import samples

router = APIRouter(prefix="/auth", tags=["auth"])

# Rate limiting state: key = "{username}:{ip}" -> list of failure timestamps
_FAILED_LOGINS: Dict[str, List[float]] = {}
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_WINDOW_SECONDS = 15 * 60  # 15 minutes
TOKEN_EXPIRY_SECONDS = 8 * 3600   # 8 hours
COOKIE_NAME = "chronos_session"


class LoginRequest(BaseModel):
    username: str
    password: str


def hash_password(password: str, salt: bytes | None = None) -> str:
    """Generate scrypt hash with format <salt_hex>$<hash_hex>."""
    if salt is None:
        salt = secrets.token_bytes(16)
    key = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=16384, r=8, p=1)
    return f"{salt.hex()}${key.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify password against stored <salt_hex>$<hash_hex> in constant time."""
    try:
        salt_hex, hash_hex = stored_hash.split("$", 1)
        salt = bytes.fromhex(salt_hex)
        expected_hash = bytes.fromhex(hash_hex)
        computed = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=16384, r=8, p=1)
        return hmac.compare_digest(computed, expected_hash)
    except (ValueError, TypeError):
        return False


def _get_configured_users() -> Dict[str, Tuple[str, str]]:
    """Parse CHRONOS_USERS env var: 'user1:hash1,user2:hash2'.
    
    Returns: dict mapping username -> (stored_hash, role)
    """
    users_raw = os.environ.get("CHRONOS_USERS", "").strip()
    users: Dict[str, Tuple[str, str]] = {}
    if users_raw:
        for item in users_raw.split(","):
            item = item.strip()
            if ":" in item:
                uname, uhash = item.split(":", 1)
                role = "security_engineer" if uname == "secops" else "viewer"
                users[uname] = (uhash, role)
    return users


def _clean_rate_limit(key: str, now: float) -> List[float]:
    """Prune timestamps older than the lockout window."""
    attempts = [ts for ts in _FAILED_LOGINS.get(key, []) if now - ts < LOCKOUT_WINDOW_SECONDS]
    _FAILED_LOGINS[key] = attempts
    return attempts


def _get_client_ip(request: Request) -> str:
    """Extract client IP, trusting X-Real-IP if set by Nginx reverse proxy."""
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "127.0.0.1"


# Signs dev-only sessions in sample mode; never used once a real secret is configured.
_EPHEMERAL_DEV_SECRET = secrets.token_hex(32)


def get_jwt_secret() -> str:
    """CHRONOS_JWT_SECRET, or fail closed. Only sample-mode dev logins may use a per-process random secret."""
    secret = os.environ.get("CHRONOS_JWT_SECRET", "").strip()
    if secret:
        return secret
    if samples.use_samples() and _dev_passwords_allowed():
        return _EPHEMERAL_DEV_SECRET
    raise HTTPException(503, "CHRONOS_JWT_SECRET is not configured; run scripts/run_all.sh")


def _dev_passwords_allowed() -> bool:
    """viewer/viewer and secops/secops exist only for sample-mode UI work, never against real data."""
    return os.environ.get("CHRONOS_ALLOW_DEV_PASSWORDS") == "1" and samples.use_samples()


def _set_session(response: Response, token: str) -> None:
    # Always Secure: browsers still accept it on http://localhost, and nginx is HTTPS-only.
    # CHRONOS_COOKIE_SECURE=0 exists only for clients that refuse Secure cookies on plain HTTP.
    response.set_cookie(key=COOKIE_NAME, value=token, httponly=True,
                        secure=os.environ.get("CHRONOS_COOKIE_SECURE", "1") != "0",
                        samesite="strict", path="/", max_age=TOKEN_EXPIRY_SECONDS)


def create_token(username: str, role: str) -> str:
    now = datetime.now(timezone.utc)
    claims = {
        "sub": username,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int(now.timestamp()) + TOKEN_EXPIRY_SECONDS,
    }
    return jwt.encode(claims, get_jwt_secret(), algorithm="HS256")


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, get_jwt_secret(), algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(401, "invalid or expired session token") from exc


@router.post("/login")
def login(body: LoginRequest, request: Request, response: Response):
    client_ip = _get_client_ip(request)
    rate_key = f"{body.username}:{client_ip}"
    now = time.time()

    attempts = _clean_rate_limit(rate_key, now)
    if len(attempts) >= MAX_FAILED_ATTEMPTS:
        raise HTTPException(429, "too many failed login attempts; account temporarily locked")

    users = _get_configured_users()
    user_entry = users.get(body.username)
    
    # Sample-mode UI development only (see _dev_passwords_allowed).
    if not user_entry and _dev_passwords_allowed():
        dev_passwords = {"viewer": "viewer", "secops": "secops"}
        if body.username in dev_passwords and hmac.compare_digest(body.password, dev_passwords[body.username]):
            role = "security_engineer" if body.username == "secops" else "viewer"
            _set_session(response, create_token(body.username, role))
            _FAILED_LOGINS.pop(rate_key, None)
            return {"sub": body.username, "role": role}

    authenticated = False
    role = "viewer"
    if user_entry:
        stored_hash, user_role = user_entry
        if verify_password(body.password, stored_hash):
            authenticated = True
            role = user_role

    if not authenticated:
        _FAILED_LOGINS.setdefault(rate_key, []).append(now)
        # Constant-time dummy work to resist timing attacks on unknown usernames
        if not user_entry:
            verify_password(body.password, "00000000000000000000000000000000$00000000000000000000000000000000")
        raise HTTPException(401, "invalid credentials")

    _FAILED_LOGINS.pop(rate_key, None)
    _set_session(response, create_token(body.username, role))
    return {"sub": body.username, "role": role}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(key=COOKIE_NAME, path="/")
    return {"status": "ok"}


@router.get("/me")
def me(user: dict = Depends(current_user)):
    return {"sub": user.get("sub", "anonymous"), "role": user.get("role", "viewer")}
