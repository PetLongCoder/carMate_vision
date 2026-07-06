from fastapi import APIRouter, UploadFile, File, HTTPException
import cv2
import numpy as np
from app.utils.logger import logger
from app.services.plate_recognition import recognize_plates

router = APIRouter()


@router.post("/plate/recognize")
async def recognize_plate(file: UploadFile = File(...)):
    """
    车牌识别接口
    前端对接文档: POST /api/plate/recognize

    接收图片 → 检测车辆 → 识别车牌 → 返回 PlateResult[]
    """
    logger.info(f"收到车牌识别请求: {file.filename}")

    # 1. 读取并解码图片
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="上传的文件为空")

    nparr = np.frombuffer(contents, np.uint8)
    image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if image is None:
        raise HTTPException(status_code=400, detail="无法解码图片，请上传 JPG/PNG 格式")

    logger.info(f"图片尺寸: {image.shape[1]}x{image.shape[0]}")

    # 2. 车辆检测 + 车牌识别 pipeline
    plates = recognize_plates(image)

    # 3. 返回结果
    return {
        "code": 200,
        "message": "识别完成" if plates else "未识别到车牌",
        "data": plates,
    }
