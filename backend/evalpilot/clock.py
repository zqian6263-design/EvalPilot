"""Shared helpers for timestamps and identifiers.

Contract conventions (``CLAUDE.md``): UTC ISO-8601 timestamps, UUID string IDs.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime


def utc_now() -> datetime:
    return datetime.now(UTC)


def to_iso(value: datetime) -> str:
    """Serialize to UTC ISO-8601 with a trailing ``Z``."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def from_iso(raw: str) -> datetime:
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


def new_id() -> str:
    return str(uuid.uuid4())
