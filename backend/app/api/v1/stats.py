from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.v1.auth import ok, require_admin
from app.core.database import get_db
from app.models.db_models import AlertRecord, PoliceGestureLog, RecognitionRecord, User
from app.utils.logger import logger

router = APIRouter()

GESTURE_TYPES = ("police_gesture", "driver_gesture")


def _count_gesture_records(
    db: Session,
    *,
    record_type: str | None = None,
    today_only: bool = False,
    success_only: bool = False,
) -> int:
    query = db.query(func.count(RecognitionRecord.id)).filter(
        RecognitionRecord.type.in_(GESTURE_TYPES)
    )
    if record_type:
        query = query.filter(RecognitionRecord.type == record_type)
    if today_only:
        query = query.filter(func.date(RecognitionRecord.created_at) == date.today())
    if success_only:
        query = query.filter(RecognitionRecord.success.is_(True))
    return query.scalar() or 0


def _count_police_logs(db: Session, *, today_only: bool = False, success_only: bool = False) -> int:
    query = db.query(func.count(PoliceGestureLog.id))
    if today_only:
        query = query.filter(func.date(PoliceGestureLog.created_at) == date.today())
    if success_only:
        query = query.filter(PoliceGestureLog.success.is_(True))
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

    gesture_record_total = _count_gesture_records(db)
    gesture_record_today = _count_gesture_records(db, today_only=True)
    gesture_record_success = _count_gesture_records(db, success_only=True)
    gesture_record_today_success = _count_gesture_records(
        db, today_only=True, success_only=True
    )

    total_alerts = db.query(func.count(AlertRecord.id)).scalar() or 0
    unread_alerts = (
        db.query(func.count(AlertRecord.id)).filter(AlertRecord.acknowledged.is_(False)).scalar() or 0
    )

    return ok(
        {
            # 手势三项主指标：统一来自 recognition_records，口径一致
            "gestureRecordTotal": gesture_record_total,
            "gestureRecordToday": gesture_record_today,
            "gestureRecordSuccess": gesture_record_success,
            "gestureRecordTodaySuccess": gesture_record_today_success,
            # 兼容旧字段名（值与上面对齐）
            "totalGestures": gesture_record_total,
            "todayGestures": gesture_record_today,
            "successGestures": gesture_record_success,
            "totalPlates": total_plates,
            "totalAlerts": total_alerts,
            "unreadAlerts": unread_alerts,
            # 明细页分类计数（与主指标同源；推理日志单独列出，不参与上面三项求和）
            "gestureBreakdown": {
                "policeRecords": _count_gesture_records(db, record_type="police_gesture"),
                "driverRecords": _count_gesture_records(db, record_type="driver_gesture"),
                "policeRecordsSuccess": _count_gesture_records(
                    db, record_type="police_gesture", success_only=True
                ),
                "driverRecordsSuccess": _count_gesture_records(
                    db, record_type="driver_gesture", success_only=True
                ),
                "policeInferenceLogs": _count_police_logs(db),
                "policeInferenceLogsSuccess": _count_police_logs(db, success_only=True),
            },
            "todayGestureBreakdown": {
                "policeRecords": _count_gesture_records(
                    db, record_type="police_gesture", today_only=True
                ),
                "driverRecords": _count_gesture_records(
                    db, record_type="driver_gesture", today_only=True
                ),
                "policeRecordsSuccess": _count_gesture_records(
                    db, record_type="police_gesture", today_only=True, success_only=True
                ),
                "driverRecordsSuccess": _count_gesture_records(
                    db, record_type="driver_gesture", today_only=True, success_only=True
                ),
                "policeInferenceLogs": _count_police_logs(db, today_only=True),
                "policeInferenceLogsSuccess": _count_police_logs(
                    db, today_only=True, success_only=True
                ),
            },
        }
    )
