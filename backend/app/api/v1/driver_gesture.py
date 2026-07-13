from fastapi import APIRouter, UploadFile, File, HTTPException, Request, Depends
from sqlalchemy.orm import Session
import time

from app.api.v1.auth import get_current_user
from app.core.database import get_db
from app.models.db_models import User
from app.models.schemas import DriverGestureResult, ControlAction
from app.services.record_service import build_gesture_summary, log_recognition
from app.services.alert_agent.event_collector import event_collector
from app.services.alert_agent import AnomalyEvent, AlertLevel
from app.utils.logger import logger

router = APIRouter()

_tracker = None

# ==========================================
# 操作片段状态
# ==========================================
_current_gesture_key = None      # 当前正在持续的手势 key
_current_start_time = 0          # 当前手势开始时间
_current_count = 0               # 连续触发次数（仅对画圈/拇指有效）
_last_play_state = None          # 上一次播放状态 (True=播放, False=暂停)

# 需要计次的手势（画圈和拇指）
COUNT_GESTURES = {"rotate_cw", "rotate_ccw", "thumb_up", "thumb_down"}

GESTURE_MAP = {
    "fist": {"id": 0, "name": "握拳"},
    "open_palm": {"id": 1, "name": "手掌张开"},
    "thumb_up": {"id": 2, "name": "拇指向上"},
    "thumb_down": {"id": 3, "name": "拇指向下"},
    "swipe_left": {"id": 4, "name": "向左滑动"},
    "swipe_right": {"id": 5, "name": "向右滑动"},
    "rotate_cw": {"id": 6, "name": "顺时针画圈"},
    "rotate_ccw": {"id": 7, "name": "逆时针画圈"},
    "no_hand": {"id": -1, "name": "未检测到手"},
    "unknown": {"id": -2, "name": "未知手势"},
}

ACTION_MAP = {
    "open_palm": ControlAction(type="play_pause", label="播放"),
    "fist": ControlAction(type="play_pause", label="暂停"),
    "thumb_up": ControlAction(type="volume_up", label="音量调高"),
    "thumb_down": ControlAction(type="volume_down", label="音量调低"),
    "swipe_left": ControlAction(type="prev_track", label="上一首"),
    "swipe_right": ControlAction(type="next_track", label="下一首"),
    "rotate_cw": ControlAction(type="temperature_up", label="温度调高"),
    "rotate_ccw": ControlAction(type="temperature_down", label="温度调低"),
}

def _get_tracker():
    global _tracker
    if _tracker is None:
        try:
            from app.services.lstm_tracker import LSTMGestureTracker
            _tracker = LSTMGestureTracker()
        except Exception as exc:
            logger.error(f"车主手势模型加载失败: {exc}")
            event_collector.collect(AnomalyEvent(
                source="driver_gesture",
                anomaly_type="driver_gesture_model_failure",
                title="车主手势模型加载失败",
                detail={"error": str(exc)},
                severity_hint=AlertLevel.CRITICAL,
            ))
            raise HTTPException(status_code=503, detail="车主手势识别模块未就绪，请稍后重试") from exc
    return _tracker

def _log_gesture_segment(db, gesture_key, gesture_name, gesture_id, confidence, duration, count, file_name, user):
    """记录一个完整的手势操作片段（只记录有效手势，忽略unknown/no_hand）"""
    if gesture_key in ["unknown", "no_hand"]:
        return

    summary = gesture_name
    if duration > 0 and gesture_key in COUNT_GESTURES:
        summary += f" (持续{duration:.1f}秒)"
    if count > 1 and gesture_key in COUNT_GESTURES:
        summary += f"，{count}次"

    result_data = {
        "gesture": gesture_name,
        "gesture_id": gesture_id,
        "confidence": confidence,
        "sourceType": "image",
        "fileName": file_name,
    }
    if gesture_key in COUNT_GESTURES:
        result_data["duration"] = round(duration, 1)
        result_data["count"] = count

    from app.services.record_service import log_recognition as log_rec
    log_rec(
        db,
        record_type="driver_gesture",
        source_type="image",
        success=True,
        summary=summary,
        result=result_data,
        file_name=file_name,
        user=user,
    )

def _log_play_state_change(db, new_state, file_name, user):
    """记录播放/暂停状态变化"""
    state_name = "播放" if new_state else "暂停"
    result_data = {
        "gesture": state_name,
        "gesture_id": -3,
        "confidence": 1.0,
        "sourceType": "image",
        "fileName": file_name,
    }
    from app.services.record_service import log_recognition as log_rec
    log_rec(
        db,
        record_type="driver_gesture",
        source_type="image",
        success=True,
        summary=f"播放状态 → {state_name}",
        result=result_data,
        file_name=file_name,
        user=user,
    )

@router.post("/driver-gesture/recognize")
async def recognize_driver_gesture(
    file: UploadFile = File(...),
    request: Request = None,
    user: User | None = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    global _current_gesture_key, _current_start_time, _current_count, _last_play_state

    logger.info(f"收到车主手势识别请求: {file.filename}")
    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="上传的文件为空")

    gesture_key, confidence, landmarks = _get_tracker().process_frame(image_bytes)

    gesture_info = GESTURE_MAP.get(gesture_key, GESTURE_MAP["unknown"])
    gesture_name = gesture_info["name"]
    gesture_id = gesture_info["id"]

    control_action = ACTION_MAP.get(gesture_key)

    if confidence < 0.2:
        gesture_name = "未知手势"
        gesture_id = -2
        control_action = None
        event_collector.collect(AnomalyEvent(
            source="driver_gesture",
            anomaly_type="driver_gesture_low_confidence",
            title="车主手势置信度偏低",
            detail={"gesture_key": gesture_key, "confidence": round(confidence, 4)},
        ))

    result = DriverGestureResult(
        gesture=gesture_name,
        gestureId=gesture_id,
        confidence=round(confidence, 4),
        controlAction=control_action,
    )

    current_time = time.time()

    # ----------------------------------------------------------
    # 1. 处理播放/暂停状态变化（单独记录）
    # ----------------------------------------------------------
    if control_action and control_action.type == "play_pause":
        new_play_state = (gesture_key == "open_palm")
        if _last_play_state != new_play_state:
            _last_play_state = new_play_state
            _log_play_state_change(db, new_play_state, file.filename, user)
            _current_gesture_key = None
            _current_start_time = 0
            _current_count = 0

    # ----------------------------------------------------------
    # 2. 处理其他手势（操作片段逻辑）
    # ----------------------------------------------------------
    else:
        if gesture_key in ["unknown", "no_hand"]:
            if _current_gesture_key and _current_gesture_key not in ["unknown", "no_hand"]:
                duration = current_time - _current_start_time
                if duration >= 0.5:
                    _log_gesture_segment(
                        db,
                        _current_gesture_key,
                        GESTURE_MAP.get(_current_gesture_key, {}).get("name", "未知"),
                        GESTURE_MAP.get(_current_gesture_key, {}).get("id", -1),
                        0.8,
                        duration,
                        _current_count,
                        file.filename,
                        user,
                    )
                _current_gesture_key = None
                _current_start_time = 0
                _current_count = 0
        else:
            if _current_gesture_key is None:
                _current_gesture_key = gesture_key
                _current_start_time = current_time
                _current_count = 1
            elif gesture_key == _current_gesture_key:
                if gesture_key in COUNT_GESTURES:
                    _current_count += 1
            else:
                if _current_gesture_key not in ["unknown", "no_hand"]:
                    duration = current_time - _current_start_time
                    if duration >= 0.5:
                        _log_gesture_segment(
                            db,
                            _current_gesture_key,
                            GESTURE_MAP.get(_current_gesture_key, {}).get("name", "未知"),
                            GESTURE_MAP.get(_current_gesture_key, {}).get("id", -1),
                            0.8,
                            duration,
                            _current_count,
                            file.filename,
                            user,
                        )
                _current_gesture_key = gesture_key
                _current_start_time = current_time
                _current_count = 1

    return {
        "code": 200,
        "message": "success",
        "data": {
            **result.dict(),
            "landmarks": landmarks,
        }
    }

@router.post("/driver-gesture/reset")
async def reset_gesture_tracker():
    global _current_gesture_key, _current_start_time, _current_count, _last_play_state
    _get_tracker().reset_state()
    _current_gesture_key = None
    _current_start_time = 0
    _current_count = 0
    _last_play_state = None
    logger.info("手势追踪器状态已重置")
    return {"code": 200, "message": "reset success", "data": None}