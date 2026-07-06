from fastapi import APIRouter, UploadFile, File
from app.utils.logger import logger

router = APIRouter()


@router.post("/plate/recognize")
async def recognize_plate(file: UploadFile = File(...)):
    """
    车牌识别接口（占位）
    前端对接文档: POST /api/plate/recognize
    """
    logger.info(f"收到车牌识别请求: {file.filename}")
    # TODO: 实现车牌识别逻辑
    return {
        "code": 200,
        "message": "success",
        "data": []  # 空数组表示未检测到车牌
    }