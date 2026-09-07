"""FastAPI dependencies, chiefly the one that turns a session token into an Identity.

This is where a request becomes a caller. Every route that touches retrieval depends on it;
a route that does not is a route without access control.
"""

from app.auth import Identity


def current_identity(authorization: str | None = None) -> Identity:
    """Resolve the caller Identity from the Authorization header.

    Raises:
        HTTPException: 401 when the header is missing, malformed, or fails verification.
    """
    raise NotImplementedError


# TODO:
#  1. Implement current_identity() using auth.verify_token, wired as a FastAPI Security dependency.
#  2. Apply it to every route except /auth/login and /health -- and add a test that enumerates
#     app.routes and fails if any other route lacks it. A forgotten dependency is a silent leak.
#  3. Return 401 without revealing whether a user id exists.
#  4. Attach the query_id from observability to the request state here, so every log line for a
#     request correlates.
