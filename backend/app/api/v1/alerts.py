from fastapi import APIRouter, Query
from typing import Optional
from app.utils.logger import logger

router = APIRouter()


@router.get("/alerts")
async def get_alerts(
    page: Optional[int] = Query(1, ge=1),
    pageSize: Optional[int] = Query(10, ge=1, le=100),
    level: Optional[str] = None
):
    """
    获取告警列表（占位）
    前端对接文档: GET /api/alerts
    """
    logger.info(f"查询告警列表: page={page}, pageSize={pageSize}, level={level}")
    # TODO: 从数据库查询告警
    return {
        "code": 200,
        "message": "success",
        "data": {
            "list": [],
            "total": 0
        }
    }


@router.put("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: int):
    """
    确认告警（占位）
    前端对接文档: PUT /api/alerts/{id}/acknowledge
    """
    logger.info(f"确认告警: id={alert_id}")
    # TODO: 更新数据库告警状态
    return {
        "code": 200,
        "message": "success",
        "data": None
    }