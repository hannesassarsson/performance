"""
Concrete repositories backing the garmin_integration use cases.

Uses raw parameterized SQL via SQLAlchemy's `text()` rather than the ORM
— faster to get correct against the exact schema from Step 2, and this
module's write patterns (idempotent upserts) map directly to SQL anyway.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

from shared.provider_ports import (
    NormalizedActivity,
    NormalizedBodyBatteryReading,
    NormalizedHrvReading,
    NormalizedSleepSession,
    NormalizedStressReading,
    NormalizedTrainingReadiness,
)


@dataclass
class ProviderConnectionRecord:
    id: str
    user_id: str
    encrypted_session: str
    status: str
    last_synced_at: datetime | None


class ProviderConnectionRepo:
    def __init__(self, db: Session):
        self.db = db

    def create_or_update(self, user_id: str, provider_type: str, encrypted_session: str, status) -> str:
        row = self.db.execute(
            text(
                """
                INSERT INTO provider_connections (user_id, provider_type, access_token, status)
                VALUES (:user_id, :provider_type, :access_token, :status)
                ON CONFLICT (user_id, provider_type, external_account_id)
                DO UPDATE SET access_token = EXCLUDED.access_token, status = EXCLUDED.status
                RETURNING id
                """
            ),
            {"user_id": user_id, "provider_type": provider_type, "access_token": encrypted_session, "status": status.value},
        ).fetchone()
        self.db.commit()
        return str(row[0])

    def get(self, connection_id: str) -> ProviderConnectionRecord:
        row = self.db.execute(
            text("SELECT id, user_id, access_token, status, last_synced_at FROM provider_connections WHERE id = :id"),
            {"id": connection_id},
        ).fetchone()
        return ProviderConnectionRecord(
            id=str(row[0]), user_id=str(row[1]), encrypted_session=row[2], status=row[3], last_synced_at=row[4]
        )

    def update_status(self, connection_id: str, status) -> None:
        self.db.execute(
            text("UPDATE provider_connections SET status = :status WHERE id = :id"),
            {"status": status.value, "id": connection_id},
        )
        self.db.commit()

    def update_session(self, connection_id: str, encrypted_session: str) -> None:
        self.db.execute(
            text("UPDATE provider_connections SET access_token = :token WHERE id = :id"),
            {"token": encrypted_session, "id": connection_id},
        )
        self.db.commit()

    def update_last_synced(self, connection_id: str) -> None:
        self.db.execute(
            text("UPDATE provider_connections SET last_synced_at = now() WHERE id = :id"),
            {"id": connection_id},
        )
        self.db.commit()


class ActivitiesRepo:
    def __init__(self, db: Session, user_id: str):
        self.db = db
        self.user_id = user_id

    def upsert(self, connection_id: str, a: NormalizedActivity) -> None:
        self.db.execute(
            text(
                """
                INSERT INTO activities
                    (user_id, provider_connection_id, external_id, activity_type, started_at,
                     duration_seconds, distance_meters, calories, avg_heart_rate, max_heart_rate, elevation_gain_meters)
                VALUES
                    (:user_id, :connection_id, :external_id, :activity_type, :started_at,
                     :duration_seconds, :distance_meters, :calories, :avg_heart_rate, :max_heart_rate, :elevation_gain_meters)
                ON CONFLICT (provider_connection_id, external_id) DO UPDATE SET
                    duration_seconds = EXCLUDED.duration_seconds,
                    distance_meters = EXCLUDED.distance_meters,
                    calories = EXCLUDED.calories,
                    avg_heart_rate = EXCLUDED.avg_heart_rate,
                    max_heart_rate = EXCLUDED.max_heart_rate,
                    elevation_gain_meters = EXCLUDED.elevation_gain_meters
                """
            ),
            {
                "user_id": self.user_id,
                "connection_id": connection_id,
                "external_id": a.external_id,
                "activity_type": a.activity_type,
                "started_at": a.started_at,
                "duration_seconds": a.duration_seconds,
                "distance_meters": a.distance_meters,
                "calories": a.calories,
                "avg_heart_rate": a.avg_heart_rate,
                "max_heart_rate": a.max_heart_rate,
                "elevation_gain_meters": a.elevation_gain_meters,
            },
        )
        self.db.commit()


class SleepRepo:
    def __init__(self, db: Session, user_id: str):
        self.db, self.user_id = db, user_id

    def upsert(self, connection_id: str, s: NormalizedSleepSession) -> None:
        self.db.execute(
            text(
                """
                INSERT INTO sleep_sessions
                    (user_id, provider_connection_id, external_id, sleep_date, started_at, ended_at,
                     total_sleep_seconds, light_sleep_seconds, deep_sleep_seconds, rem_sleep_seconds,
                     awake_seconds, sleep_score)
                VALUES
                    (:user_id, :connection_id, :external_id, :sleep_date, :started_at, :ended_at,
                     :total, :light, :deep, :rem, :awake, :score)
                ON CONFLICT (provider_connection_id, external_id) DO UPDATE SET
                    total_sleep_seconds = EXCLUDED.total_sleep_seconds, sleep_score = EXCLUDED.sleep_score
                """
            ),
            {
                "user_id": self.user_id, "connection_id": connection_id, "external_id": s.external_id,
                "sleep_date": s.sleep_date, "started_at": s.started_at, "ended_at": s.ended_at,
                "total": s.total_sleep_seconds, "light": s.light_sleep_seconds, "deep": s.deep_sleep_seconds,
                "rem": s.rem_sleep_seconds, "awake": s.awake_seconds, "score": s.sleep_score,
            },
        )
        self.db.commit()


class HrvRepo:
    def __init__(self, db: Session, user_id: str):
        self.db, self.user_id = db, user_id

    def upsert(self, connection_id: str, h: NormalizedHrvReading) -> None:
        self.db.execute(
            text(
                """
                INSERT INTO hrv_readings
                    (user_id, provider_connection_id, external_id, reading_date, rmssd_ms,
                     provider_baseline_low, provider_baseline_high, recorded_at)
                VALUES
                    (:user_id, :connection_id, :external_id, :reading_date, :rmssd,
                     :low, :high, :recorded_at)
                ON CONFLICT (provider_connection_id, external_id) DO UPDATE SET rmssd_ms = EXCLUDED.rmssd_ms
                """
            ),
            {
                "user_id": self.user_id, "connection_id": connection_id, "external_id": h.external_id,
                "reading_date": h.reading_date, "rmssd": h.rmssd_ms, "low": h.provider_baseline_low,
                "high": h.provider_baseline_high, "recorded_at": h.recorded_at,
            },
        )
        self.db.commit()


class BodyBatteryRepo:
    def __init__(self, db: Session, user_id: str):
        self.db, self.user_id = db, user_id

    def insert(self, connection_id: str, b: NormalizedBodyBatteryReading) -> None:
        self.db.execute(
            text(
                """
                INSERT INTO body_battery_readings (user_id, provider_connection_id, recorded_at, level, event_type)
                VALUES (:user_id, :connection_id, :recorded_at, :level, :event_type)
                """
            ),
            {"user_id": self.user_id, "connection_id": connection_id, "recorded_at": b.recorded_at,
             "level": b.level, "event_type": b.event_type},
        )
        self.db.commit()


class StressRepo:
    def __init__(self, db: Session, user_id: str):
        self.db, self.user_id = db, user_id

    def insert(self, connection_id: str, s: NormalizedStressReading) -> None:
        self.db.execute(
            text(
                """
                INSERT INTO stress_readings (user_id, provider_connection_id, recorded_at, stress_level)
                VALUES (:user_id, :connection_id, :recorded_at, :stress_level)
                """
            ),
            {"user_id": self.user_id, "connection_id": connection_id, "recorded_at": s.recorded_at,
             "stress_level": s.stress_level},
        )
        self.db.commit()


class ReadinessRepo:
    def __init__(self, db: Session, user_id: str):
        self.db, self.user_id = db, user_id

    def upsert(self, connection_id: str, r: NormalizedTrainingReadiness) -> None:
        self.db.execute(
            text(
                """
                INSERT INTO training_readiness_scores
                    (user_id, provider_connection_id, score_date, score, contributing_factors)
                VALUES (:user_id, :connection_id, :score_date, :score, :factors)
                ON CONFLICT (user_id, score_date, provider_connection_id) DO UPDATE SET score = EXCLUDED.score
                """
            ),
            {"user_id": self.user_id, "connection_id": connection_id, "score_date": r.score_date,
             "score": r.score, "factors": json.dumps(r.contributing_factors) if r.contributing_factors else None},
        )
        self.db.commit()


class SyncLogRepo:
    def __init__(self, db: Session):
        self.db = db

    def record(self, connection_id: str, records_synced: int, status: str) -> None:
        self.db.execute(
            text(
                """
                INSERT INTO provider_sync_logs (provider_connection_id, sync_completed_at, status, records_synced)
                VALUES (:connection_id, now(), :status, :records_synced)
                """
            ),
            {"connection_id": connection_id, "status": status, "records_synced": records_synced},
        )
        self.db.commit()
