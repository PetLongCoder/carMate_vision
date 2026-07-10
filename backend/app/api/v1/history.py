from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api.v1.auth import ok, require_current_user
from app.core.database import get_db
from app.models.db_models import HistoryRecord, User
from app.services.record_service import TYPE_LABELS, history_record_to_dict
from app.utils.date_filters import apply_created_at_end, apply_created_at_start

router = APIRouter()


def _apply_filters(
    query,
    *,
    record_type: Optional[str],
    source_type: Optional[str],
    success: Optional[bool],
    keyword: Optional[str],
    start_date: Optional[str],
    end_date: Optional[str],
):
    if record_type:
        query = query.filter(HistoryRecord.type == record_type)
    if source_type:
        query = query.filter(
            or_(
                HistoryRecord.result_json.like(f'%"sourceType": "{source_type}"%'),
                HistoryRecord.result_json.like(f'%"sourceType":"{source_type}"%'),
            )
        )
    if success is not None:
        if success:
            query = query.filter(
                or_(
                    HistoryRecord.result_json.like('%"success": true%'),
                    HistoryRecord.result_json.like('%"success":true%'),
                    HistoryRecord.result_json.is_(None),
                    ~HistoryRecord.result_json.like('%"success":%'),
                )
            )
        else:
            query = query.filter(
                or_(
                    HistoryRecord.result_json.like('%"success": false%'),
                    HistoryRecord.result_json.like('%"success":false%'),
                )
            )
    if keyword:
        kw = keyword.strip()
        query = query.filter(
            or_(
                HistoryRecord.result_json.like(f"%{kw}%"),
                HistoryRecord.type.like(f"%{kw}%"),
            )
        )
    if start_date:
        query = apply_created_at_start(query, HistoryRecord.created_at, start_date)
    if end_date:
        query = apply_created_at_end(query, HistoryRecord.created_at, end_date)
    return query


@router.get("/history")
def get_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100, alias="pageSize"),
    type: Optional[str] = None,
    source_type: Optional[str] = Query(None, alias="sourceType"),
    success: Optional[bool] = None,
    keyword: Optional[str] = None,
    start_date: Optional[str] = Query(None, alias="startDate"),
    end_date: Optional[str] = Query(None, alias="endDate"),
    user: User = Depends(require_current_user),
    db: Session = Depends(get_db),
):
    """当前登录用户的识别历史（history_records）。"""
    query = db.query(HistoryRecord).filter(HistoryRecord.user_id == user.id)
    query = _apply_filters(
        query,
        record_type=type,
        source_type=source_type,
        success=success,
        keyword=keyword,
        start_date=start_date,
        end_date=end_date,
    )

    total = query.count()
    records = (
        query.order_by(HistoryRecord.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return ok({"list": [history_record_to_dict(item) for item in records], "total": total})


@router.get("/history/types")
def list_history_types(_: User = Depends(require_current_user)):
    return ok([{"value": key, "label": label} for key, label in TYPE_LABELS.items()])
