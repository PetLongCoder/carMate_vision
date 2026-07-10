from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.v1.auth import ok, require_admin
from app.core.database import get_db
from app.models.db_models import AlertRecord, HistoryRecord, PoliceGestureLog, RecognitionRecord, User
from app.utils.logger import logger

router = APIRouter()


def _count_history(db: Session, record_type: str, *, today_only: bool = False) -> int:
    query = db.query(func.count(HistoryRecord.id)).filter(HistoryRecord.type == record_type)
    if today_only:
        query = query.filter(func.date(HistoryRecord.created_at) == date.today())
    return query.scalar() or 0


@router.get("/stats/dashboard")
def get_dashboard_stats(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    logger.info("查询仪表盘统计")

    total_plates = (
        db.query(func.count(RecognitionRecord.id))
        .filter(RecognitionRecord.type == "plate", RecognitionRecord.success.is_(True))
        .scalar()
        or 0
    )
    total_gestures_records = (
        db.query(func.count(RecognitionRecord.id))
        .filter(
            RecognitionRecord.type.in_(["police_gesture", "driver_gesture"]),
            RecognitionRecord.success.is_(True),
        )
        .scalar()
        or 0
    )
    total_police_logs = db.query(func.count(PoliceGestureLog.id)).scalar() or 0
    success_police_logs = (
        db.query(func.count(PoliceGestureLog.id))
        .filter(PoliceGestureLog.success.is_(True))
        .scalar()
        or 0
    )
    today_gestures = (
        db.query(func.count(PoliceGestureLog.id))
        .filter(func.date(PoliceGestureLog.created_at) == date.today())
        .scalar()
        or 0
    )
    total_alerts = db.query(func.count(AlertRecord.id)).scalar() or 0
    unread_alerts = (
        db.query(func.count(AlertRecord.id)).filter(AlertRecord.acknowledged.is_(False)).scalar() or 0
    )

    police_gesture_records = _count_history(db, "police_gesture")
    driver_gesture_records = _count_history(db, "driver_gesture")
    today_police_gesture_records = _count_history(db, "police_gesture", today_only=True)
    today_driver_gesture_records = _count_history(db, "driver_gesture", today_only=True)

    return ok(
        {
            "totalPlates": total_plates,
            "totalGestures": total_gestures_records + total_police_logs,
            "todayGestures": today_gestures + today_police_gesture_records + today_driver_gesture_records,
            "successGestures": success_police_logs,
            "totalAlerts": total_alerts,
            "unreadAlerts": unread_alerts,
            "gestureBreakdown": {
                "policeGestureRecords": police_gesture_records,
                "driverGestureRecords": driver_gesture_records,
                "policeGestureLogs": total_police_logs,
                "policeGestureLogsSuccess": success_police_logs,
            },
            "todayGestureBreakdown": {
                "policeGestureRecords": today_police_gesture_records,
                "driverGestureRecords": today_driver_gesture_records,
                "policeGestureLogs": today_gestures,
            },
        }
    )
