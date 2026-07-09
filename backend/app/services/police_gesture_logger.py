"""
交警手势识别 — 云数据库日志服务
================================

将每次交警手势识别请求的结果写入云数据库 (TencentDB MySQL),
使用独立线程池异步写入, 不阻塞推理主流程。
"""

import json
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Optional

from app.core.database import SessionLocal
from app.models.db_models import PoliceGestureLog
from app.utils.logger import logger

# 单线程池: 保证写入顺序, 避免数据库连接池耗尽
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="gesture-log")


@dataclass
class GestureLogEntry:
    """单次手势识别日志条目"""

    recognition_type: str  # image / video / video_stream / camera_stream
    gesture: str
    gesture_id: int
    confidence: float
    inference_ms: float
    success: bool = True
    filename: Optional[str] = None
    video_session_id: Optional[str] = None  # 同一视频的 UUID
    top5_json: Optional[str] = None
    frames_total: Optional[int] = None
    frames_processed: Optional[int] = None
    video_fps: Optional[float] = None
    video_duration: Optional[float] = None
    segments_json: Optional[str] = None
    error_message: Optional[str] = None
    client_info: Optional[str] = None
    timestamp: int = field(default_factory=lambda: int(time.time() * 1000))


def _write_log(entry: GestureLogEntry) -> None:
    """同步写入一条日志到数据库 (在后台线程中调用)"""
    db = SessionLocal()
    try:
        log_record = PoliceGestureLog(
            recognition_type=entry.recognition_type,
            gesture=entry.gesture,
            gesture_id=entry.gesture_id,
            confidence=entry.confidence,
            inference_ms=entry.inference_ms,
            success=entry.success,
            filename=entry.filename,
            video_session_id=entry.video_session_id,
            top5_json=entry.top5_json,
            frames_total=entry.frames_total,
            frames_processed=entry.frames_processed,
            video_fps=entry.video_fps,
            video_duration=entry.video_duration,
            segments_json=entry.segments_json,
            error_message=entry.error_message,
            client_info=entry.client_info,
        )
        db.add(log_record)
        db.commit()
        logger.debug(
            "手势日志已写入云数据库: id=%d, type=%s, gesture=%s, confidence=%.2f%%",
            log_record.id,
            entry.recognition_type,
            entry.gesture,
            entry.confidence * 100,
        )
    except Exception as exc:
        db.rollback()
        logger.warning("手势日志写入云数据库失败 (非致命): %s", exc)
    finally:
        db.close()


def log_gesture_async(entry: GestureLogEntry) -> None:
    """异步提交日志写入任务 (不阻塞调用方)"""
    try:
        _executor.submit(_write_log, entry)
    except Exception as exc:
        logger.warning("提交手势日志任务失败 (非致命): %s", exc)


def log_gestures_batch_async(entries: list[GestureLogEntry]) -> None:
    """异步批量提交日志写入任务 (同一个事务中写入)"""
    if not entries:
        return

    def _write_batch():
        db = SessionLocal()
        try:
            records = [
                PoliceGestureLog(
                    recognition_type=e.recognition_type,
                    gesture=e.gesture,
                    gesture_id=e.gesture_id,
                    confidence=e.confidence,
                    inference_ms=e.inference_ms,
                    success=e.success,
                    filename=e.filename,
                    video_session_id=e.video_session_id,
                    top5_json=e.top5_json,
                    frames_total=e.frames_total,
                    frames_processed=e.frames_processed,
                    video_fps=e.video_fps,
                    video_duration=e.video_duration,
                    segments_json=e.segments_json,
                    error_message=e.error_message,
                    client_info=e.client_info,
                )
                for e in entries
            ]
            db.add_all(records)
            db.commit()
            logger.debug(
                "批量手势日志已写入云数据库: %d 条, type=%s",
                len(records),
                entries[0].recognition_type,
            )
        except Exception as exc:
            db.rollback()
            logger.warning("批量手势日志写入云数据库失败 (非致命): %s", exc)
        finally:
            db.close()

    try:
        _executor.submit(_write_batch)
    except Exception as exc:
        logger.warning("提交批量手势日志任务失败 (非致命): %s", exc)


def log_gesture_sync(entry: GestureLogEntry) -> None:
    """同步写入日志 (用于需要立即确认的场景)"""
    _write_log(entry)


# ---- 辅助构建函数 ----

def build_top5_json(top5_list: list[dict]) -> str:
    """将 top5 列表序列化为 JSON 字符串"""
    try:
        return json.dumps(top5_list, ensure_ascii=False)
    except Exception:
        return "[]"


def build_segments_json(segments: list[dict]) -> str:
    """将手势段列表序列化为 JSON 字符串"""
    try:
        return json.dumps(segments, ensure_ascii=False)
    except Exception:
        return "[]"
