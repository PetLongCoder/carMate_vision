import os
from fastapi import APIRouter, UploadFile, File, HTTPException
import cv2
import numpy as np
from app.utils.logger import logger
from app.services.plate_recognition import recognize_plates, recognize_plates_from_video

router = APIRouter()

# 常见视频扩展名
VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".flv", ".wmv"}


@router.post("/plate/recognize")
async def recognize_plate(file: UploadFile = File(...)):
    """
    车牌识别接口
    前端对接文档: POST /api/plate/recognize

    接收图片或视频 → 检测车辆 → 识别车牌 → 返回 PlateResult[]
    """
    logger.info(f"收到车牌识别请求: {file.filename} (type={file.content_type})")

    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="上传的文件为空")

    # ── 判断是否为视频 ──
    ext = os.path.splitext(file.filename or "")[1].lower()
    is_video = ext in VIDEO_EXTENSIONS or (
        file.content_type and file.content_type.startswith("video/")
    )

    if is_video:
        logger.info(f"检测到视频文件，启动视频识别管道")
        plates = recognize_plates_from_video(contents)
    else:
        # ── 图片处理（原有逻辑） ──
        nparr = np.frombuffer(contents, np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if image is None:
            raise HTTPException(
                status_code=400, detail="无法解码图片，请上传 JPG/PNG 格式"
            )
        logger.info(f"图片尺寸: {image.shape[1]}x{image.shape[0]}")
        plates = recognize_plates(image)

    return {
        "code": 200,
        "message": "识别完成" if plates else "未识别到车牌",
        "data": plates,
    }
