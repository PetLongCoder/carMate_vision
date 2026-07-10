"""
视频/流媒体后台处理任务
========================
"""
import asyncio
import time
from typing import Optional

import cv2
import numpy as np

from app.services.plate_tracker import VideoStreamProcessor
from app.services.session_manager import (
    SessionStatus,
    TrackingSession,
    SessionType,
    session_manager,
)
from app.utils.logger import logger


async def run_video_session(
    session: TrackingSession,
):
    cap: Optional[cv2.VideoCapture] = None

    try:
        session.update_status(SessionStatus.PROCESSING)

        if session.type == SessionType.STREAM:
            await _run_stream_loop(session)
        else:
            processor = VideoStreamProcessor(process_every_n_frames=1)
            session.processor = processor
            cap = cv2.VideoCapture(session.source)
            if not cap.isOpened():
                raise RuntimeError(f"无法打开视频: {session.source}")
            total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            session.total_frames = total
            session.fps = fps
            await _run_event_loop(session, cap, processor, total, fps)

        summary = _build_tracking_summary(session)
        await session.broadcast(summary)

        # 保存最终追踪结果到历史记录
        _save_tracking_summary_to_db(session, summary)

    except Exception as exc:
        logger.exception(f"会话 {session.session_id} 异常: {exc}")
        session.update_status(SessionStatus.ERROR, str(exc))
        try:
            await session.broadcast({"type": "error", "sessionId": session.session_id, "message": str(exc)})
        except Exception:
            pass
    finally:
        if cap is not None:
            cap.release()
        await _delayed_cleanup(session.session_id)


async def _open_capture(source: str) -> Optional[cv2.VideoCapture]:
    try:
        cap = await asyncio.to_thread(cv2.VideoCapture, source, cv2.CAP_FFMPEG)
    except Exception:
        return None
    if cap and cap.isOpened():
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return cap
    if cap:
        cap.release()
    return None


async def _run_detection(
    session: TrackingSession,
    processor: VideoStreamProcessor,
    frame: np.ndarray,
    fps: float,
    frame_idx: int,
):
    """在后台线程中执行检测，完成后广播结果。不阻塞主循环。"""
    try:
        results, annotated = await asyncio.to_thread(processor.process_frame, frame, fps)
    except Exception as exc:
        logger.warning(f"检测帧 {frame_idx} 异常: {exc}")
        return

    if results:
        ts = frame_idx / fps if fps > 0 else 0
        await session.broadcast({
            "type": "detection", "sessionId": session.session_id,
            "frameNumber": frame_idx, "timestamp": round(ts, 3),
            "fps": fps, "detections": results,
        })

    # 检测完成后推一帧标注画面到 MJPEG（覆盖原始帧）
    if annotated is not None and annotated.size > 0:
        ok, jpeg = cv2.imencode('.jpg', annotated, [cv2.IMWRITE_JPEG_QUALITY, 75])
        if ok:
            await session.set_frame(jpeg.tobytes())


async def _run_stream_loop(
    session: TrackingSession,
):
    """
    流媒体循环 — 读帧与检测完全分离

    主循环: 读取 RTSP → 编码 JPEG → 推送 MJPEG（满帧率不阻塞）
    检测:    每 N 帧 fire-and-forget 启动检测任务，检测完成后覆盖 MJPEG
    """
    logger.info(f"流会话 {session.session_id} 开始")
    cap = None
    processor = VideoStreamProcessor(process_every_n_frames=3)
    session.processor = processor
    frame_idx = 0
    detect_interval = 6  # 每 6 帧检测一次
    fps = 25.0

    # 打开 VideoCapture
    cap = await _open_capture(session.source)
    if cap is None:
        await asyncio.sleep(2)
        cap = await _open_capture(session.source)
        if cap is None:
            raise RuntimeError(f"无法连接到视频源: {session.source}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    session.fps = fps
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 1280
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 720
    logger.info(f"流 {session.session_id} 已连接: {width}x{height} @ {fps:.1f} fps")

    while True:
        try:
            ret, frame = cap.read()
        except Exception:
            ret = False
            frame = None

        if not ret:
            logger.warning("读帧失败，重连中...")
            try:
                cap.release()
            except Exception:
                pass
            await asyncio.sleep(1)
            cap = await _open_capture(session.source)
            if cap:
                continue
            continue

        session.processed_frames += 1

        # 每 N 帧 fire-and-forget 检测（不阻塞主循环）
        if frame_idx % detect_interval == 0:
            asyncio.create_task(_run_detection(
                session, processor, frame.copy(), fps, frame_idx
            ))

        # 每帧推 MJPEG（原始帧，满帧率流畅）
        ok, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
        if ok:
            await session.set_frame(jpeg.tobytes())

        frame_idx += 1
        if frame_idx % 50 == 0:
            await session.broadcast({
                "type": "status", "sessionId": session.session_id,
                "status": "processing", "progress": 0,
                "framesProcessed": frame_idx, "totalFrames": 0,
            })
        if session.status == SessionStatus.STOPPED:
            break
        await asyncio.sleep(0)

    if session.status != SessionStatus.STOPPED:
        session.update_status(SessionStatus.COMPLETED)


async def _run_event_loop(
    session: TrackingSession,
    cap: cv2.VideoCapture,
    processor: VideoStreamProcessor,
    total: int,
    fps: float,
):
    logger.info(f"会话 {session.session_id} 进入播放驱动模式")
    cache: dict[int, list[dict]] = {}
    last_sync_time = time.time()

    while True:
        if session.status == SessionStatus.STOPPED:
            break
        # 60 秒无同步信号则自动停止（用户已离开）
        if time.time() - last_sync_time > 60:
            logger.info(f"会话 {session.session_id}: 60秒无操作, 自动停止")
            session.update_status(SessionStatus.STOPPED, "超时无操作")
            break
        wait_ms = 0.001
        try:
            await asyncio.wait_for(session._sync_event.wait(), timeout=wait_ms)
            session._sync_event.clear()
        except asyncio.TimeoutError:
            continue
        sync_data = session._latest_sync
        if sync_data is None:
            continue
        last_sync_time = time.time()
        _, target_time = sync_data
        target_frame = int(target_time * fps)
        aligned = (target_frame // 1) * 1
        if aligned < 0 or aligned >= total:
            continue
        if aligned in cache:
            ts = aligned / fps
            await session.broadcast({
                "type": "detection", "sessionId": session.session_id,
                "frameNumber": aligned, "timestamp": round(ts, 3),
                "fps": fps, "detections": cache[aligned], "cached": True,
            })
            continue
        cap.set(cv2.CAP_PROP_POS_FRAMES, aligned)
        ret, frame = cap.read()
        if not ret:
            continue
        t0 = time.time()
        results, _ = processor.process_frame(frame, fps)
        ts = aligned / fps
        session.processed_frames += 1
        cache[aligned] = results if results else []
        await session.broadcast({
            "type": "detection", "sessionId": session.session_id,
            "frameNumber": aligned, "timestamp": round(ts, 3),
            "fps": fps, "detections": results if results else [],
            "processingMs": round((time.time() - t0) * 1000, 1), "cached": False,
        })
    if session.status != SessionStatus.STOPPED:
        session.update_status(SessionStatus.COMPLETED)


def _build_tracking_summary(session: TrackingSession) -> dict:
    plates = []
    try:
        if session.processor and hasattr(session.processor, 'tracker'):
            plates = session.processor.tracker.get_summary()
    except Exception:
        pass
    return {
        "type": "summary", "sessionId": session.session_id,
        "totalFrames": session.total_frames, "processedFrames": session.processed_frames,
        "duration": round(session.processed_frames / session.fps, 2) if session.fps > 0 else 0,
        "plates": plates,
    }


def _save_tracking_summary_to_db(session: TrackingSession, summary: dict) -> None:
    """追踪/流完成后，将最终车牌结果保存到历史记录。"""
    from app.core.database import SessionLocal
    from app.services.record_service import build_plate_summary, update_recognition_by_session

    plates = summary.get("plates", [])
    db = SessionLocal()
    try:
        if plates:
            plate_summary = build_plate_summary(plates)
            update_recognition_by_session(
                db,
                session_id=session.session_id,
                final_result={
                    "plates": plates,
                    "totalFrames": summary.get("totalFrames", 0),
                    "processedFrames": summary.get("processedFrames", 0),
                    "duration": summary.get("duration", 0),
                    "sourceType": "stream" if session.type == SessionType.STREAM else "track",
                },
                success=True,
                summary=plate_summary,
            )
            logger.info(f"追踪结果已保存到历史记录 [{session.session_id}]: {plate_summary}")
    except Exception as exc:
        logger.warning(f"保存追踪结果到历史记录失败 [{session.session_id}]: {exc}")
        db.rollback()
    finally:
        db.close()


async def _delayed_cleanup(session_id: str, delay: int = 60):
    await asyncio.sleep(delay)
    await session_manager.remove_session(session_id)
