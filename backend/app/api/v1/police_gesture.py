import tempfile
import time
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from starlette.background import BackgroundTask

from app.utils.logger import logger
from app.services.police_gesture_service import (
    GESTURE_NAMES_CN,
    VIDEO_EXTENSIONS,
    get_torch_device_info,
    is_model_loaded,
    preload_model,
    process_police_gesture_image,
    process_police_gesture_video,
    generate_police_gesture_video_stream,
    process_stream_frame,
    reset_stream_state,
    remove_files,
    transcode_browser_preview,
)

router = APIRouter()
_models_loaded = False


def ensure_police_gesture_model_loaded():
    """Lazy-load 交警手势模型"""
    global _models_loaded
    if _models_loaded or is_model_loaded():
        _models_loaded = True
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
            return process_police_gesture_video(contents, file_ext, timestamp)
        return process_police_gesture_image(contents, timestamp)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as exc:
        logger.exception(f"交警手势识别失败: {exc}")
        raise HTTPException(500, f"识别失败: {str(exc)}")


@router.post("/police-gesture/recognize/stream")
async def recognize_police_gesture_stream_video(file: UploadFile = File(...)):
    """上传视频边分析边返回结果（SSE）。"""
    ensure_police_gesture_model_loaded()
    contents = await file.read()
    file_ext = Path(file.filename or "video.mp4").suffix.lower()
    if file_ext not in VIDEO_EXTENSIONS:
        raise HTTPException(400, "流式识别仅支持视频文件")
    return StreamingResponse(
        generate_police_gesture_video_stream(contents, file_ext),
        media_type="text/event-stream",
    )


@router.post("/police-gesture/stream/reset")
async def reset_police_gesture_stream(stream_id: str = Form("default")):
    reset_stream_state(stream_id)
    return {"code": 200, "message": "success", "data": {"streamId": stream_id}}


@router.post("/police-gesture/stream/frame")
async def recognize_police_gesture_stream_frame(
    file: UploadFile = File(...),
    stream_id: str = Form("default"),
):
    """实时摄像头截帧识别。"""
    ensure_police_gesture_model_loaded()
    contents = await file.read()
    try:
        return process_stream_frame(contents, stream_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as exc:
        logger.exception(f"实时帧识别失败: {exc}")
        raise HTTPException(500, f"识别失败: {str(exc)}")


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
        transcode_browser_preview(src_path, out_path)
    except RuntimeError as e:
        remove_files([src_path, out_path])
        raise HTTPException(500, str(e))
    except Exception:
        remove_files([src_path, out_path])
        raise

    return FileResponse(
        out_path,
        media_type="video/mp4",
        filename=f"{Path(file.filename or 'preview').stem}_preview.mp4",
        background=BackgroundTask(remove_files, [src_path, out_path]),
    )
