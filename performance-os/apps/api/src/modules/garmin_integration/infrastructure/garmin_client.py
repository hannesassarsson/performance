"""
GarminClient — concrete implementation of ActivityProvider and
HealthMetricsProvider, backed by `garminconnect` (cyberjunky), which as
of mid-2026 is the actively-maintained survivor of Garmin's March 2026
Cloudflare/TLS-fingerprinting change that killed `garth`.

VERIFIED against the library's README/PyPI listing (July 2026):
  - pip install garminconnect curl_cffi ua-generator
  - `from garminconnect import Garmin`
  - Garmin(email, password, prompt_mfa=callback)
  - client.login(tokenstore_path) — tries saved tokens first, falls
    back to a full email/password (+MFA) login if tokens are missing
    or the refresh token has expired
  - DI OAuth tokens auto-refresh indefinitely as long as the refresh
    token is valid; tokens are normally persisted to a JSON file
  - client.get_stats(date), client.get_heart_rates(date) — confirmed
    method names from the README example

NOT VERIFIED — confirm against the library's demo.py before relying on
these in production, method names are inferred from the "Advanced
Health Metrics" / "Daily Health & Activity" category descriptions:
  - get_sleep_data, get_hrv_data, get_body_battery, get_stress_data,
    get_training_readiness, get_activities / get_activities_by_date

This is the ONLY file that should import `garminconnect`. Everything
upstream depends on the Protocols in shared/provider_ports.py — so if
this library also breaks (plausible, given the ongoing arms race), or
if Garmin Health API partnership comes through, only this file changes.
"""

from __future__ import annotations

import queue
import shutil
import tempfile
import threading
from datetime import date, datetime
from pathlib import Path

from garminconnect import Garmin  # pip install garminconnect curl_cffi ua-generator

from modules.garmin_integration.domain.models import GarminSession
from shared.provider_ports import (
    NormalizedActivity,
    NormalizedBodyBatteryReading,
    NormalizedHrvReading,
    NormalizedSleepSession,
    NormalizedStressReading,
    NormalizedTrainingReadiness,
)


class GarminAuthError(Exception):
    """Login failed outright, or a resumed session's refresh token is dead."""


class GarminMfaTimeout(Exception):
    """No MFA code was submitted within the allowed window."""


class GarminClient:
    """
    Wraps garminconnect.Garmin behind the project's Provider Protocols.

    Session persistence: the library's native format is a small JSON
    token file on disk, not an in-memory blob, so unlike the old
    garth-based design this class materializes the encrypted DB blob
    into a temp directory for the duration of a call and cleans it up
    afterwards — it never leaves plaintext tokens on disk longer than
    a single request/job execution.
    """

    def __init__(self, client: Garmin, tokenstore_dir: Path):
        self._client = client
        self._tokenstore_dir = tokenstore_dir

    # -- Resuming an existing session (used by the sync job) ----------------

    @classmethod
    def resume(cls, session: GarminSession) -> "GarminClient":
        tokenstore_dir = Path(tempfile.mkdtemp(prefix="garmin_session_"))
        (tokenstore_dir / "garmin_tokens.json").write_text(session.serialized_blob)

        # Email/password are intentionally blank here — by design we do not
        # persist the user's Garmin password. If the token file's refresh
        # token has died, login() will raise rather than silently fall
        # back to an interactive flow it has no credentials for. That
        # failure is what should mark the connection EXPIRED and prompt
        # the user to reconnect interactively (see ConnectGarminAccountUseCase).
        client = Garmin(email="", password="")
        try:
            client.login(str(tokenstore_dir))
        except Exception as exc:  # noqa: BLE001 — narrow this to the library's real exception type once verified
            shutil.rmtree(tokenstore_dir, ignore_errors=True)
            raise GarminAuthError(f"Failed to resume Garmin session: {exc}") from exc

        return cls(client, tokenstore_dir)

    def dump_session(self) -> GarminSession:
        """Re-read the (possibly auto-refreshed) token file for storage."""
        blob = (self._tokenstore_dir / "garmin_tokens.json").read_text()
        return GarminSession(serialized_blob=blob, obtained_at=datetime.utcnow())

    def close(self) -> None:
        shutil.rmtree(self._tokenstore_dir, ignore_errors=True)

    def is_session_valid(self) -> bool:
        try:
            self._client.get_stats(date.today().isoformat())
            return True
        except Exception:
            return False

    # -- ActivityProvider -----------------------------------------------------

    def fetch_activities(self, since: date) -> list[NormalizedActivity]:
        # TODO verify: real method is likely get_activities(start, limit) or
        # get_activities_by_date(startdate, enddate) — confirm against demo.py.
        raw_activities = self._client.get_activities_by_date(
            since.isoformat(), date.today().isoformat()
        )
        return [self._normalize_activity(a) for a in raw_activities]

    def _normalize_activity(self, raw: dict) -> NormalizedActivity:
        return NormalizedActivity(
            external_id=str(raw["activityId"]),
            activity_type=raw["activityType"]["typeKey"],
            started_at=datetime.fromisoformat(raw["startTimeLocal"]),
            duration_seconds=int(raw["duration"]),
            distance_meters=raw.get("distance"),
            calories=raw.get("calories"),
            avg_heart_rate=raw.get("averageHR"),
            max_heart_rate=raw.get("maxHR"),
            elevation_gain_meters=raw.get("elevationGain"),
        )

    # -- HealthMetricsProvider ------------------------------------------------

    def fetch_sleep(self, since: date) -> list[NormalizedSleepSession]:
        raw = self._client.get_sleep_data(since.isoformat())  # TODO verify method name
        entries = raw if isinstance(raw, list) else [raw]
        return [self._normalize_sleep(s) for s in entries if s]

    def _normalize_sleep(self, raw: dict) -> NormalizedSleepSession:
        return NormalizedSleepSession(
            external_id=str(raw["id"]),
            sleep_date=date.fromisoformat(raw["calendarDate"]),
            started_at=datetime.fromisoformat(raw["sleepStartTimestampLocal"]),
            ended_at=datetime.fromisoformat(raw["sleepEndTimestampLocal"]),
            total_sleep_seconds=raw["sleepTimeSeconds"],
            light_sleep_seconds=raw.get("lightSleepSeconds"),
            deep_sleep_seconds=raw.get("deepSleepSeconds"),
            rem_sleep_seconds=raw.get("remSleepSeconds"),
            awake_seconds=raw.get("awakeSleepSeconds"),
            sleep_score=raw.get("sleepScores", {}).get("overall", {}).get("value"),
        )

    def fetch_hrv(self, since: date) -> list[NormalizedHrvReading]:
        raw = self._client.get_hrv_data(since.isoformat())  # TODO verify method name
        entries = raw if isinstance(raw, list) else [raw]
        return [
            NormalizedHrvReading(
                external_id=f"{r['calendarDate']}-hrv",
                reading_date=date.fromisoformat(r["calendarDate"]),
                rmssd_ms=r["lastNightAvg"],
                recorded_at=datetime.fromisoformat(r["calendarDate"]),
                provider_baseline_low=r.get("baseline", {}).get("lowUpper"),
                provider_baseline_high=r.get("baseline", {}).get("balancedUpper"),
            )
            for r in entries if r
        ]

    def fetch_body_battery(self, since: date) -> list[NormalizedBodyBatteryReading]:
        raw = self._client.get_body_battery(since.isoformat())  # TODO verify method name
        return [
            NormalizedBodyBatteryReading(recorded_at=datetime.fromisoformat(r["timestamp"]), level=r["level"])
            for r in raw
        ]

    def fetch_stress(self, since: date) -> list[NormalizedStressReading]:
        raw = self._client.get_stress_data(since.isoformat())  # TODO verify method name
        entries = raw if isinstance(raw, list) else [raw]
        return [
            NormalizedStressReading(
                recorded_at=datetime.fromisoformat(r["calendarDate"]),
                stress_level=r.get("avgStressLevel"),
            )
            for r in entries if r
        ]

    def fetch_training_readiness(self, since: date) -> list[NormalizedTrainingReadiness]:
        raw = self._client.get_training_readiness(since.isoformat())  # TODO verify method name
        entries = raw if isinstance(raw, list) else [raw]
        return [
            NormalizedTrainingReadiness(
                score_date=date.fromisoformat(r["calendarDate"]),
                score=r["score"],
                contributing_factors=r.get("feedbackPhrase"),
            )
            for r in entries if r
        ]


# ---------------------------------------------------------------------------
# Interactive login with MFA, adapted for a request/response web backend.
#
# The library's `prompt_mfa` is a blocking callable (like `input()`) —
# it assumes a terminal session. In a web API, the login() call happens
# on a background thread; prompt_mfa blocks on a queue.get() that a
# SEPARATE HTTP request (the user submitting their MFA code) populates.
#
# LIMITATION: the pending-login registry below is an in-process dict.
# It only works correctly with a single backend instance. On Railway,
# if this service ever scales to multiple replicas, the connect flow
# must be pinned to one instance (sticky session) or moved to a
# Redis-backed coordination mechanism. Flagging this now so it isn't
# a surprise during Step 11 (deployment).
# ---------------------------------------------------------------------------

class PendingGarminLogin:
    def __init__(self):
        self.mfa_requested = threading.Event()
        self.mfa_code_queue: queue.Queue[str] = queue.Queue()
        self.result: GarminSession | None = None
        self.error: Exception | None = None
        self.done = threading.Event()


_pending_logins: dict[str, PendingGarminLogin] = {}


def start_interactive_login(attempt_id: str, email: str, password: str) -> None:
    pending = PendingGarminLogin()
    _pending_logins[attempt_id] = pending

    def _prompt_mfa() -> str:
        pending.mfa_requested.set()
        try:
            return pending.mfa_code_queue.get(timeout=300)  # 5 min for the user to submit a code
        except queue.Empty as exc:
            raise GarminMfaTimeout("No MFA code submitted in time") from exc

    def _run():
        tokenstore_dir = Path(tempfile.mkdtemp(prefix="garmin_login_"))
        try:
            client = Garmin(email, password, prompt_mfa=_prompt_mfa)
            client.login(str(tokenstore_dir))
            blob = (tokenstore_dir / "garmin_tokens.json").read_text()
            pending.result = GarminSession(serialized_blob=blob, obtained_at=datetime.utcnow())
        except Exception as exc:  # noqa: BLE001 — narrow once the library's real exceptions are confirmed
            pending.error = exc
        finally:
            shutil.rmtree(tokenstore_dir, ignore_errors=True)
            pending.done.set()

    threading.Thread(target=_run, daemon=True).start()


def poll_login_status(attempt_id: str, timeout_seconds: float = 8.0) -> dict:
    """Called by the API layer right after starting login, and again after
    the user submits an MFA code. Short-polls so the HTTP request doesn't
    hang indefinitely."""
    pending = _pending_logins.get(attempt_id)
    if pending is None:
        return {"status": "not_found"}

    if pending.done.wait(timeout=timeout_seconds):
        del _pending_logins[attempt_id]
        if pending.error is not None:
            return {"status": "error", "message": str(pending.error)}
        return {"status": "success", "session": pending.result}

    if pending.mfa_requested.is_set():
        return {"status": "mfa_required"}

    return {"status": "pending"}


def submit_mfa_code(attempt_id: str, code: str) -> None:
    pending = _pending_logins.get(attempt_id)
    if pending is None:
        raise ValueError("Unknown or expired login attempt")
    pending.mfa_code_queue.put(code)
