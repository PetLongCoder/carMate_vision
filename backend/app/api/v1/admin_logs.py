from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.v1.auth import ok, require_admin
from app.core.database import get_db
from app.models.db_models import User, UserOperationLog
from app.services.operation_log_service import ACTION_LABELS, log_operation, operation_log_to_dict

router = APIRouter(prefix="/admin", tags=["管理员"])


@router.get("/operation-logs/actions")
def list_operation_log_actions(_: User = Depends(require_admin)):
    return ok([{"value": key, "label": label} for key, label in ACTION_LABELS.items()])


@router.get("/operation-logs")
def list_operation_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100, alias="pageSize"),
    username: Optional[str] = None,
    action: Optional[str] = None,
    success: Optional[bool] = None,
    start_date: Optional[str] = Query(None, alias="startDate"),
    end_date: Optional[str] = Query(None, alias="endDate"),
    request: Request = None,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    query = db.query(UserOperationLog)
    if username:
        query = query.filter(UserOperationLog.username.like(f"%{username.strip()}%"))
    if action:
        query = query.filter(UserOperationLog.action == action)
    if success is not None:
        query = query.filter(UserOperationLog.success == success)
    if start_date:
        try:
            start = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
            query = query.filter(UserOperationLog.created_at >= start.replace(tzinfo=None))
        except ValueError:
            pass
    if end_date:
        try:
            end = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
            query = query.filter(UserOperationLog.created_at <= end.replace(tzinfo=None))
        except ValueError:
            pass

    total = query.count()
    records = (
        query.order_by(UserOperationLog.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    log_operation(
        db,
        action="view_operation_logs",
        user=admin,
        success=True,
        request=request,
        detail={"page": page, "pageSize": page_size},
    )

    return ok(
        {
            "list": [operation_log_to_dict(item) for item in records],
            "total": total,
            "page": page,
            "pageSize": page_size,
        }
    )
