"""
Shared Provider interfaces.

Design decision: split into two narrow Protocols instead of one large
interface. Garmin implements both. A future Strava/Polar provider may
only implement ActivityProvider — it should never be forced to stub out
fetch_hrv() etc. with NotImplementedError.

Application-layer use cases depend on these Protocols, never on a
concrete provider class. This is what makes providers swappable without
touching the Analytics Engine or anything above the Normalization Layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol


# ---------------------------------------------------------------------------
# Normalized DTOs — the shape every provider must translate its raw payload
# into, before anything touches the database. This IS the Normalization
# Layer contract.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class NormalizedActivity:
    external_id: str
    activity_type: str
    started_at: datetime
    duration_seconds: int
    distance_meters: float | None = None
    calories: int | None = None
    avg_heart_rate: int | None = None
    max_heart_rate: int | None = None
    elevation_gain_meters: float | None = None
    raw_laps: list[dict] | None = None          # mapped to activity_laps by the use case
    raw_hr_samples: list[tuple[datetime, int]] | None = None  # mapped to heart_rate_samples


@dataclass(frozen=True)
class NormalizedSleepSession:
    external_id: str
    sleep_date: date
    started_at: datetime
    ended_at: datetime
    total_sleep_seconds: int
    light_sleep_seconds: int | None
    deep_sleep_seconds: int | None
    rem_sleep_seconds: int | None
    awake_seconds: int | None
    sleep_score: int | None


@dataclass(frozen=True)
class NormalizedHrvReading:
    external_id: str
    reading_date: date
    rmssd_ms: float
    recorded_at: datetime
    provider_baseline_low: float | None = None
    provider_baseline_high: float | None = None


@dataclass(frozen=True)
class NormalizedBodyBatteryReading:
    recorded_at: datetime
    level: int
    event_type: str | None = None


@dataclass(frozen=True)
class NormalizedStressReading:
    recorded_at: datetime
    stress_level: int | None


@dataclass(frozen=True)
class NormalizedTrainingReadiness:
    score_date: date
    score: int
    contributing_factors: dict | None = None


# ---------------------------------------------------------------------------
# Provider protocols
# ---------------------------------------------------------------------------

class ActivityProvider(Protocol):
    """Any provider that can supply workout/activity data."""

    def fetch_activities(self, since: date) -> list[NormalizedActivity]:
        ...


class HealthMetricsProvider(Protocol):
    """Any provider that can supply all-day health/wellness data.

    Garmin is currently the only implementer of this — Strava has no
    equivalent data. That's fine: application code that needs health
    metrics depends on this Protocol specifically, not on ActivityProvider.
    """

    def fetch_sleep(self, since: date) -> list[NormalizedSleepSession]:
        ...

    def fetch_hrv(self, since: date) -> list[NormalizedHrvReading]:
        ...

    def fetch_body_battery(self, since: date) -> list[NormalizedBodyBatteryReading]:
        ...

    def fetch_stress(self, since: date) -> list[NormalizedStressReading]:
        ...

    def fetch_training_readiness(self, since: date) -> list[NormalizedTrainingReadiness]:
        ...
