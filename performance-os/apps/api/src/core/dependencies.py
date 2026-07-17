from fastapi import Depends
from sqlalchemy.orm import Session

from core.database import get_db
from core.security import get_current_user_id
from modules.garmin_integration.application.connect_garmin_account import ConnectGarminAccountUseCase
from modules.garmin_integration.application.sync_garmin_data import SyncGarminDataUseCase
from modules.garmin_integration.infrastructure.repositories import (
    ActivitiesRepo,
    BodyBatteryRepo,
    HrvRepo,
    ProviderConnectionRepo,
    ReadinessRepo,
    SleepRepo,
    StressRepo,
    SyncLogRepo,
)


def get_connect_use_case(db: Session = Depends(get_db)) -> ConnectGarminAccountUseCase:
    return ConnectGarminAccountUseCase(ProviderConnectionRepo(db))


def get_sync_use_case(
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> SyncGarminDataUseCase:
    return SyncGarminDataUseCase(
        provider_connection_repo=ProviderConnectionRepo(db),
        activities_repo=ActivitiesRepo(db, user_id),
        sleep_repo=SleepRepo(db, user_id),
        hrv_repo=HrvRepo(db, user_id),
        body_battery_repo=BodyBatteryRepo(db, user_id),
        stress_repo=StressRepo(db, user_id),
        readiness_repo=ReadinessRepo(db, user_id),
        sync_log_repo=SyncLogRepo(db),
    )
