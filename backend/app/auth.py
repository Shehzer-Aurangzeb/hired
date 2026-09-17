"""
One password guards the instance, no accounts. Only an scrypt hash is stored,
in the environment rather than the database.
"""

import base64
import hmac
import math
import secrets
import time
from dataclasses import dataclass
from hashlib import scrypt

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .settings import get_settings

# Interactive-login parameters. 128 * N * r is 16 MB, inside OpenSSL's cap.
N, R, P = 2**14, 8, 1

MAX_ATTEMPTS = 5
BASE_LOCKOUT = 30
MAX_LOCKOUT = 15 * 60

router = APIRouter(prefix="/api/auth", tags=["auth"])


# ---------- hashing ----------


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    key = scrypt(password.encode(), salt=salt, n=N, r=R, p=P)
    return "$".join(["scrypt", str(N), str(R), str(P), _b64(salt), _b64(key)])


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, key = stored.split("$")
        if scheme != "scrypt":
            return False
        candidate = scrypt(
            password.encode(), salt=_unb64(salt), n=int(n), r=int(r), p=int(p)
        )
    except (ValueError, TypeError):
        # A malformed hash is a broken lock, and a broken lock reads as locked.
        return False
    # Constant time, so a wrong password cannot be narrowed down by timing it.
    return hmac.compare_digest(candidate, _unb64(key))


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


# ---------- rate limiting ----------


@dataclass
class Gate:
    failures: int = 0
    lockouts: int = 0
    locked_until: float = 0.0


# ponytail: in-process, so it needs Redis the day there is a second worker.
# Global rather than per-IP, because per-IP only means rotating addresses. The
# cost is that a stranger can lock the owner out for a while.
_gate = Gate()


def _locked_for() -> int:
    return max(0, math.ceil(_gate.locked_until - time.monotonic()))


def _record_failure() -> None:
    _gate.failures += 1
    if _gate.failures < MAX_ATTEMPTS:
        return
    # Each lockout doubles, so a typo costs 30s and a guessing run costs more.
    _gate.lockouts += 1
    _gate.failures = 0
    wait = min(BASE_LOCKOUT * 2 ** (_gate.lockouts - 1), MAX_LOCKOUT)
    _gate.locked_until = time.monotonic() + wait


def _too_many(wait: int) -> JSONResponse:
    """Flat body, not HTTPException: the client needs retry_after beside detail."""
    return JSONResponse(
        {
            "detail": "Too many attempts. Wait a moment before trying again.",
            "retry_after": wait,
        },
        status_code=429,
        headers={"Retry-After": str(wait)},
    )


def reset_gate() -> None:
    _gate.failures = _gate.lockouts = 0
    _gate.locked_until = 0.0


# ---------- routes ----------


class LoginBody(BaseModel):
    password: str


def require_session(request: Request) -> None:
    """Attached to the whole API router, so a new route cannot forget it."""
    if not request.session.get("auth"):
        raise HTTPException(401, "Not signed in.")


@router.get("/session")
def session_state(request: Request) -> dict[str, bool]:
    return {"authenticated": bool(request.session.get("auth"))}


@router.post("/login")
def login(body: LoginBody, request: Request):
    wait = _locked_for()
    if wait:
        return _too_many(wait)

    stored = get_settings().password_hash
    if not stored:
        # Not set up. Letting anyone in is the worst reading of "no password".
        raise HTTPException(503, "No password is configured on this instance.")

    if not verify_password(body.password, stored):
        _record_failure()
        wait = _locked_for()
        if wait:
            return _too_many(wait)
        raise HTTPException(401, "That password is not right.")

    reset_gate()
    # Clear first, so a cookie handed out earlier cannot be promoted to signed in.
    request.session.clear()
    request.session["auth"] = True
    return {"authenticated": True}


@router.post("/logout")
def logout(request: Request) -> dict[str, bool]:
    request.session.clear()
    return {"authenticated": False}
