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
from pathlib import Path

import cv2
import numpy as np
from fastapi import APIRouter, UploadFile, File, HTTPException, Form, Response, Request, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.v1.auth import get_current_user
from app.core.database import get_db
from app.models.db_models import User
from app.services.record_service import build_plate_summary, log_recognition

from app.services.plate_recognition import (
    recognize_plates,
    recognize_plates_from_video,
)
from app.services.session_manager import (
    SessionStatus,
    SessionType,
    session_manager,
)
from app.services.alert_agent.event_collector import event_collector
from app.services.alert_agent import AnomalyEvent, AlertLevel
from app.utils.logger import logger

router = APIRouter()

# 常见视频扩展名
VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".flv", ".wmv"}


# ═══════════════════════════════════════════════════════════
#  原有接口: 图片/视频上传识别
# ═══════════════════════════════════════════════════════════

@router.post("/plate/recognize")
async def recognize_plate(
    file: UploadFile = File(...),
    request: Request = None,
    user: User | None = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    车牌识别接口 (POST /api/plate/recognize)

    接收图片或视频 → 检测车辆 → 识别车牌 → 返回 PlateResult[]

    图片: 立即处理并返回结果
    视频: 逐帧采样处理, 去重合并后返回
    """
    logger.info(f"收到车牌识别请求: {file.filename} (type={file.content_type})")

    try:
        from app.services.plate_recognition import recognize_plates, recognize_plates_from_video
    except Exception as exc:
        logger.error(f"车牌识别模块加载失败: {exc}")
        event_collector.collect(AnomalyEvent(
            source="plate_recognition",
            anomaly_type="plate_model_load_failure",
            title="车牌识别模块加载失败",
            detail={"error": str(exc), "filename": file.filename},
            severity_hint=AlertLevel.CRITICAL,
        ))
        raise HTTPException(status_code=503, detail="车牌识别模块未就绪，请稍后重试") from exc

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
            event_collector.collect(AnomalyEvent(
                source="plate_recognition",
                anomaly_type="plate_frame_decode_failure",
                title="图片解码失败",
                detail={"filename": file.filename, "ext": ext},
            ))
            raise HTTPException(
                status_code=400, detail="无法解码图片, 请上传 JPG/PNG 格式"
            )
        logger.info(f"图片尺寸: {image.shape[1]}x{image.shape[0]}")
        plates = recognize_plates(image)

    log_recognition(
        db,
        record_type="plate",
        source_type="video" if is_video else "image",
        success=bool(plates),
        summary=build_plate_summary(plates),
        result={"plates": plates},
        file_name=file.filename,
        user=user,
    )

    return {
        "code": 200,
        "message": "识别完成" if plates else "未识别到车牌",
        "data": plates,
    }


# ═══════════════════════════════════════════════════════════
#  新增: 视频上传并实时追踪 (返回 session_id)
# ═══════════════════════════════════════════════════════════

@router.post("/plate/track")
async def track_video(
    file: UploadFile = File(...),
    request: Request = None,
    user: User | None = Depends(get_current_user),
    db: Session = Depends(get_db),
):
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
        SessionType.VIDEO,
        tmp_path,
        total_frames,
        delete_source_on_cleanup=True,
    )

    logger.info(
        f"视频追踪会话已创建: {session.session_id}, "
        f"{len(contents)} bytes, {total_frames} 帧"
    )

    log_recognition(
        db,
        record_type="plate",
        source_type="track",
        success=True,
        summary=f"视频追踪 {file.filename or 'video.mp4'}",
        result={
            "sessionId": session.session_id,
            "fileName": file.filename,
            "totalFrames": total_frames,
        },
        file_name=file.filename,
        session_id=session.session_id,
        user=user,
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
    user: User | None = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    启动流媒体追踪 (POST /api/plate/stream/start)

    接收 RTSP/RTMP/HTTP 流地址, 启动后台帧处理任务。

    参数:
      url:  流地址 (例如 rtsp://localhost:8554/camera)
      name: 可选名称 (例如 "前摄像头")

    返回 sessionId, 用于 WebSocket 连接:
      ws://host/api/ws/plate/track/{sessionId}
    """
    if not url or not url.strip():
        raise HTTPException(status_code=400, detail="流地址不能为空")

    url = url.strip()
    logger.info(f"收到流追踪请求: {url}")

    # 简单的 URL 格式校验（不实际连接，避免 cv2.VideoCapture 阻塞事件循环）
    # 实际连接由后台任务 _run_stream_loop 处理，失败时会通过 WebSocket 返回错误
    if not (url.startswith("rtsp://") or url.startswith("rtmp://") or url.startswith("http")):
        raise HTTPException(
            status_code=400,
            detail=f"不支持的流地址格式: {url}。请使用 rtsp:// 或 rtmp:// 形式的地址。"
        )

    # 创建会话
    session = await session_manager.create_session(SessionType.STREAM, url)

    # 写入历史记录（先写记录，再启动后台任务，避免竞态）
    log_recognition(
        db,
        record_type="plate",
        source_type="stream",
        success=True,
        summary=f"流追踪 {name or url}",
        result={
            "sessionId": session.session_id,
            "url": url,
            "name": name or url,
        },
        file_name=name or None,
        session_id=session.session_id,
        user=user,
    )

    # 在后台启动处理任务
    from app.services.video_processor import run_video_session
    asyncio.create_task(run_video_session(session))

    logger.info(f"流追踪会话已创建: {session.session_id}, URL: {url}")

    return {
        "code": 200,
        "message": "流追踪已启动",
        "data": {
            "sessionId": session.session_id,
            "name": name or url,
            "url": url,
            "status": SessionStatus.PROCESSING.value,
            "wsEndpoint": f"/api/ws/plate/track/{session.session_id}",
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
        last_frame = b""
        while True:
            if session.status in (SessionStatus.COMPLETED,
                                  SessionStatus.ERROR,
                                  SessionStatus.STOPPED):
                break

            # 直接读取最新帧，不使用条件变量（避免通知竞争）
            frame = session.latest_frame if session.latest_frame is not None else last_frame
            if frame:
                last_frame = frame if session.latest_frame is not None else last_frame
                yield boundary
                yield b"Content-Type: image/jpeg\r\n"
                yield f"Content-Length: {len(frame)}\r\n".encode()
                yield b"\r\n"
                yield frame
                yield b"\r\n"

            await asyncio.sleep(0.05)  # 20 FPS 硬心跳

    return StreamingResponse(
        frame_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@router.get("/plate/stream/{session_id}/frame")
async def stream_frame(session_id: str):
    """获取最新单帧 (备用)"""
    session = await session_manager.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    if session.latest_frame is None:
        raise HTTPException(status_code=204, detail="尚无帧数据")
    return Response(content=session.latest_frame, media_type="image/jpeg",
                    headers={"Cache-Control": "no-cache"})
