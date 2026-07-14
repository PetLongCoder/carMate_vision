"""
告警统计与分析 API
================
提供告警仪表盘、时间线、事件回放等数据接口。
"""

from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.v1.auth import ok, require_admin, get_current_user
from app.core.database import get_db
from app.models.db_models import AlertRecord, User
from app.services.alert_agent import ANOMALY_TYPE_LABELS, SOURCE_LABELS
from app.services.alert_agent.alert_agent import alert_agent
from app.services.alert_agent.event_collector import event_collector
from app.services.alert_agent import AnomalyEvent, AlertLevel
from app.utils.logger import logger

router = APIRouter()


def _apply_user_filter(query, user: User):
    """对查询应用用户过滤：管理员看所有，普通用户只看自己的告警。"""
    if user.role != "admin":
        return query.filter(AlertRecord.user_id == user.id)
    return query


def alert_to_dict(record: AlertRecord) -> dict:
    """将 AlertRecord 转换为前端友好的字典"""
    suggested_actions = []
    if record.suggested_actions:
        import json
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


# ═══════════════════════════════════════════════════════════
#  告警统计
# ═══════════════════════════════════════════════════════════

@router.get("/alerts/stats")
def get_alert_stats(
    days: int = Query(7, ge=1, le=90),
    user: User | None = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取告警统计数据（仪表盘用）。管理员看所有，普通用户只看自己的。"""
    if user is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="未登录")
    stats = alert_agent.get_stats(db, days=days, user_id=None if user.role == "admin" else user.id)
    return ok(stats)


# ═══════════════════════════════════════════════════════════
#  告警时间线
# ═══════════════════════════════════════════════════════════

@router.get("/alerts/timeline")
def get_alert_timeline(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100, alias="pageSize"),
    start_date: Optional[str] = Query(None, alias="startDate"),
    end_date: Optional[str] = Query(None, alias="endDate"),
    level: Optional[str] = None,
    anomaly_type: Optional[str] = Query(None, alias="anomalyType"),
    user: User | None = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取告警时间线（时间倒序，支持筛选）。管理员看所有，普通用户只看自己的。"""
    if user is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="未登录")
    query = db.query(AlertRecord)

    # 用户过滤
    query = _apply_user_filter(query, user)

    if level:
        query = query.filter(AlertRecord.level == level)
    if anomaly_type:
        query = query.filter(AlertRecord.anomaly_type == anomaly_type)
    if start_date:
        try:
            sd = datetime.fromisoformat(start_date)
            query = query.filter(AlertRecord.created_at >= sd)
        except ValueError:
            pass
    if end_date:
        try:
            ed = datetime.fromisoformat(end_date)
            query = query.filter(AlertRecord.created_at <= ed)
        except ValueError:
            pass

    total = query.count()
    records = (
        query.order_by(AlertRecord.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return ok({
        "list": [alert_to_dict(r) for r in records],
        "total": total,
    })


# ═══════════════════════════════════════════════════════════
#  告警详情（含事件回放数据）
# ═══════════════════════════════════════════════════════════

@router.get("/alerts/{alert_id}/detail")
def get_alert_detail(
    alert_id: int,
    user: User | None = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取告警完整详情，包含原始事件数据用于回放。管理员看所有，普通用户只看自己的。"""
    if user is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="未登录")
    
    query = db.query(AlertRecord).filter(AlertRecord.id == alert_id)
    query = _apply_user_filter(query, user)
    record = query.first()
    if not record:
        return {"code": 404, "message": "告警不存在", "data": None}

    data = alert_to_dict(record)

    # 解析 raw_event 用于事件回放
    raw_event = None
    if record.raw_event:
        import json
        try:
            raw_event = json.loads(record.raw_event)
        except (json.JSONDecodeError, TypeError):
            raw_event = {"raw": record.raw_event}
    data["rawEvent"] = raw_event

    # 查找相关告警（同类型，前后 1 小时内）
    if record.anomaly_type and record.created_at:
        related_query = (
            db.query(AlertRecord)
            .filter(
                AlertRecord.anomaly_type == record.anomaly_type,
                AlertRecord.id != record.id,
                AlertRecord.created_at >= record.created_at - timedelta(hours=1),
                AlertRecord.created_at <= record.created_at + timedelta(hours=1),
            )
        )
        related_query = _apply_user_filter(related_query, user)
        related = (
            related_query
            .order_by(AlertRecord.created_at.desc())
            .limit(10)
            .all()
        )
        data["relatedAlerts"] = [alert_to_dict(r) for r in related]

    return ok(data)


# ═══════════════════════════════════════════════════════════
#  告警分析（聚合）
# ═══════════════════════════════════════════════════════════

@router.get("/alerts/analysis")
def get_alert_analysis(
    days: int = Query(7, ge=1, le=90),
    user: User | None = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取告警原因分析聚合数据。管理员看所有，普通用户只看自己的。"""
    if user is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="未登录")
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    # 异常类型频率排名
    type_query = (
        db.query(
            AlertRecord.anomaly_type,
            func.count(AlertRecord.id).label("count"),
        )
        .filter(
            AlertRecord.anomaly_type.isnot(None),
            AlertRecord.created_at >= cutoff,
        )
    )
    type_query = _apply_user_filter(type_query, user)
    type_rows = (
        type_query
        .group_by(AlertRecord.anomaly_type)
        .order_by(func.count(AlertRecord.id).desc())
        .all()
    )
    top_types = [
        {
            "type": row[0],
            "label": ANOMALY_TYPE_LABELS.get(row[0], row[0]),
            "count": row[1],
        }
        for row in type_rows
    ]

    # 来源模块告警分布
    source_query = (
        db.query(
            AlertRecord.source,
            func.count(AlertRecord.id).label("count"),
        )
        .filter(
            AlertRecord.source.isnot(None),
            AlertRecord.created_at >= cutoff,
        )
    )
    source_query = _apply_user_filter(source_query, user)
    source_rows = (
        source_query
        .group_by(AlertRecord.source)
        .order_by(func.count(AlertRecord.id).desc())
        .all()
    )
    source_distribution = [
        {
            "source": row[0],
            "label": SOURCE_LABELS.get(row[0], row[0]),
            "count": row[1],
        }
        for row in source_rows
    ]

    # 按小时分布（峰值时段）
    hour_query = (
        db.query(
            func.hour(AlertRecord.created_at).label("hour"),
            func.count(AlertRecord.id).label("count"),
        )
        .filter(AlertRecord.created_at >= cutoff)
    )
    hour_query = _apply_user_filter(hour_query, user)
    hour_rows = (
        hour_query
        .group_by("hour")
        .order_by("hour")
        .all()
    )
    peak_hours = [
        {"hour": row[0], "count": row[1]} for row in hour_rows
    ]

    # 确认率
    total_q = _apply_user_filter(
        db.query(func.count(AlertRecord.id)).filter(AlertRecord.created_at >= cutoff),
        user,
    )
    total = total_q.scalar() or 0
    ack_q = _apply_user_filter(
        db.query(func.count(AlertRecord.id)).filter(
            AlertRecord.created_at >= cutoff,
            AlertRecord.acknowledged.is_(True),
        ),
        user,
    )
    acknowledged = ack_q.scalar() or 0
    ack_rate = round(acknowledged / total * 100, 1) if total > 0 else 0

    return ok({
        "topAnomalyTypes": top_types,
        "sourceDistribution": source_distribution,
        "peakHours": peak_hours,
        "ackRate": ack_rate,
        "total": total,
        "acknowledged": acknowledged,
    })


# ═══════════════════════════════════════════════════════════
#  异常类型列表（供前端筛选下拉）
# ═══════════════════════════════════════════════════════════

@router.get("/alerts/anomaly-types")
def get_anomaly_types(user: User | None = Depends(get_current_user)):
    """获取所有可用的异常类型及中文标签"""
    if user is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="未登录")
    types = [
        {"value": key, "label": label}
        for key, label in sorted(ANOMALY_TYPE_LABELS.items())
    ]
    return ok(types)


# ═══════════════════════════════════════════════════════════
#  测试告警生成（开发调试用）
# ═══════════════════════════════════════════════════════════

@router.post("/alerts/test")
async def trigger_test_alert(
    anomaly_type: str = Query("plate_recognition_failure", alias="type"),
    level: str = Query("warning"),
    _: User = Depends(require_admin),
):
    """手动触发测试告警（仅管理员，开发调试用）"""
    import time

    test_detail = {
        "error": f"测试告警: {anomaly_type}",
        "test": True,
        "triggered_by": "admin",
    }

    severity_hint = None
    try:
        severity_hint = AlertLevel(level)
    except ValueError:
        severity_hint = AlertLevel.WARNING

    event = AnomalyEvent(
        source="system",
        anomaly_type=anomaly_type,
        title=f"[测试] {ANOMALY_TYPE_LABELS.get(anomaly_type, anomaly_type)}",
        detail=test_detail,
        timestamp=time.time(),
        severity_hint=severity_hint,
    )

    alert_id = await alert_agent.process_event(event)

    if alert_id:
        logger.info(f"测试告警已生成: id={alert_id}")
        return ok({"alertId": alert_id, "message": "测试告警已生成"})
    else:
        return ok({"alertId": None, "message": "测试告警被防抖过滤，请稍后再试"})


# ═══════════════════════════════════════════════════════════
#  批量确认
# ═══════════════════════════════════════════════════════════

@router.put("/alerts/batch-acknowledge")
def batch_acknowledge_alerts(
    alert_ids: list[int] = Query([], alias="ids"),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """批量确认告警"""
    if not alert_ids:
        return {"code": 400, "message": "请提供要确认的告警 ID 列表", "data": None}

    now = datetime.now(timezone.utc)
    updated = (
        db.query(AlertRecord)
        .filter(
            AlertRecord.id.in_(alert_ids),
            AlertRecord.acknowledged.is_(False),
        )
        .update(
            {
                "acknowledged": True,
                "acknowledged_by": admin.username,
                "acknowledged_at": now,
            },
            synchronize_session=False,
        )
    )
    db.commit()

    logger.info(f"批量确认告警: {updated} 条, 操作者: {admin.username}")
    return ok({"updated": updated})
