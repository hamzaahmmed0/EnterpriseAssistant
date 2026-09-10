"""Demo authentication and the Identity that authorization is keyed to.

Authentication here is deliberately minimal (ADR-006): 3-4 demo users spanning department and
access-level boundaries, and HMAC-signed compact session tokens. Authorization -- the part this
project actually studies -- is real, and everything downstream depends on the Identity produced
here being trustworthy.

This module has no FastAPI dependency: the MCP server needs the same Identity type without
importing the web layer.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.config import get_settings

TOKEN_VERSION = "v1"


@dataclass(frozen=True)
class Identity:
    """An authenticated caller, and the only input the access filter is allowed to key on.

    Immutable on purpose: nothing downstream may widen a caller scope in flight.
    """

    user_id: str
    name: str
    department: str
    access_level: str
    role: str


@dataclass(frozen=True)
class DemoUser:
    """A row from the demo users file, before authentication."""

    user_id: str
    name: str
    department: str
    access_level: str
    role: str
    password_sha256: str

    def to_identity(self) -> Identity:
        """Project this user into the Identity used for authorization."""
        return Identity(
            user_id=self.user_id,
            name=self.name,
            department=self.department,
            access_level=self.access_level,
            role=self.role,
        )


class AuthenticationError(Exception):
    """Raised when a caller cannot be authenticated."""


def _hash_password(password: str) -> str:
    """Hash a demo password. Demo-grade by design (ADR-006), not a credential store."""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def load_demo_users(path: str | None = None) -> dict[str, DemoUser]:
    """Load the demo user table keyed by user_id.

    Args:
        path: Path to the demo users JSON file. Defaults to settings.demo_users_path.

    Returns:
        Mapping of user_id to DemoUser.

    Raises:
        AuthenticationError: If the file is missing, malformed, or any user lacks a department
            or access level. A user that cannot be constrained must never exist.
    """
    resolved = Path(path or get_settings().demo_users_path)
    if not resolved.exists():
        raise AuthenticationError(f"demo users file not found: {resolved}")

    try:
        raw = json.loads(resolved.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:  # pragma: no cover - config error path
        raise AuthenticationError(f"demo users file is not valid JSON: {exc}") from exc

    users: dict[str, DemoUser] = {}
    for entry in raw:
        missing = [
            field
            for field in (
                "user_id",
                "name",
                "department",
                "access_level",
                "role",
                "password_sha256",
            )
            if not entry.get(field)
        ]
        if missing:
            raise AuthenticationError(
                f"demo user {entry.get('user_id', '<unknown>')} is missing: {', '.join(missing)}"
            )
        user = DemoUser(**{k: entry[k] for k in DemoUser.__dataclass_fields__})
        users[user.user_id] = user

    if not users:
        raise AuthenticationError("demo users file contains no users")
    return users


@lru_cache
def _cached_users() -> dict[str, DemoUser]:
    """Process-wide demo user table."""
    return load_demo_users()


def reset_user_cache() -> None:
    """Clear the demo user cache. Tests only."""
    _cached_users.cache_clear()


def authenticate(user_id: str, password: str) -> Identity:
    """Verify demo credentials and return the caller Identity.

    Raises:
        AuthenticationError: If the user is unknown or the password does not match. The message
            is identical in both cases so callers cannot enumerate user ids.
    """
    users = _cached_users()
    user = users.get(user_id)
    expected = user.password_sha256 if user else "0" * 64
    supplied = _hash_password(password)
    # Compare in both branches so a missing user and a wrong password cost the same.
    ok = hmac.compare_digest(expected, supplied) and user is not None
    if not ok or user is None:
        raise AuthenticationError("invalid credentials")
    return user.to_identity()


def _b64encode(data: bytes) -> str:
    """URL-safe base64 without padding."""
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64decode(data: str) -> bytes:
    """Inverse of _b64encode."""
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _sign(payload_b64: str, secret: str) -> str:
    """HMAC-SHA256 over the encoded payload."""
    digest = hmac.new(secret.encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256).digest()
    return _b64encode(digest)


def issue_token(identity: Identity, *, now: float | None = None) -> str:
    """Issue a session token encoding the caller Identity.

    Format: ``<base64url(payload_json)>.<base64url(hmac_sha256)>`` (ADR-006). No JWT library:
    the payload is five fields plus an expiry, and this is short enough to audit by eye.
    """
    settings = get_settings()
    issued = int(now if now is not None else time.time())
    payload = {
        "v": TOKEN_VERSION,
        "sub": identity.user_id,
        "name": identity.name,
        "dept": identity.department,
        "lvl": identity.access_level,
        "role": identity.role,
        "iat": issued,
        "exp": issued + settings.auth_token_ttl_minutes * 60,
    }
    payload_b64 = _b64encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    return f"{payload_b64}.{_sign(payload_b64, settings.auth_secret)}"


def verify_token(token: str, *, now: float | None = None) -> Identity:
    """Decode and validate a session token back into an Identity.

    Raises:
        AuthenticationError: If the token is malformed, expired, or fails signature verification.
    """
    settings = get_settings()
    if not token or token.count(".") != 1:
        raise AuthenticationError("malformed token")

    payload_b64, signature = token.split(".", 1)
    if not hmac.compare_digest(_sign(payload_b64, settings.auth_secret), signature):
        raise AuthenticationError("invalid token signature")

    try:
        payload = json.loads(_b64decode(payload_b64))
    except (ValueError, json.JSONDecodeError) as exc:
        raise AuthenticationError("malformed token payload") from exc

    if payload.get("v") != TOKEN_VERSION:
        raise AuthenticationError("unsupported token version")

    current = now if now is not None else time.time()
    if float(payload.get("exp", 0)) <= current:
        raise AuthenticationError("token expired")

    required = ("sub", "name", "dept", "lvl", "role")
    if any(not payload.get(field) for field in required):
        raise AuthenticationError("token missing identity fields")

    return Identity(
        user_id=payload["sub"],
        name=payload["name"],
        department=payload["dept"],
        access_level=payload["lvl"],
        role=payload["role"],
    )
