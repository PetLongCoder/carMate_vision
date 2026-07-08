import tempfile
import time
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from app.utils.logger import logger

from server import (
    GESTURE_NAMES_CN,
    VIDEO_EXTENSIONS,
    _process_image,
    _process_video,
    _remove_files,
    _stream_states,
    _transcode_browser_preview,
    get_torch_device_info,
    preload_model,
    recognize_police_gesture_stream_frame as _recognize_police_gesture_stream_frame,
    recognize_police_gesture_stream_video as _recognize_police_gesture_stream_video,
)


router = APIRouter()
_models_loaded = False


def ensure_police_gesture_model_loaded():
    """Lazy-load ctpgr models for the unified backend."""
    global _models_loaded
    if _models_loaded:
        return

    logger.info("统一后端正在加载交警手势识别模型")
    preload_model()
    _models_loaded = True


@router.get("/health")
async def health_check():
    device_info = get_torch_device_info()
    return {
        "status": "ok",
        "model": "ctpgr-pytorch (Pose + LSTM)",
        "classes": len(GESTURE_NAMES_CN),
        **device_info,
    }


@router.post("/police-gesture/recognize")
async def recognize_police_gesture(file: UploadFile = File(...)):
    """交警手势识别 - 支持图片或视频。"""
    ensure_police_gesture_model_loaded()

    contents = await file.read()
    file_ext = Path(file.filename or "image.jpg").suffix.lower()
    timestamp = int(time.time() * 1000)

    try:
        if file_ext in VIDEO_EXTENSIONS:
            return await _process_video(contents, file_ext, timestamp)
        return await _process_image(contents, timestamp)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(f"交警手势识别失败: {exc}")
        raise HTTPException(500, f"识别失败: {str(exc)}") from exc


@router.post("/police-gesture/recognize/stream")
async def recognize_police_gesture_stream_video(file: UploadFile = File(...)):
    """上传视频边分析边返回结果。"""
    ensure_police_gesture_model_loaded()
    return await _recognize_police_gesture_stream_video(file)


@router.post("/police-gesture/stream/reset")
async def reset_police_gesture_stream(stream_id: str = Form("default")):
    _stream_states.pop(stream_id, None)
    return {"code": 200, "message": "success", "data": {"streamId": stream_id}}


@router.post("/police-gesture/stream/frame")
async def recognize_police_gesture_stream_frame(
    file: UploadFile = File(...),
    stream_id: str = Form("default"),
):
    """实时摄像头截帧识别。"""
    ensure_police_gesture_model_loaded()
    return await _recognize_police_gesture_stream_frame(file, stream_id)


@router.post("/police-gesture/preview")
async def create_police_gesture_preview(file: UploadFile = File(...)):
    """生成浏览器兼容的 MP4 预览视频。"""
    contents = await file.read()
    file_ext = Path(file.filename or "video.mp4").suffix.lower()
    if file_ext not in VIDEO_EXTENSIONS:
        raise HTTPException(400, "预览转码仅支持视频文件")

    with tempfile.NamedTemporaryFile(suffix=file_ext, delete=False) as src_tmp:
        src_tmp.write(contents)
        src_path = src_tmp.name

    out_tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    out_path = out_tmp.name
    out_tmp.close()

    try:
        _transcode_browser_preview(src_path, out_path)
    except Exception:
        _remove_files([src_path, out_path])
        raise

    return FileResponse(
        out_path,
        media_type="video/mp4",
        filename=f"{Path(file.filename or 'preview').stem}_preview.mp4",
        background=BackgroundTask(_remove_files, [src_path, out_path]),
    )
