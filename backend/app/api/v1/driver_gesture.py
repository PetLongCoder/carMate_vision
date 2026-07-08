from fastapi import APIRouter, UploadFile, File, HTTPException
from app.services.hand_tracker import HandTracker
from app.models.schemas import DriverGestureResult, ControlAction
from app.utils.logger import logger

router = APIRouter()

tracker = HandTracker()

GESTURE_MAP = {
    "fist": {"id": 0, "name": "握拳"},
    "open_palm": {"id": 1, "name": "手掌张开"},
    "thumb_up": {"id": 2, "name": "拇指向上"},
    "thumb_down": {"id": 3, "name": "拇指向下"},
    "swipe_left": {"id": 4, "name": "向左滑动"},
    "swipe_right": {"id": 5, "name": "向右滑动"},
    "circle": {"id": 6, "name": "画圈"},
    "no_hand": {"id": -1, "name": "未检测到手"},
    "unknown": {"id": -2, "name": "未知手势"}
}

# 按照你的要求重新映射
ACTION_MAP = {
    "fist": ControlAction(type="play_pause", label="播放/暂停"),
    "thumb_up": ControlAction(type="volume_up", label="音量调高"),
    "thumb_down": ControlAction(type="volume_down", label="音量调低"),
    "swipe_left": ControlAction(type="prev_track", label="上一首"),
    "swipe_right": ControlAction(type="next_track", label="下一首"),
    "open_palm": ControlAction(type="temperature_up", label="温度调高"),
    "circle": ControlAction(type="temperature_down", label="温度调低"),
}

@router.post("/driver-gesture/recognize")
async def recognize_driver_gesture(file: UploadFile = File(...)):
    logger.info(f"收到车主手势识别请求: {file.filename}")
    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="上传的文件为空")

    gesture_key, confidence, landmarks = tracker.process_frame(image_bytes)

    gesture_info = GESTURE_MAP.get(gesture_key, GESTURE_MAP["unknown"])
    gesture_name = gesture_info["name"]
    gesture_id = gesture_info["id"]

    control_action = ACTION_MAP.get(gesture_key)

    if confidence < 0.2:
        gesture_name = "未知手势"
        gesture_id = -2
        control_action = None

    result = DriverGestureResult(
        gesture=gesture_name,
        gestureId=gesture_id,
        confidence=round(confidence, 4),
        controlAction=control_action
    )

    return {
        "code": 200,
        "message": "success",
        "data": result.dict()
    }

@router.post("/driver-gesture/reset")
async def reset_gesture_tracker():
    tracker.reset_state()
    logger.info("手势追踪器状态已重置")
    return {"code": 200, "message": "reset success", "data": None}