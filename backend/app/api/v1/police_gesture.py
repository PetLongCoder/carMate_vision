from fastapi import APIRouter, UploadFile, File
from app.utils.logger import logger

router = APIRouter()


@router.post("/police-gesture/recognize")
async def recognize_police_gesture(file: UploadFile = File(...)):
    """
    交警手势识别接口（占位）
    前端对接文档: POST /api/police-gesture/recognize
    """
    logger.info(f"收到交警手势识别请求: {file.filename}")
    # TODO: 实现交警手势识别逻辑
    return {
        "code": 200,
        "message": "success",
        "data": {
            "gesture": "停止",
            "gestureId": 0,
            "confidence": 0.95,
            "timestamp": 1750233600000
        }
    }