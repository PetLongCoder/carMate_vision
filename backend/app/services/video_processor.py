"""
视频/流媒体后台处理任务
========================

与 session_manager 配合, 负责真正的帧采集 → 检测 → 追踪 → 广播循环。
被 main.py (WebSocket) 和 plate.py (REST API) 共同调用。
"""
import asyncio
import time
from typing import Optional

import cv2

from app.services.plate_tracker import VideoStreamProcessor
from app.services.session_manager import (
    SessionStatus,
    TrackingSession,
    SessionType,
    session_manager,
)
from app.utils.logger import logger


async def run_video_session(session: TrackingSession):
    """
    后台任务: 处理视频文件或流 URL

    逐帧读取 → 检测 → 追踪 → 广播结果到 WebSocket
    """
    cap: Optional[cv2.VideoCapture] = None
    processor = VideoStreamProcessor(process_every_n_frames=3)

    try:
        session.update_status(SessionStatus.PROCESSING)
        session.processor = processor  # 让会话持有处理器, 方便取汇总

        cap = cv2.VideoCapture(session.source)
        if not cap.isOpened():
            raise RuntimeError(f"无法打开视频源: {session.source}")

        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        if total > 0:
            session.total_frames = total
        session.fps = fps

        frame_idx = 0
        start_time = time.time()
        all_results: list[dict] = []  # 累积所有帧的检测结果

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            results, annotated = processor.process_frame(frame, fps)
            timestamp = frame_idx / fps if fps > 0 else 0
            session.processed_frames += 1

            # 流模式: 保存标注帧给 MJPEG 流
            if session.type == SessionType.STREAM and annotated is not None:
                _, jpeg = cv2.imencode('.jpg', annotated, [cv2.IMWRITE_JPEG_QUALITY, 75])
                await session.set_frame(jpeg.tobytes())

            # 始终推送检测结果 (含空结果), 让前端感知流存活
            all_results.append({
                "frameNumber": frame_idx,
                "timestamp": round(timestamp, 3),
                "detections": results if results else [],
            })
            await session.broadcast({
                "type": "detection",
                "sessionId": session.session_id,
                "frameNumber": frame_idx,
                "timestamp": round(timestamp, 3),
                "fps": fps,
                "detections": results if results else [],
                "processingMs": round((time.time() - start_time) * 1000, 1),
            })

            # 定期推送进度
            if frame_idx % 15 == 0:
                await session.broadcast({
                    "type": "status",
                    "sessionId": session.session_id,
                    "status": SessionStatus.PROCESSING.value,
                    "progress": round(frame_idx / total, 4) if total > 0 else 0,
                    "framesProcessed": frame_idx,
                    "totalFrames": total,
                })

            frame_idx += 1

            # 流模式: 检查是否被停止
            if session.type == SessionType.STREAM and session.status == SessionStatus.STOPPED:
                logger.info(f"流会话 {session.session_id} 已被手动停止")
                break

            # 让出事件循环
            if frame_idx % 5 == 0:
                await asyncio.sleep(0)

        elapsed = time.time() - start_time
        logger.info(
            f"会话 {session.session_id} 处理完成: "
            f"{frame_idx} 帧, {elapsed:.1f}s"
        )

        if session.status != SessionStatus.STOPPED:
            session.update_status(SessionStatus.COMPLETED)

        # 广播汇总
        summary = _build_tracking_summary(session, all_results)
        await session.broadcast(summary)

    except Exception as exc:
        logger.exception(f"会话 {session.session_id} 处理异常: {exc}")
        session.update_status(SessionStatus.ERROR, str(exc))
        try:
            await session.broadcast({
                "type": "error",
                "sessionId": session.session_id,
                "message": str(exc),
            })
        except Exception:
            pass
    finally:
        if cap is not None:
            cap.release()
        # 延时清理, 让 WebSocket 收完最后的消息
        await _delayed_cleanup(session.session_id)


def _build_tracking_summary(session: TrackingSession,
                             all_results: list[dict]) -> dict:
    """构造追踪汇总消息"""
    # 从 processor 的 tracker 中获取稳定追踪
    plates = []
    try:
        if session.processor is not None:
            tracker = session.processor.tracker
            plates = tracker.get_summary()
    except Exception as exc:
        logger.warning(f"获取追踪汇总异常: {exc}")

    return {
        "type": "summary",
        "sessionId": session.session_id,
        "totalFrames": session.total_frames,
        "processedFrames": session.processed_frames,
        "duration": round(session.processed_frames / session.fps, 2)
                     if session.fps > 0 else 0,
        "plates": plates,
    }


async def _delayed_cleanup(session_id: str, delay: int = 60):
    """延时清理会话"""
    await asyncio.sleep(delay)
    await session_manager.remove_session(session_id)
