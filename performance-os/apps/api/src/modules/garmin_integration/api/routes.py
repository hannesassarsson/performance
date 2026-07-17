"""
Thin FastAPI layer — validation and routing only. Real logic lives in
application/ use cases, injected via Depends().

Connect flow is three endpoints because MFA can't be resolved within a
single request/response cycle (see garmin_client.py docstring on the
thread+queue pattern this is built on).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from core.dependencies import get_connect_use_case, get_sync_use_case
from core.security import get_current_user_id
from modules.garmin_integration.application.connect_garmin_account import (
    ConnectGarminAccountUseCase,
)
from modules.garmin_integration.application.sync_garmin_data import SyncGarminDataUseCase

router = APIRouter(prefix="/api/v1/providers/garmin", tags=["garmin"])


class ConnectGarminRequest(BaseModel):
    email: str
    password: str


class SubmitMfaRequest(BaseModel):
    code: str


class ConnectGarminResponse(BaseModel):
    attempt_id: str
    status: str  # 'pending' | 'mfa_required' | 'success' | 'error'
    provider_connection_id: str | None = None
    error_message: str | None = None


def _to_response(result) -> ConnectGarminResponse:
    return ConnectGarminResponse(
        attempt_id=result.attempt_id,
        status=result.status,
        provider_connection_id=result.provider_connection_id,
        error_message=result.error_message,
    )


@router.post("/connect", response_model=ConnectGarminResponse)
def connect_garmin(
    payload: ConnectGarminRequest,
    current_user_id: str = Depends(get_current_user_id),
    use_case: ConnectGarminAccountUseCase = Depends(get_connect_use_case),
):
    result = use_case.start(current_user_id, payload.email, payload.password)
    return _to_response(result)


@router.post("/connect/{attempt_id}/mfa", response_model=ConnectGarminResponse)
def submit_garmin_mfa(
    attempt_id: str,
    payload: SubmitMfaRequest,
    current_user_id: str = Depends(get_current_user_id),
    use_case: ConnectGarminAccountUseCase = Depends(get_connect_use_case),
):
    result = use_case.submit_mfa(current_user_id, attempt_id, payload.code)
    return _to_response(result)


@router.get("/connect/{attempt_id}/status", response_model=ConnectGarminResponse)
def garmin_connect_status(
    attempt_id: str,
    current_user_id: str = Depends(get_current_user_id),
    use_case: ConnectGarminAccountUseCase = Depends(get_connect_use_case),
):
    # Frontend polls this (e.g. every 2s) whenever start/submit_mfa
    # returned 'pending' instead of a terminal state.
    result = use_case.check_status(current_user_id, attempt_id)
    return _to_response(result)


@router.post("/sync/{provider_connection_id}")
def trigger_sync(
    provider_connection_id: str,
    use_case: SyncGarminDataUseCase = Depends(get_sync_use_case),
):
    # Production: enqueue a background job rather than running inline —
    # kept synchronous here for clarity; wired up properly at Step 11.
    result = use_case.execute(provider_connection_id)
    return {"status": result.status, "records_synced": result.records_synced}
