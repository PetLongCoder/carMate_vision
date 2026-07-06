from fastapi import APIRouter, Query
from typing import Optional
from app.utils.logger import logger

router = APIRouter()


@router.get("/history")
async def get_history(
    page: Optional[int] = Query(1, ge=1),
    pageSize: Optional[int] = Query(10, ge=1, le=100),
    type: Optional[str] = None
):
    """
    获取历史记录（占位）
    前端对接文档: GET /api/history
    """
    logger.info(f"查询历史记录: page={page}, pageSize={pageSize}, type={type}")
    # TODO: 从数据库查询历史
    return {
        "code": 200,
        "message": "success",
        "data": {
            "list": [],
            "total": 0
        }
    }