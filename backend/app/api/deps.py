"""FastAPI dependencies, chiefly the one that turns a session token into an Identity.

This is where a request becomes a caller. Every route that touches retrieval depends on it; a
route that does not is a route without access control. ``test_route_auth.py`` enumerates
``app.routes`` and fails if a new route forgets it.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth import AuthenticationError, Identity, verify_token

#: auto_error=False so a missing header produces our own 401 rather than FastAPI's 403.
bearer_scheme = HTTPBearer(auto_error=False)

#: Routes that legitimately have no caller. Kept here so the auth-coverage test reads one list.
UNAUTHENTICATED_PATHS = frozenset({"/auth/login", "/health", "/docs", "/openapi.json", "/redoc"})


def current_identity(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> Identity:
    """Resolve the caller Identity from the Authorization header.

    Raises:
        HTTPException: 401 when the header is missing, malformed, expired, or fails signature
            verification. The message is identical in every case, so a caller cannot use it to
            learn whether a user id exists.
    """
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        identity = verify_token(credentials.credentials)
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    # Available to the logging middleware without re-parsing the token.
    request.state.identity = identity
    return identity


IdentityDep = Depends(current_identity)
