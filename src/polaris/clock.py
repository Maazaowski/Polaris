"""One clock for the whole app: UTC.

MySQL's ``NOW()`` (used for ``created_at`` server defaults) runs in the
container's zone, which is UTC. Python timestamps written next to them must be
UTC too, or an invoice shows "Started" hours after "Received" the moment a
process runs outside Docker in a non-UTC zone. The DB columns are naive
``DateTime``, so :func:`utcnow` returns a *naive* UTC datetime to store, and
:func:`utcnow_iso` an explicit ``+00:00`` string for files and logs. The API
serializer and the frontend already treat naive values as UTC.
"""

from __future__ import annotations

from datetime import UTC, datetime


def utcnow() -> datetime:
    """Current UTC time as a naive datetime, for the DB's naive columns."""
    return datetime.now(UTC).replace(tzinfo=None)


def utcnow_iso(timespec: str = "auto") -> str:
    """Current UTC time as an ISO-8601 string with an explicit offset."""
    return datetime.now(UTC).isoformat(timespec=timespec)
