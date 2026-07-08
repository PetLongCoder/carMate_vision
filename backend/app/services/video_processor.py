"""
视频/流媒体后台处理任务
========================

与 session_manager 配合, 负责帧采集 → 检测 → 追踪 → 广播。

视频文件模式 (VIDEO):
  由前端播放事件驱动: play/sync/seek → 处理对应帧 → 推结果 → 等待下一指令。
  不播放则不处理任何帧，零负载。

流媒体模式 (STREAM):
  保持连续处理循环（直播流需要持续跟上）。
"""
import asyncio
import json
import time
from typing import Optional
import math

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

    根据 session.type 分两种模式运行。
    """
    cap: Optional[cv2.VideoCapture] = None
    processor = VideoStreamProcessor(process_every_n_frames=1)
    processed_cache: dict[int, list[dict]] = {}  # aligned_frame → results

    try:
        session.update_status(SessionStatus.PROCESSING)
        session.processor = processor

        cap = cv2.VideoCapture(session.source)
        if not cap.isOpened():
            raise RuntimeError(f"无法打开视频源: {session.source}")

        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        if total > 0:
            session.total_frames = total
        session.fps = fps

        all_results: list[dict] = []
        last_processed_frame: int = -1

        if session.type == SessionType.STREAM:
            await _run_stream_loop(session, cap, processor, total, fps)
        else:
            await _run_event_loop(
                session, cap, processor, total, fps, processed_cache,
                all_results,
            )

        elapsed = 0
        # 构建汇总
        summary = _build_tracking_summary(session)
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
        await _delayed_cleanup(session.session_id)


async def _run_event_loop(
    session: TrackingSession,
    cap: cv2.VideoCapture,
    processor: VideoStreamProcessor,
    total: int,
    fps: float,
    cache: dict[int, list[dict]],
    all_results: list[dict],
):
    """
    播放驱动的连续处理循环 — 用于视频文件 (VIDEO)

    播放时持续向前处理帧，暂停时停止。
    ─ play/sync → 开始从当前位置连续向前处理
    ─ pause/stop → 停止处理，零负载
    ─ seek → 跳到新位置继续处理
    """
    logger.info(f"会话 {session.session_id} 进入播放驱动模式")
    process_interval = processor.process_every_n_frames
    start_time = time.time()
    next_frame: int = -1

    while True:
        if session.status == SessionStatus.STOPPED:
            break

        # ── 等待事件 (播放时仅等1ms用于检查事件, 暂停时5s心跳) ──
        wait_ms = 0.001 if next_frame >= 0 else 5.0
        try:
            await asyncio.wait_for(session._sync_event.wait(), timeout=wait_ms)
            session._sync_event.clear()
        except asyncio.TimeoutError:
            if next_frame >= 0:
                pass  # 继续处理下一帧
            else:
                continue  # 没有 sync 事件，继续等待

        # ── 检查最新 sync ──
        sync_data = session._latest_sync
        if sync_data is not None:
            _, target_time = sync_data
            target_frame = int(target_time * fps)
            aligned = (target_frame // process_interval) * process_interval

            # 始终对齐到 sync 报告的播放位置
            # 这样不管处理快慢，始终紧贴当前画面
            next_frame = aligned
        else:
            # pause → 停止处理
            next_frame = -1
            continue

        # ── 检查范围 ──
        if next_frame < 0 or next_frame >= total:
            next_frame = -1
            continue

        # ── 缓存命中 ──
        if next_frame in cache:
            cached = cache[next_frame]
            ts = next_frame / fps
            await session.broadcast({
                "type": "detection",
                "sessionId": session.session_id,
                "frameNumber": next_frame,
                "timestamp": round(ts, 3),
                "fps": fps,
                "detections": cached,
                "cached": True,
            })
            next_frame += process_interval
            await asyncio.sleep(0)
            continue

        # ── seek + 处理 ──
        cap.set(cv2.CAP_PROP_POS_FRAMES, next_frame)
        ret, frame = cap.read()
        if not ret:
            next_frame = -1
            continue

        t0 = time.time()
        results, annotated = processor.process_frame(frame, fps)
        elapsed = time.time() - t0
        ts = next_frame / fps
        session.processed_frames += 1

        results_list = results if results else []
        cache[next_frame] = results_list
        all_results.append({
            "frameNumber": next_frame,
            "timestamp": round(ts, 3),
            "detections": results_list,
        })

        await session.broadcast({
            "type": "detection",
            "sessionId": session.session_id,
            "frameNumber": next_frame,
            "timestamp": round(ts, 3),
            "fps": fps,
            "detections": results_list,
            "processingMs": round(elapsed * 1000, 1),
            "cached": False,
        })

        # 前进到下一帧
        next_frame += process_interval

        # 定期广播进度
        if session.processed_frames % 10 == 0:
            total_frames_est = total if total > 0 else 0
            await session.broadcast({
                "type": "status",
                "sessionId": session.session_id,
                "status": "processing",
                "progress": round(min(next_frame / max(total_frames_est, 1), 1.0), 4),
                "framesProcessed": session.processed_frames * process_interval,
                "totalFrames": total_frames_est,
            })

        await asyncio.sleep(0)

    # 循环结束
    if session.status != SessionStatus.STOPPED:
        session.update_status(SessionStatus.COMPLETED)


async def _run_stream_loop(
    session: TrackingSession,
    cap: cv2.VideoCapture,
    processor: VideoStreamProcessor,
    total: int,
    fps: float,
):
    """
    连续处理循环 — 用于流媒体 (STREAM)

    保持逐帧读取处理，与原始行为一致。
    """
    logger.info(f"会话 {session.session_id} 进入流媒体连续处理模式")
    frame_idx = 0
    start_time = time.time()

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        results, annotated = processor.process_frame(frame, fps)
        timestamp = frame_idx / fps if fps > 0 else 0
        session.processed_frames += 1

        # 保存标注帧给 MJPEG 流
        if annotated is not None:
            _, jpeg = cv2.imencode('.jpg', annotated, [cv2.IMWRITE_JPEG_QUALITY, 75])
            await session.set_frame(jpeg.tobytes())

        await session.broadcast({
            "type": "detection",
            "sessionId": session.session_id,
            "frameNumber": frame_idx,
            "timestamp": round(timestamp, 3),
            "fps": fps,
            "detections": results if results else [],
            "processingMs": round((time.time() - start_time) * 1000, 1),
        })

        if frame_idx % 15 == 0:
            await session.broadcast({
                "type": "status",
                "sessionId": session.session_id,
                "status": "processing",
                "progress": 0,
                "framesProcessed": frame_idx,
                "totalFrames": 0,
            })

        frame_idx += 1

        # 检查停止
        if session.status == SessionStatus.STOPPED:
            logger.info(f"流会话 {session.session_id} 已被手动停止")
            break

        if frame_idx % 5 == 0:
            await asyncio.sleep(0)

    elapsed = time.time() - start_time
    logger.info(f"流会话 {session.session_id} 处理完成: {frame_idx} 帧, {elapsed:.1f}s")

    if session.status != SessionStatus.STOPPED:
        session.update_status(SessionStatus.COMPLETED)


def _build_tracking_summary(session: TrackingSession) -> dict:
    """构造追踪汇总消息"""
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
