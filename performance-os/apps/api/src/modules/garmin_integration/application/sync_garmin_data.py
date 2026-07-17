"""
SyncGarminDataUseCase — the recurring background job.

Depends only on the Provider Protocols (ActivityProvider,
HealthMetricsProvider), never on GarminClient directly, so this same
use case class works unchanged for any future provider that implements
those Protocols.

Idempotency contract: every repo.upsert_* call relies on the
UNIQUE(provider_connection_id, external_id) constraints already defined
in the schema (Step 2). Re-running this use case for the same date
range must be safe and side-effect-free beyond updating existing rows.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from modules.garmin_integration.domain.models import ConnectionStatus, GarminSession, SyncResult
from modules.garmin_integration.infrastructure.garmin_client import GarminAuthError, GarminClient
from modules.garmin_integration.infrastructure.session_encryption import SessionEncryptor
from shared.provider_ports import ActivityProvider, HealthMetricsProvider


@dataclass
class SyncGarminDataUseCase:
    provider_connection_repo: object   # holds encrypted session, status, last_synced_at
    activities_repo: object
    sleep_repo: object
    hrv_repo: object
    body_battery_repo: object
    stress_repo: object
    readiness_repo: object
    sync_log_repo: object
    session_encryptor: SessionEncryptor | None = None

    def execute(self, provider_connection_id: str) -> SyncResult:
        encryptor = self.session_encryptor or SessionEncryptor()
        connection = self.provider_connection_repo.get(provider_connection_id)

        decrypted_blob = encryptor.decrypt(connection.encrypted_session)
        session = GarminSession(serialized_blob=decrypted_blob, obtained_at=connection.last_synced_at)

        try:
            client = GarminClient.resume(session)
        except GarminAuthError:
            # Refresh token is dead — no password on hand to fall back to.
            # User must go through the interactive connect flow again.
            self.provider_connection_repo.update_status(provider_connection_id, ConnectionStatus.EXPIRED)
            return SyncResult(records_synced=0, status="failed", error_message="Session expired — user must reconnect")

        since = connection.last_synced_at.date() if connection.last_synced_at else date(2020, 1, 1)
        records_synced = 0

        try:
            records_synced += self._sync_activities(client, provider_connection_id, since)
            records_synced += self._sync_health_metrics(client, provider_connection_id, since)

            # Tokens may have auto-refreshed mid-sync — persist the
            # (possibly updated) session back, encrypted, every time.
            refreshed_session = client.dump_session()
            self.provider_connection_repo.update_session(
                provider_connection_id, encryptor.encrypt(refreshed_session.serialized_blob)
            )
        except GarminAuthError as exc:
            self.provider_connection_repo.update_status(provider_connection_id, ConnectionStatus.ERROR)
            return SyncResult(records_synced=records_synced, status="partial", error_message=str(exc))
        finally:
            client.close()

        self.provider_connection_repo.update_last_synced(provider_connection_id)
        self.sync_log_repo.record(provider_connection_id, records_synced, status="success")
        return SyncResult(records_synced=records_synced, status="success")

    def _sync_activities(self, provider: ActivityProvider, connection_id: str, since: date) -> int:
        activities = provider.fetch_activities(since)
        for activity in activities:
            self.activities_repo.upsert(connection_id, activity)
        return len(activities)

    def _sync_health_metrics(self, provider: HealthMetricsProvider, connection_id: str, since: date) -> int:
        count = 0
        for sleep in provider.fetch_sleep(since):
            self.sleep_repo.upsert(connection_id, sleep)
            count += 1
        for hrv in provider.fetch_hrv(since):
            self.hrv_repo.upsert(connection_id, hrv)
            count += 1
        for bb in provider.fetch_body_battery(since):
            self.body_battery_repo.insert(connection_id, bb)  # append-only, no external_id to dedupe on
            count += 1
        for stress in provider.fetch_stress(since):
            self.stress_repo.insert(connection_id, stress)
            count += 1
        for readiness in provider.fetch_training_readiness(since):
            self.readiness_repo.upsert(connection_id, readiness)
            count += 1
        return count
