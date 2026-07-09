import json
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.db_models import PoliceGestureLog
from app.utils.logger import logger

router = APIRouter()


@router.get("/history")
async def get_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    type: Optional[str] = Query(None, description="筛选类型: gesture(交警手势)"),
    db: Session = Depends(get_db),
):
    """获取历史记录 — 包含交警手势识别日志"""
    logger.info(f"查询历史记录: page={page}, pageSize={page_size}, type={type}")

    # 构建联合查询 (当前只有交警手势日志, 后续可扩展车牌识别等)
    query = db.query(PoliceGestureLog)

    if type == "gesture" or type is None:
        pass  # 当前全量即 gesture
    elif type:
        # 未知类型返回空
        return {
            "code": 200,
            "message": "success",
            "data": {"list": [], "total": 0, "page": page, "pageSize": page_size},
        }

    if type == "gesture" or type is None:
        total = query.count()
        rows = (
            query.order_by(desc(PoliceGestureLog.created_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        def _row_to_dict(row):
            segments = None
            if row.segments_json:
                try:
                    segments = json.loads(row.segments_json)
                except Exception:
                    pass
            return {
                "id": row.id,
                "type": "gesture",
                "recognitionType": row.recognition_type,
                "videoSessionId": row.video_session_id,
                "filename": row.filename,
                "gesture": row.gesture,
                "gestureId": row.gesture_id,
                "confidence": row.confidence,
                "inferenceMs": row.inference_ms,
                "videoDuration": row.video_duration,
                "segments": segments,
                "success": row.success,
                "createdAt": row.created_at.isoformat() if row.created_at else None,
            }

        return {
            "code": 200,
            "message": "success",
            "data": {
                "list": [_row_to_dict(row) for row in rows],
                "total": total,
                "page": page,
                "pageSize": page_size,
            },
        }
