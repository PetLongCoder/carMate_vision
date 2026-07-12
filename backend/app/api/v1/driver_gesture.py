from fastapi import APIRouter, UploadFile, File, HTTPException, Request, Depends
from sqlalchemy.orm import Session

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

GESTURE_MAP = {
    "fist": {"id": 0, "name": "握拳"},
    "open_palm": {"id": 1, "name": "手掌张开"},
    "thumb_up": {"id": 2, "name": "拇指向上"},
    "thumb_down": {"id": 3, "name": "拇指向下"},
    "swipe_left": {"id": 4, "name": "向左滑动"},
    "swipe_right": {"id": 5, "name": "向右滑动"},
    "rotate_cw": {"id": 6, "name": "画圈"},
    "rotate_ccw": {"id": 6, "name": "画圈"},
    "circle": {"id": 6, "name": "画圈"},
    "no_hand": {"id": -1, "name": "未检测到手"},
    "unknown": {"id": -2, "name": "未知手势"},
}

ACTION_MAP = {
    "fist": ControlAction(type="play_pause", label="播放/暂停"),
    "thumb_up": ControlAction(type="volume_up", label="音量调高"),
    "thumb_down": ControlAction(type="volume_down", label="音量调低"),
    "swipe_left": ControlAction(type="prev_track", label="上一首"),
    "swipe_right": ControlAction(type="next_track", label="下一首"),
    "open_palm": ControlAction(type="temperature_up", label="温度调高"),
    "rotate_cw": ControlAction(type="temperature_down", label="温度调低"),
    "rotate_ccw": ControlAction(type="temperature_down", label="温度调低"),
    "circle": ControlAction(type="temperature_down", label="温度调低"),
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

@router.post("/driver-gesture/recognize")
async def recognize_driver_gesture(
    file: UploadFile = File(...),
    request: Request = None,
    user: User | None = Depends(get_current_user),
    db: Session = Depends(get_db),
):
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

    result_dict = result.dict()
    log_recognition(
        db,
        record_type="driver_gesture",
        source_type="image",
        success=gesture_id >= 0 and confidence >= 0.2,
        summary=build_gesture_summary(result_dict),
        result=result_dict,
        file_name=file.filename,
        user=user,
    )

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
    _get_tracker().reset_state()
    logger.info("手势追踪器状态已重置")
    return {"code": 200, "message": "reset success", "data": None}