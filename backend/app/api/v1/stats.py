from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.db_models import PoliceGestureLog
from app.utils.logger import logger

router = APIRouter()


@router.get("/stats/dashboard")
async def get_dashboard_stats(db: Session = Depends(get_db)):
    """获取仪表盘统计数据 (含交警手势识别统计)"""
    logger.info("查询仪表盘统计")

    total_gestures = db.query(func.count(PoliceGestureLog.id)).scalar() or 0
    success_gestures = (
        db.query(func.count(PoliceGestureLog.id))
        .filter(PoliceGestureLog.success == True)
        .scalar()
        or 0
    )
    # 今天识别数
    from datetime import date
    today = date.today()
    today_gestures = (
        db.query(func.count(PoliceGestureLog.id))
        .filter(func.date(PoliceGestureLog.created_at) == today)
        .scalar()
        or 0
    )

    return {
        "code": 200,
        "message": "success",
        "data": {
            "totalPlates": 0,  # TODO: 车牌识别统计
            "totalGestures": total_gestures,
            "todayGestures": today_gestures,
            "successGestures": success_gestures,
            "totalAlerts": 0,  # TODO: 告警统计
            "unreadAlerts": 0,
        },
    }
