"""
车牌识别 API
=============

REST 端点:
- POST /api/plate/recognize      — 图片/视频上传识别 (现有)
- POST /api/plate/stream/start   — 启动流追踪会话
- POST /api/plate/stream/stop/{id} — 停止会话
- GET  /api/plate/stream/sessions — 列出活跃会话
- GET  /api/plate/stream/sessions/{id} — 查询会话详情
"""
import asyncio
import os
import time
import tempfile
from typing import Optional
from pathlib import Path

import cv2
import numpy as np
from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from fastapi.responses import StreamingResponse

from app.services.plate_recognition import (
    recognize_plates,
    recognize_plates_from_video,
)
from app.services.session_manager import (
    SessionStatus,
    SessionType,
    session_manager,
)
from app.utils.logger import logger

router = APIRouter()

# 常见视频扩展名
VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".flv", ".wmv"}


# ═══════════════════════════════════════════════════════════
#  原有接口: 图片/视频上传识别
# ═══════════════════════════════════════════════════════════

@router.post("/plate/recognize")
async def recognize_plate(file: UploadFile = File(...)):
    """
    车牌识别接口 (POST /api/plate/recognize)

    接收图片或视频 → 检测车辆 → 识别车牌 → 返回 PlateResult[]

    图片: 立即处理并返回结果
    视频: 逐帧采样处理, 去重合并后返回
    """
    logger.info(f"收到车牌识别请求: {file.filename} (type={file.content_type})")

    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="上传的文件为空")

    ext = os.path.splitext(file.filename or "")[1].lower()
    is_video = ext in VIDEO_EXTENSIONS or (
        file.content_type and file.content_type.startswith("video/")
    )

    if is_video:
        logger.info(f"检测到视频文件, 启动视频识别管道")
        plates = recognize_plates_from_video(contents)
    else:
        nparr = np.frombuffer(contents, np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if image is None:
            raise HTTPException(
                status_code=400, detail="无法解码图片, 请上传 JPG/PNG 格式"
            )
        logger.info(f"图片尺寸: {image.shape[1]}x{image.shape[0]}")
        plates = recognize_plates(image)

    return {
        "code": 200,
        "message": "识别完成" if plates else "未识别到车牌",
        "data": plates,
    }


# ═══════════════════════════════════════════════════════════
#  新增: 视频上传并实时追踪 (返回 session_id)
# ═══════════════════════════════════════════════════════════

@router.post("/plate/track")
async def track_video(file: UploadFile = File(...)):
    """
    上传视频并启动实时追踪 (POST /api/plate/track)

    与 /plate/recognize 的区别:
    - 返回 session_id, 可配合 WebSocket 实时接收逐帧检测结果
    - WebSocket 连接: ws://host/api/ws/plate/track/{session_id}

    返回:
      {"code": 200, "data": {"sessionId": "...", "fileName": "...",
                              "fileSize": ..., "status": "processing"}}
    """
    logger.info(f"收到实时追踪请求: {file.filename}")

    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="上传的文件为空")

    # 保存到临时文件
    ext = os.path.splitext(file.filename or "video.mp4")[1].lower()
    if ext not in VIDEO_EXTENSIONS:
        ext = ".mp4"

    tmp_file = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
    tmp_file.write(contents)
    tmp_path = tmp_file.name
    tmp_file.close()

    # 获取帧数
    cap = cv2.VideoCapture(tmp_path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()

    # 创建会话
    session = await session_manager.create_session(
        SessionType.VIDEO, tmp_path, total_frames
    )

    logger.info(
        f"视频追踪会话已创建: {session.session_id}, "
        f"{len(contents)} bytes, {total_frames} 帧"
    )

    return {
        "code": 200,
        "message": "视频已上传, 请连接 WebSocket 接收实时结果",
        "data": {
            "sessionId": session.session_id,
            "fileName": file.filename or "video.mp4",
            "fileSize": len(contents),
            "totalFrames": total_frames,
            "status": SessionStatus.PENDING.value,
            "wsEndpoint": f"/api/ws/plate/track/{session.session_id}",
        },
    }


# ═══════════════════════════════════════════════════════════
#  新增: 流媒体地址追踪 (MediaMTX + FFmpeg)
# ═══════════════════════════════════════════════════════════

@router.post("/plate/stream/start")
async def start_stream_tracking(
    url: str = Form(...),
    name: str = Form(""),
    push_enabled: bool = Form(False),
    push_url: str = Form(""),
):
    """
    启动流媒体追踪 (POST /api/plate/stream/start)

    接收 RTSP/RTMP/HTTP 流地址, 启动后台帧处理任务。
    可选择将标注后的视频帧推送到指定流媒体地址。

    参数:
      url:          流地址 (例如 rtsp://localhost:8554/camera)
      name:         可选名称 (例如 "前摄像头")
      push_enabled: 是否启用推流 (默认 False)
      push_url:     推流目标地址, 为空时自动生成
                    (例如 rtsp://localhost:8554/recognized/{sessionId})

    返回 sessionId, 用于 WebSocket 连接:
      ws://host/api/ws/plate/track/{sessionId}

    前置条件:
      - 流媒体服务器 (如 MediaMTX) 已启动并推送流
      - 确保后端能访问该流地址
      - 启用推流需要安装 FFmpeg 并加入 PATH
    """
    if not url or not url.strip():
        raise HTTPException(status_code=400, detail="流地址不能为空")

    url = url.strip()
    logger.info(f"收到流追踪请求: {url}")

    # 验证流是否可连接
    cap = cv2.VideoCapture(url)
    if not cap.isOpened():
        raise HTTPException(
            status_code=400,
            detail=f"无法连接到流地址: {url}. 请确认流媒体服务器已启动且地址正确。"
        )
    cap.release()

    # 创建会话
    session = await session_manager.create_session(SessionType.STREAM, url)

    # 确定推流地址
    resolved_push_url: Optional[str] = None
    if push_enabled:
        resolved_push_url = (
            push_url.strip()
            if push_url.strip()
            else f"rtsp://127.0.0.1:8554/recognized/{session.session_id}"
        )
        logger.info("推流已启用, 目标地址: %s", resolved_push_url)

    # 在后台启动处理任务
    from app.services.video_processor import run_video_session
    asyncio.create_task(run_video_session(session, push_url=resolved_push_url))

    logger.info(
        "流追踪会话已创建: %s, URL: %s, 推流: %s",
        session.session_id, url, resolved_push_url or "禁用"
    )

    return {
        "code": 200,
        "message": "流追踪已启动",
        "data": {
            "sessionId": session.session_id,
            "name": name or url,
            "url": url,
            "status": SessionStatus.PROCESSING.value,
            "wsEndpoint": f"/api/ws/plate/track/{session.session_id}",
            "pushEnabled": push_enabled,
            "pushUrl": resolved_push_url or None,
        },
    }


@router.post("/plate/stream/stop/{session_id}")
async def stop_stream_tracking(session_id: str):
    """停止指定会话的流追踪"""
    session = await session_manager.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"会话 {session_id} 不存在")

    session.update_status(SessionStatus.STOPPED, "用户手动停止")
    logger.info(f"会话 {session_id} 已手动停止")

    return {
        "code": 200,
        "message": "会话已停止",
        "data": {"sessionId": session_id, "status": SessionStatus.STOPPED.value},
    }


@router.get("/plate/stream/sessions")
async def list_stream_sessions():
    """列出所有追踪会话"""
    sessions = await session_manager.list_sessions()
    return {
        "code": 200,
        "message": f"共 {len(sessions)} 个会话",
        "data": sessions,
    }


@router.get("/plate/stream/sessions/{session_id}")
async def get_stream_session(session_id: str):
    """查询某个会话的详细信息"""
    session = await session_manager.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"会话 {session_id} 不存在")
    return {
        "code": 200,
        "message": "success",
        "data": session.to_dict(),
    }


@router.get("/plate/stream/{session_id}/mjpeg")
async def stream_mjpeg(session_id: str):
    """
    MJPEG 流端点 (GET /api/plate/stream/{session_id}/mjpeg)

    返回 multipart/x-mixed-replace 格式的连续 JPEG 帧,
    前端可直接用 <img> 标签播放。
    """
    session = await session_manager.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"会话 {session_id} 不存在")

    async def frame_generator():
        boundary = b"--frame\r\n"
        while True:
            async with session._frame_cond:
                await session._frame_cond.wait()
                if session.latest_frame is not None:
                    yield boundary
                    yield b"Content-Type: image/jpeg\r\n"
                    yield f"Content-Length: {len(session.latest_frame)}\r\n".encode()
                    yield b"\r\n"
                    yield session.latest_frame
                    yield b"\r\n"

            # 会话结束则停止
            if session.status in (SessionStatus.COMPLETED,
                                  SessionStatus.ERROR,
                                  SessionStatus.STOPPED):
                break

    return StreamingResponse(
        frame_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )
