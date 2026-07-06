from fastapi import APIRouter
from app.utils.logger import logger

router = APIRouter()


@router.get("/stats/dashboard")
async def get_dashboard_stats():
    """
    获取仪表盘统计数据（占位）
    前端对接文档: GET /api/stats/dashboard
    """
    logger.info("查询仪表盘统计")
    # TODO: 从数据库汇总统计
    return {
        "code": 200,
        "message": "success",
        "data": {
            "totalPlates": 0,
            "totalGestures": 0,
            "totalAlerts": 0,
            "unreadAlerts": 0
        }
    }