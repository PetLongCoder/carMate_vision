from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import exists, or_
from sqlalchemy.orm import Session

from app.api.v1.auth import ok, require_admin
from app.core.database import get_db
from app.models.db_models import HistoryRecord, PlateRecord, User
from app.services.record_service import TYPE_LABELS, history_record_to_dict
from app.utils.date_filters import apply_created_at_end, apply_created_at_start

router = APIRouter(prefix="/admin", tags=["管理员"])


def _apply_filters(
    query,
    *,
    record_type: Optional[str],
    source_type: Optional[str],
    success: Optional[bool],
    keyword: Optional[str],
    plate_no: Optional[str],
    username: Optional[str],
    start_date: Optional[str],
    end_date: Optional[str],
):
    if record_type:
        query = query.filter(HistoryRecord.type == record_type)
    if username:
        query = query.filter(User.username.like(f"%{username.strip()}%"))
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
    if plate_no:
        kw = plate_no.strip()
        query = query.filter(
            exists().where(
                PlateRecord.history_record_id == HistoryRecord.id,
                PlateRecord.plate_no.like(f"%{kw}%"),
            )
        )
    if start_date:
        query = apply_created_at_start(query, HistoryRecord.created_at, start_date)
    if end_date:
        query = apply_created_at_end(query, HistoryRecord.created_at, end_date)
    return query


@router.get("/recognition-records/types")
def list_recognition_types(_: User = Depends(require_admin)):
    return ok([{"value": key, "label": label} for key, label in TYPE_LABELS.items()])


@router.get("/recognition-records")
def list_recognition_records(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100, alias="pageSize"),
    type: Optional[str] = None,
    source_type: Optional[str] = Query(None, alias="sourceType"),
    success: Optional[bool] = None,
    keyword: Optional[str] = None,
    username: Optional[str] = None,
    plate_no: Optional[str] = Query(None, alias="plateNo"),
    start_date: Optional[str] = Query(None, alias="startDate"),
    end_date: Optional[str] = Query(None, alias="endDate"),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """管理员查看全部用户的识别记录（history_records）。"""
    query = (
        db.query(HistoryRecord, User.username)
        .outerjoin(User, HistoryRecord.user_id == User.id)
    )
    query = _apply_filters(
        query,
        record_type=type,
        source_type=source_type,
        success=success,
        keyword=keyword,
        plate_no=plate_no,
        username=username,
        start_date=start_date,
        end_date=end_date,
    )

    total = query.count()
    rows = (
        query.order_by(HistoryRecord.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return ok(
        {
            "list": [
                history_record_to_dict(record, username=uname)
                for record, uname in rows
            ],
            "total": total,
            "page": page,
            "pageSize": page_size,
        }
    )
