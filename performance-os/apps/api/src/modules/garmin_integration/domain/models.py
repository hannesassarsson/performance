"""
Domain layer for garmin_integration.

Deliberately has zero dependency on garth, FastAPI, or SQLAlchemy — these
are the plain business concepts. Keeping this framework-free means the
sync orchestration logic (in application/) can be unit tested without a
real Garmin session or a database.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class ConnectionStatus(str, Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"
    ERROR = "error"


@dataclass(frozen=True)
class GarminSession:
    """Represents a resumable garth session.

    `serialized_blob` is garth's own session dump (JSON) — treated as an
    opaque string by everything except infrastructure/garmin_client.py.
    It is encrypted before it's ever handed to a repository for storage.
    """
    serialized_blob: str
    obtained_at: datetime


@dataclass
class SyncResult:
    records_synced: int
    status: str  # 'success' | 'partial' | 'failed'
    error_message: str | None = None
