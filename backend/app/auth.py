"""Demo authentication and the Identity that authorization is keyed to.

Authentication here is deliberately minimal (ADR-006): 3-4 hardcoded users spanning department
and access-level boundaries. Authorization -- the part this project actually studies -- is real,
and everything downstream depends on the Identity produced here being trustworthy.

This module has no FastAPI dependency: the MCP server needs the same Identity type without
importing the web layer.
"""

from dataclasses import dataclass


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
    password: str


def load_demo_users(path: str) -> dict[str, DemoUser]:
    """Load the demo user table keyed by user_id.

    Args:
        path: Path to the demo users JSON file (settings.demo_users_path).

    Returns:
        Mapping of user_id to DemoUser.
    """
    raise NotImplementedError


def authenticate(user_id: str, password: str) -> Identity:
    """Verify demo credentials and return the caller Identity.

    Raises:
        AuthenticationError: If the user is unknown or the password does not match.
    """
    raise NotImplementedError


def issue_token(identity: Identity) -> str:
    """Issue a session token encoding the caller Identity."""
    raise NotImplementedError


def verify_token(token: str) -> Identity:
    """Decode and validate a session token back into an Identity.

    Raises:
        AuthenticationError: If the token is malformed, expired, or fails verification.
    """
    raise NotImplementedError


class AuthenticationError(Exception):
    """Raised when a caller cannot be authenticated."""


# TODO:
#  1. Resolve ADR-006 open question 3 (JWT vs. opaque token) before writing issue/verify.
#  2. Define the demo users JSON schema and author the file; keep it out of data/ so it can be
#     committed -- it is fixture, not corpus.
#  3. Implement load_demo_users() with a hard failure on a missing department or access_level.
#  4. Implement authenticate(); constant-time password comparison even for demo credentials.
#  5. Implement issue_token()/verify_token() honouring auth_token_ttl_minutes.
#  6. Add a test asserting Identity is frozen and cannot be mutated after construction.
#  7. Author the demo users so that at least one document in the corpus is visible to exactly
#     one of them -- the live access-control demo depends on that asymmetry existing.
