import json
import tempfile
import time
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import desc
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from app.core.database import get_db
from app.models.db_models import PoliceGestureLog
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
from app.services.police_gesture_logger import GestureLogEntry, log_gesture_async

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
            return process_police_gesture_video(contents, file_ext, timestamp, filename=file.filename)
        return process_police_gesture_image(contents, timestamp)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as exc:
        logger.exception(f"交警手势识别失败: {exc}")
        log_gesture_async(
            GestureLogEntry(
                recognition_type="image" if file_ext not in VIDEO_EXTENSIONS else "video",
                gesture="未知",
                gesture_id=-1,
                confidence=0.0,
                inference_ms=0.0,
                success=False,
                filename=file.filename,
                error_message=str(exc),
            )
        )
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
        generate_police_gesture_video_stream(contents, file_ext, filename=file.filename),
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
        log_gesture_async(
            GestureLogEntry(
                recognition_type="camera_stream",
                gesture="未知",
                gesture_id=-1,
                confidence=0.0,
                inference_ms=0.0,
                success=False,
                error_message=str(exc),
            )
        )
        raise HTTPException(500, f"识别失败: {str(exc)}")


@router.get("/police-gesture/logs")
async def get_police_gesture_logs(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(10, ge=1, le=100, description="每页条数"),
    recognition_type: str | None = Query(None, description="识别类型: image/video/video_stream/camera_stream"),
    gesture: str | None = Query(None, description="手势名称筛选"),
    db: Session = Depends(get_db),
):
    """查询交警手势识别历史日志 (分页 + 筛选)"""
    query = db.query(PoliceGestureLog)

    if recognition_type:
        query = query.filter(PoliceGestureLog.recognition_type == recognition_type)
    if gesture:
        query = query.filter(PoliceGestureLog.gesture == gesture)

    total = query.count()
    total_pages = max(1, (total + page_size - 1) // page_size)
    rows = (
        query.order_by(desc(PoliceGestureLog.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    def _row_to_dict(row: PoliceGestureLog) -> dict:
        segments = None
        if row.segments_json:
            try:
                segments = json.loads(row.segments_json)
            except Exception:
                pass
        top5 = None
        if row.top5_json:
            try:
                top5 = json.loads(row.top5_json)
            except Exception:
                pass
        return {
            "id": row.id,
            "recognitionType": row.recognition_type,
            "videoSessionId": row.video_session_id,
            "filename": row.filename,
            "gesture": row.gesture,
            "gestureId": row.gesture_id,
            "confidence": row.confidence,
            "inferenceMs": row.inference_ms,
            "top5": top5,
            "framesTotal": row.frames_total,
            "framesProcessed": row.frames_processed,
            "videoFps": row.video_fps,
            "videoDuration": row.video_duration,
            "segments": segments,
            "success": row.success,
            "errorMessage": row.error_message,
            "createdAt": row.created_at.isoformat() if row.created_at else None,
        }

    return {
        "code": 200,
        "message": "success",
        "data": {
            "list": [_row_to_dict(row) for row in rows],
            "total": total,
            "page": page,
            "pageSize": page_size,
            "totalPages": total_pages,
        },
    }


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
