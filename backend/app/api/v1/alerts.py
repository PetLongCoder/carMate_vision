from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.v1.auth import ok, require_admin
from app.core.database import get_db
from app.models.db_models import AlertRecord, User

router = APIRouter()


def alert_to_dict(record: AlertRecord) -> dict:
    return {
        "id": record.id,
        "level": record.level,
        "title": record.title,
        "summary": record.summary or "",
        "source": record.source or "",
        "createdAt": record.created_at.isoformat() if record.created_at else "",
        "acknowledged": record.acknowledged,
    }


@router.get("/alerts")
def get_alerts(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100, alias="pageSize"),
    level: Optional[str] = None,
    acknowledged: Optional[bool] = None,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    query = db.query(AlertRecord)
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
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    record = db.query(AlertRecord).filter(AlertRecord.id == alert_id).first()
    if not record:
        return {"code": 404, "message": "告警不存在", "data": None}

    record.acknowledged = True
    db.commit()
    return ok(None)
