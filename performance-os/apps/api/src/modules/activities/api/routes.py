from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from core.database import get_db
from core.security import get_current_user_id

router = APIRouter(prefix="/api/v1/activities", tags=["activities"])


@router.get("")
def list_activities(db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    rows = db.execute(
        text(
            """
            SELECT id, activity_type, started_at, duration_seconds, distance_meters, avg_heart_rate
            FROM activities
            WHERE user_id = :user_id
            ORDER BY started_at DESC
            LIMIT 50
            """
        ),
        {"user_id": user_id},
    ).fetchall()
    return [
        {
            "id": str(r[0]),
            "activity_type": r[1],
            "started_at": r[2].isoformat() if r[2] else None,
            "duration_seconds": r[3],
            "distance_meters": float(r[4]) if r[4] is not None else None,
            "avg_heart_rate": r[5],
        }
        for r in rows
    ]
