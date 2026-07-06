from fastapi import APIRouter, UploadFile, File, HTTPException
from app.services.hand_tracker import HandTracker
from app.models.schemas import DriverGestureResult, ControlAction
from app.utils.logger import logger

router = APIRouter()

# 全局初始化手部追踪器（模型只加载一次）
tracker = HandTracker()

# 手势键 → 中文名称 & ID 映射
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

# 手势 → 车辆控制动作映射（可根据需要调整）
ACTION_MAP = {
    "fist": ControlAction(type="play_pause", label="播放/暂停"),
    "open_palm": ControlAction(type="volume_up", label="音量调高"),
    "thumb_up": ControlAction(type="next_track", label="下一首"),
    "thumb_down": ControlAction(type="prev_track", label="上一首"),
    "swipe_left": ControlAction(type="volume_down", label="音量调低"),
    "swipe_right": ControlAction(type="temperature_up", label="温度调高"),
    "circle": ControlAction(type="temperature_down", label="温度调低"),
}


@router.post("/driver-gesture/recognize")
async def recognize_driver_gesture(file: UploadFile = File(...)):
    """
    车主手势识别接口
    完全符合前端对接文档: POST /api/driver-gesture/recognize
    """
    logger.info(f"收到车主手势识别请求: {file.filename}")

    # 1. 读取文件字节
    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="上传的文件为空")

    # 2. 调用核心识别服务
    gesture_key, confidence, landmarks = tracker.process_frame(image_bytes)

    # 3. 获取手势信息
    gesture_info = GESTURE_MAP.get(gesture_key, GESTURE_MAP["unknown"])
    gesture_name = gesture_info["name"]
    gesture_id = gesture_info["id"]

    # 4. 获取对应的控制动作（如果有映射）
    control_action = ACTION_MAP.get(gesture_key)

    # 5. 如果置信度太低，降级为未知
    if confidence < 0.3:
        gesture_name = "未知手势"
        gesture_id = -2
        control_action = None

    # 6. 构造符合文档的响应
    result = DriverGestureResult(
        gesture=gesture_name,
        gestureId=gesture_id,
        confidence=round(confidence, 4),
        controlAction=control_action
    )

    # 7. 返回统一格式（code=200 表示成功）
    return {
        "code": 200,
        "message": "success",
        "data": result.dict()
    }