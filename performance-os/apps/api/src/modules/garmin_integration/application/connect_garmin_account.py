"""
ConnectGarminAccountUseCase — orchestrates the interactive login.

Three-step HTTP dance (matches routes.py):
  1. POST /connect            -> start login, poll briefly, may return mfa_required
  2. POST /connect/{id}/mfa   -> submit the code
  3. GET  /connect/{id}/status -> poll until success/error (frontend polls this
     after step 1 or step 2 if the first poll didn't resolve immediately)

Password is never persisted — it's only held in the closure of the
background login thread for the duration of that one login attempt.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from modules.garmin_integration.domain.models import ConnectionStatus
from modules.garmin_integration.infrastructure.garmin_client import (
    poll_login_status,
    start_interactive_login,
    submit_mfa_code,
)
from modules.garmin_integration.infrastructure.session_encryption import SessionEncryptor


@dataclass
class ConnectGarminStepResult:
    attempt_id: str
    status: str  # 'pending' | 'mfa_required' | 'success' | 'error'
    provider_connection_id: str | None = None
    error_message: str | None = None


class ConnectGarminAccountUseCase:
    def __init__(self, provider_connection_repo, session_encryptor: SessionEncryptor | None = None):
        self._repo = provider_connection_repo
        self._encryptor = session_encryptor or SessionEncryptor()

    def start(self, user_id: str, email: str, password: str) -> ConnectGarminStepResult:
        attempt_id = str(uuid.uuid4())
        start_interactive_login(attempt_id, email, password)
        status = poll_login_status(attempt_id)
        return self._handle_status(user_id, attempt_id, status)

    def submit_mfa(self, user_id: str, attempt_id: str, code: str) -> ConnectGarminStepResult:
        submit_mfa_code(attempt_id, code)
        status = poll_login_status(attempt_id)
        return self._handle_status(user_id, attempt_id, status)

    def check_status(self, user_id: str, attempt_id: str) -> ConnectGarminStepResult:
        status = poll_login_status(attempt_id)
        return self._handle_status(user_id, attempt_id, status)

    def _handle_status(self, user_id: str, attempt_id: str, status: dict) -> ConnectGarminStepResult:
        if status["status"] == "success":
            encrypted_blob = self._encryptor.encrypt(status["session"].serialized_blob)
            connection_id = self._repo.create_or_update(
                user_id=user_id,
                provider_type="garmin",
                encrypted_session=encrypted_blob,
                status=ConnectionStatus.ACTIVE,
            )
            return ConnectGarminStepResult(attempt_id=attempt_id, status="success", provider_connection_id=connection_id)

        if status["status"] == "error":
            return ConnectGarminStepResult(attempt_id=attempt_id, status="error", error_message=status.get("message"))

        return ConnectGarminStepResult(attempt_id=attempt_id, status=status["status"])
