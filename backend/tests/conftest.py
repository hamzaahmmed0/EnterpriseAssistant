"""Shared pytest fixtures.

Fixtures here must never construct an Identity with wider access than a real demo user has, and
must never provide an unfiltered vector-store client.
"""

from collections.abc import Iterator

import pytest

from app.auth import Identity


@pytest.fixture
def hr_identity() -> Identity:
    """A demo HR user."""
    raise NotImplementedError


@pytest.fixture
def engineering_identity() -> Identity:
    """A demo Engineering user with no Finance or HR access."""
    raise NotImplementedError


@pytest.fixture
def fake_vector_store() -> Iterator[object]:
    """A stub Qdrant client that records the filter passed to every search call."""
    raise NotImplementedError


# TODO:
#  1. Implement the identity fixtures from the same demo users file the app loads, so tests and
#     the running system cannot disagree about who can see what.
#  2. Implement fake_vector_store() to capture search kwargs; the access-filter regression test
#     asserts against what it captured.
#  3. Add a settings fixture that supplies test config without reading the developer .env.
#  4. Add a corpus fixture with a handful of chunks spanning two departments and two access
#     levels, used by the filter tests.
