from typing import Optional
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.v1.auth import ok, require_current_user
from app.core.database import get_db
from app.models.db_models import AlertRecord, User
from app.services.alert_agent import ANOMALY_TYPE_LABELS, SOURCE_LABELS

router = APIRouter()


def alert_to_dict(record: AlertRecord) -> dict:
    """将 AlertRecord 转换为前端友好的字典"""
    suggested_actions = []
    if record.suggested_actions:
        try:
            suggested_actions = json.loads(record.suggested_actions)
        except (json.JSONDecodeError, TypeError):
            suggested_actions = [record.suggested_actions]

    notified_channels = []
    if record.notified_channels:
        notified_channels = [c.strip() for c in record.notified_channels.split(",") if c.strip()]

    return {
        "id": record.id,
        "level": record.level,
        "title": record.title,
        "summary": record.summary or "",
        "source": record.source or "",
        "sourceLabel": SOURCE_LABELS.get(record.source or "", record.source or ""),
        "anomalyType": record.anomaly_type or "",
        "anomalyTypeLabel": ANOMALY_TYPE_LABELS.get(record.anomaly_type or "", record.anomaly_type or ""),
        "impactScope": record.impact_scope or "",
        "suggestedActions": suggested_actions,
        "notifiedChannels": notified_channels,
        "acknowledged": record.acknowledged,
        "acknowledgedBy": record.acknowledged_by,
        "acknowledgedAt": record.acknowledged_at.isoformat() if record.acknowledged_at else None,
        "createdAt": record.created_at.isoformat() if record.created_at else "",
    }


@router.get("/alerts")
def get_alerts(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100, alias="pageSize"),
    level: Optional[str] = None,
    acknowledged: Optional[bool] = None,
    user: User = Depends(require_current_user),
    db: Session = Depends(get_db),
):
    """获取告警列表。管理员看所有告警，普通用户只看自己的告警。"""
    query = db.query(AlertRecord)
    
    # 普通用户只看自己的告警，管理员看所有
    if user.role != "admin":
        query = query.filter(AlertRecord.user_id == user.id)
    
    if level:
        query = query.filter(AlertRecord.level == level)
    if acknowledged is not None:
        query = query.filter(AlertRecord.acknowledged == acknowledged)

    total = query.count()
    records = (
        query.order_by(AlertRecord.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return ok({"list": [alert_to_dict(item) for item in records], "total": total})


@router.put("/alerts/{alert_id}/acknowledge")
def acknowledge_alert(
    alert_id: int,
    user: User = Depends(require_current_user),
    db: Session = Depends(get_db),
):
    """确认告警。用户只能确认自己的告警，管理员可以确认所有。"""
    query = db.query(AlertRecord).filter(AlertRecord.id == alert_id)
    if user.role != "admin":
        query = query.filter(AlertRecord.user_id == user.id)
    record = query.first()
    if not record:
        return {"code": 404, "message": "告警不存在或无权操作", "data": None}

    record.acknowledged = True
    record.acknowledged_by = user.username
    record.acknowledged_at = datetime.now(timezone.utc)
    db.commit()
    return ok(None)
