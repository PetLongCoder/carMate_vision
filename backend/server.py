"""
CarMate 交警手势识别推理服务
基于 ctpgr-pytorch 预训练模型 (Pose Estimation + LSTM)

启动: cd backend && python server.py
API文档: http://localhost:8000/docs
"""

import os
import io
import time
import tempfile
import logging
import json
import shutil
import subprocess
from pathlib import Path

LOCAL_PACKAGES_DIR = Path(__file__).parent / ".python-packages"
if LOCAL_PACKAGES_DIR.exists():
    import sys
    sys.path.insert(0, str(LOCAL_PACKAGES_DIR))

def load_env_file():
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


load_env_file()

# CARMATE_DEVICE:
# - auto: 有 CUDA 就使用 GPU，否则回退 CPU
# - cuda: 强制使用 GPU，CUDA 不可用时启动失败
# - cpu: 强制使用 CPU，并隐藏 CUDA，避免 Windows 原生 CUDA 崩溃
DEVICE_MODE = os.getenv("CARMATE_DEVICE", "auto").lower()
if DEVICE_MODE not in {"auto", "cpu", "cuda"}:
    DEVICE_MODE = "auto"

if DEVICE_MODE == "cpu":
    os.environ.setdefault("CUDA_VISIBLE_DEVICES", "-1")

import cv2
import numpy as np
from PIL import Image
from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from starlette.background import BackgroundTask

# ---- 将 ctpgr 加入路径 ----
CTPGR_DIR = Path(__file__).parent / "ctpgr"
import sys
sys.path.insert(0, str(CTPGR_DIR))

from constants.enum_keys import PG

# ---- 配置 ----
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# 8 种手势类别 (与前端 GESTURE_LABELS 一致)
GESTURE_NAMES_CN = [
    "无手势",    # 0
    "停止",      # 1
    "直行",      # 2
    "左转",      # 3
    "左转待转",  # 4
    "右转",      # 5
    "变道",      # 6
    "减速慢行",  # 7
    "靠边停车",  # 8
]

# ---- FastAPI ----
GESTURE_NAMES_CN = [
    "无手势",
    "停止",
    "直行",
    "左转",
    "左转待转",
    "右转",
    "变道",
    "减速慢行",
    "靠边停车",
]

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    preload_model()
    logger.info("CarMate 推理服务已启动 (ctpgr-pytorch)")
    yield

app = FastAPI(
    title="CarMate 视觉推理服务",
    description="车载智能视觉系统后端 - 交警手势识别 (ctpgr-pytorch)",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 全局共享模型 (只加载一次)
_shared_pose = None   # 姿态估计模型 (45MB)
_shared_bla = None     # 骨骼特征提取器
_shared_lstm = None    # LSTM 手势分类模型 (60KB)


_stream_states = {}


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        logger.warning("Invalid %s, fallback to %s", name, default)
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        logger.warning("Invalid %s, fallback to %s", name, default)
        return default


VIDEO_SAMPLE_FPS = _env_float("CARMATE_VIDEO_SAMPLE_FPS", 15.0)
LSTM_WARMUP_FRAMES = _env_int("CARMATE_LSTM_WARMUP_FRAMES", 15)
SMOOTH_WINDOW = max(1, _env_int("CARMATE_SMOOTH_WINDOW", 5))
MIN_SEGMENT_SECONDS = _env_float("CARMATE_MIN_SEGMENT_SECONDS", 0.6)
LABEL_TIME_OFFSET_SECONDS = max(0.0, _env_float("CARMATE_LABEL_TIME_OFFSET_SECONDS", 0.8))
PREVIEW_MAX_WIDTH = max(240, _env_int("CARMATE_PREVIEW_MAX_WIDTH", 1280))
PREVIEW_CRF = min(35, max(18, _env_int("CARMATE_PREVIEW_CRF", 23)))
PREVIEW_TRANSCODE_TIMEOUT_SECONDS = max(30, _env_int("CARMATE_PREVIEW_TRANSCODE_TIMEOUT_SECONDS", 300))
VIDEO_EXTENSIONS = (".mp4", ".avi", ".mov", ".webm", ".mkv")


def get_torch_device_info() -> dict:
    import torch

    cuda_available = bool(torch.cuda.is_available())
    info = {
        "device_mode": DEVICE_MODE,
        "cuda_available": cuda_available,
        "cuda_version": torch.version.cuda,
        "device": "cuda" if cuda_available else "cpu",
        "gpu_name": None,
        "gpu_count": torch.cuda.device_count() if cuda_available else 0,
    }
    if cuda_available:
        info["gpu_name"] = torch.cuda.get_device_name(0)
    return info


def force_cpu_if_needed():
    if DEVICE_MODE != "cpu":
        return
    import torch
    torch.cuda.is_available = lambda: False


def validate_device_mode():
    import torch

    if DEVICE_MODE == "cuda" and not torch.cuda.is_available():
        raise RuntimeError(
            "CARMATE_DEVICE=cuda 但当前 PyTorch 无法使用 CUDA。"
            "请检查 NVIDIA 驱动、CUDA 版 PyTorch，或改为 CARMATE_DEVICE=auto/cpu。"
        )


def preload_model():
    """预加载所有模型"""
    global _shared_pose, _shared_bla, _shared_lstm
    import os
    force_cpu_if_needed()
    validate_device_mode()
    device_info = get_torch_device_info()
    logger.info(
        "推理设备: %s (mode=%s, cuda_available=%s, gpu=%s)",
        device_info["device"],
        device_info["device_mode"],
        device_info["cuda_available"],
        device_info["gpu_name"] or "-",
    )
    old_cwd = os.getcwd()
    os.chdir(str(CTPGR_DIR))
    try:
        from pred.human_keypoint_pred import HumanKeypointPredict
        from pgdataset.s3_handcraft import BoneLengthAngle
        from models.gesture_recognition_model import GestureRecognitionModel
        logger.info("加载姿态估计模型 (45MB)...")
        _shared_pose = HumanKeypointPredict()
        _shared_bla = BoneLengthAngle()
        logger.info("加载 LSTM 手势分类模型...")
        _shared_lstm = GestureRecognitionModel(1)
        _shared_lstm.load_ckpt()
        _shared_lstm.eval()
        # 预热
        dummy = np.random.randint(0, 255, (512, 512, 3), dtype=np.uint8)
        _shared_pose.get_coordinates(dummy)
        logger.info("模型预加载完成")
    finally:
        os.chdir(old_cwd)


def predict_single_frame(img_bgr: np.ndarray):
    """单帧推理: 共享姿态模型 + 独立 LSTM 状态
    每帧重置 h0/c0, 避免长序列 CUDA 段错误"""
    import torch
    import os
    old_cwd = os.getcwd()
    os.chdir(str(CTPGR_DIR))
    try:
        # 姿态估计
        p_res = _shared_pose.get_coordinates(img_bgr)
        coord_norm = p_res[PG.COORD_NORM][np.newaxis]

        # 骨骼特征
        ges_data = _shared_bla.handcrafted_features(coord_norm)
        features = np.concatenate((ges_data[PG.BONE_LENGTH], ges_data[PG.BONE_ANGLE_COS],
                                    ges_data[PG.BONE_ANGLE_SIN]), axis=1)
        features = features[np.newaxis].transpose((1, 0, 2))
        features = torch.from_numpy(features).float().to(_shared_lstm.device)

        # 每帧独立 LSTM 状态
        h0, c0 = _shared_lstm.h0(), _shared_lstm.c0()
        with torch.no_grad():
            _, _, _, class_out = _shared_lstm(features, h0, c0)

        np_out = class_out[0].cpu().numpy()
        scores_arr = np_out if np_out.ndim == 1 else np_out[0]
        gesture_id = int(np.argmax(scores_arr))
        return gesture_id, scores_arr
    finally:
        os.chdir(old_cwd)


def predict_video_frame(img_bgr: np.ndarray, state):
    """视频序列推理: 同一视频内保留 LSTM 状态。"""
    import torch
    import os
    old_cwd = os.getcwd()
    os.chdir(str(CTPGR_DIR))
    try:
        p_res = _shared_pose.get_coordinates(img_bgr)
        coord_norm = p_res[PG.COORD_NORM][np.newaxis]

        ges_data = _shared_bla.handcrafted_features(coord_norm)
        features = np.concatenate((ges_data[PG.BONE_LENGTH], ges_data[PG.BONE_ANGLE_COS],
                                    ges_data[PG.BONE_ANGLE_SIN]), axis=1)
        features = features[np.newaxis].transpose((1, 0, 2))
        features = torch.from_numpy(features).float().to(_shared_lstm.device)

        h, c = state
        with torch.no_grad():
            _, h, c, class_out = _shared_lstm(features, h, c)

        np_out = class_out[0].cpu().numpy()
        scores_arr = np_out if np_out.ndim == 1 else np_out[0]
        gesture_id = int(np.argmax(scores_arr))
        return gesture_id, scores_arr, (h.detach(), c.detach())
    finally:
        os.chdir(old_cwd)


def resize_keep_ratio(img_bgr: np.ndarray, target_size=(512, 512)) -> np.ndarray:
    """等比例缩放并居中补边，和 ctpgr 原始视频推理保持一致。"""
    target_w, target_h = target_size
    img_h, img_w = img_bgr.shape[:2]
    scale = min(target_w / img_w, target_h / img_h)
    resized_w = max(1, int(round(img_w * scale)))
    resized_h = max(1, int(round(img_h * scale)))

    resized = cv2.resize(img_bgr, (resized_w, resized_h))
    canvas = np.zeros((target_h, target_w, 3), dtype=img_bgr.dtype)
    left = (target_w - resized_w) // 2
    top = (target_h - resized_h) // 2
    canvas[top:top + resized_h, left:left + resized_w] = resized
    return canvas


def _smooth_frame_results(frame_results: list[dict]) -> list[dict]:
    if not frame_results:
        return []

    half_window = SMOOTH_WINDOW // 2
    smoothed = []
    for idx, fr in enumerate(frame_results):
        left = max(0, idx - half_window)
        right = min(len(frame_results), idx + half_window + 1)
        window = frame_results[left:right]
        votes = {}
        confs = {}
        for item in window:
            gid = item["gestureId"]
            votes[gid] = votes.get(gid, 0) + 1
            confs[gid] = confs.get(gid, 0.0) + item["confidence"]

        # Prefer stronger average confidence when classes tie in the window.
        best_gid = max(votes, key=lambda gid: (votes[gid], confs[gid] / votes[gid]))
        best_conf = confs[best_gid] / votes[best_gid]

        merged = dict(fr)
        merged["rawGestureId"] = fr["gestureId"]
        merged["rawGesture"] = fr["gesture"]
        merged["rawConfidence"] = fr["confidence"]
        merged["gestureId"] = int(best_gid)
        merged["gesture"] = GESTURE_NAMES_CN[best_gid] if best_gid < len(GESTURE_NAMES_CN) else "未知"
        merged["confidence"] = round(float(best_conf), 4)
        smoothed.append(merged)

    return smoothed


def _build_segments(frame_results: list[dict]) -> list[dict]:
    segments = []
    seg_start = None
    seg_gesture = None
    last_time = frame_results[-1]["time"] if frame_results else 0

    for fr in frame_results:
        gid = fr["gestureId"]
        if gid != seg_gesture:
            if seg_start is not None and seg_gesture is not None and seg_gesture > 0:
                end_time = fr["time"]
                if end_time - seg_start["time"] >= MIN_SEGMENT_SECONDS:
                    segments.append({
                        "start": seg_start["time"],
                        "end": end_time,
                        "gesture": GESTURE_NAMES_CN[seg_gesture],
                        "gestureId": seg_gesture,
                    })
            seg_start = fr
            seg_gesture = gid

    if seg_start is not None and seg_gesture is not None and seg_gesture > 0:
        if last_time - seg_start["time"] >= MIN_SEGMENT_SECONDS:
            segments.append({
                "start": seg_start["time"],
                "end": last_time,
                "gesture": GESTURE_NAMES_CN[seg_gesture],
                "gestureId": seg_gesture,
            })

    return segments


def _vote_best_gesture(frame_results: list[dict]) -> tuple[int, float, list[dict]]:
    valid_frames = frame_results[LSTM_WARMUP_FRAMES:] if len(frame_results) > LSTM_WARMUP_FRAMES else frame_results
    gesture_scores = {}
    gesture_counts = {}

    for fr in valid_frames:
        gid = fr["gestureId"]
        if gid <= 0:
            continue
        gesture_scores[gid] = gesture_scores.get(gid, 0.0) + fr["confidence"]
        gesture_counts[gid] = gesture_counts.get(gid, 0) + 1

    if not gesture_scores:
        return 0, 0.0, []

    best_gesture_id = max(gesture_scores, key=lambda gid: (gesture_counts[gid], gesture_scores[gid]))
    avg_confidence = gesture_scores[best_gesture_id] / gesture_counts[best_gesture_id]
    total = max(1, len(valid_frames))
    top5 = sorted(gesture_scores, key=lambda gid: (gesture_counts[gid], gesture_scores[gid]), reverse=True)[:5]
    top5_list = [
        {
            "gesture": GESTURE_NAMES_CN[gid] if gid < len(GESTURE_NAMES_CN) else "未知",
            "gestureId": gid,
            "confidence": round(gesture_counts[gid] / total, 4),
        }
        for gid in top5
    ]
    return int(best_gesture_id), float(avg_confidence), top5_list


def _video_meta(cap) -> tuple[int, float, float, int, float]:
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)

    if total_frames <= 0:
        raise HTTPException(400, "无法读取视频")

    target_sample_fps = min(VIDEO_SAMPLE_FPS, fps) if fps > 0 else VIDEO_SAMPLE_FPS
    sample_interval = max(1, int(round(fps / target_sample_fps))) if fps > 0 else 1
    duration = total_frames / fps if fps > 0 else 0
    return total_frames, fps, target_sample_fps, sample_interval, duration


def _scores_to_probs(scores_arr):
    import torch
    import torch.nn.functional as F

    t = torch.from_numpy(scores_arr).float() if isinstance(scores_arr, np.ndarray) else scores_arr.float()
    probs = F.softmax(t, dim=-1)
    return probs.tolist() if hasattr(probs, "tolist") else list(probs)


def _display_time(seconds: float) -> float:
    return round(max(0.0, seconds - LABEL_TIME_OFFSET_SECONDS), 2)


def _with_display_time(frame_result: dict) -> dict:
    display_time = _display_time(float(frame_result["time"]))
    return {
        **frame_result,
        "raw_time": frame_result["time"],
        "time": display_time,
        "display_time": display_time,
        "label_offset_seconds": LABEL_TIME_OFFSET_SECONDS,
    }


def _apply_label_offset_to_segments(segments: list[dict]) -> list[dict]:
    return [
        {
            **segment,
            "raw_start": segment["start"],
            "raw_end": segment["end"],
            "start": _display_time(float(segment["start"])),
            "end": _display_time(float(segment["end"])),
            "label_offset_seconds": LABEL_TIME_OFFSET_SECONDS,
        }
        for segment in segments
    ]


def _build_video_result(
    frame_results: list[dict],
    *,
    timestamp: int,
    elapsed: float,
    total_frames: int,
    fps: float,
    target_sample_fps: float,
    sample_interval: int,
    duration: float,
    processed: int,
):
    raw_smoothed_results = _smooth_frame_results(frame_results)
    smoothed_results = [_with_display_time(item) for item in raw_smoothed_results]
    best_gesture_id, avg_confidence, top5_list = _vote_best_gesture(smoothed_results)
    gesture_cn = GESTURE_NAMES_CN[best_gesture_id] if best_gesture_id < len(GESTURE_NAMES_CN) else "未知"
    segments = _apply_label_offset_to_segments(_build_segments(raw_smoothed_results))

    return {
        "gesture": gesture_cn,
        "gestureId": best_gesture_id,
        "confidence": round(avg_confidence, 4),
        "timestamp": timestamp,
        "top5": top5_list,
        "inference_ms": round(elapsed * 1000, 1),
        "video_duration": round(duration, 1),
        "video_fps": round(fps, 1),
        "sample_fps": round(target_sample_fps, 1),
        "sample_interval": sample_interval,
        "label_offset_seconds": LABEL_TIME_OFFSET_SECONDS,
        "warmup_frames": min(LSTM_WARMUP_FRAMES, processed),
        "frames_total": total_frames,
        "frames_processed": processed,
        "frames": smoothed_results,
        "segments": segments,
    }


def _sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _ffmpeg_path() -> str | None:
    ffmpeg_bin = os.getenv("CARMATE_FFMPEG_PATH")
    if ffmpeg_bin and Path(ffmpeg_bin).is_file():
        return ffmpeg_bin

    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return system_ffmpeg

    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def _remove_files(paths: list[str]):
    for path in paths:
        try:
            if path and Path(path).exists():
                os.unlink(path)
        except OSError:
            logger.warning("临时文件清理失败: %s", path)


def _transcode_browser_preview(input_path: str, output_path: str):
    ffmpeg_bin = _ffmpeg_path()
    if not ffmpeg_bin:
        raise HTTPException(
            503,
            "后端未找到 FFmpeg。请安装 ffmpeg 或安装 Python 依赖 imageio-ffmpeg 后重启服务。",
        )

    vf = f"scale='min({PREVIEW_MAX_WIDTH},iw)':-2"
    command = [
        ffmpeg_bin,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        input_path,
        "-vf",
        vf,
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        str(PREVIEW_CRF),
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        output_path,
    ]

    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=PREVIEW_TRANSCODE_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(504, "预览视频转码超时，请尝试更短的视频")

    if completed.returncode != 0 or not Path(output_path).is_file():
        detail = completed.stderr.strip() or "FFmpeg 转码失败"
        raise HTTPException(500, f"预览视频转码失败: {detail}")


@app.get("/api/health")
async def health_check():
    device_info = get_torch_device_info()
    return {
        "status": "ok",
        "model": "ctpgr-pytorch (Pose + LSTM)",
        "classes": len(GESTURE_NAMES_CN),
        **device_info,
    }


@app.post("/api/police-gesture/stream/reset")
async def reset_police_gesture_stream(stream_id: str = Form("default")):
    _stream_states.pop(stream_id, None)
    return {"code": 200, "message": "success", "data": {"streamId": stream_id}}


@app.post("/api/police-gesture/stream/frame")
async def recognize_police_gesture_stream_frame(
    file: UploadFile = File(...),
    stream_id: str = Form("default"),
):
    contents = await file.read()
    try:
        image = Image.open(io.BytesIO(contents))
        if image.mode != "RGB":
            image = image.convert("RGB")
    except Exception:
        raise HTTPException(400, "无法解析摄像头帧")

    img_array = np.array(image)
    img_bgr = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
    re_frame = resize_keep_ratio(img_bgr, (512, 512))

    state = _stream_states.get(stream_id)
    if state is None:
        state = (_shared_lstm.h0(), _shared_lstm.c0())

    start = time.time()
    gesture_id, scores_arr, state = predict_video_frame(re_frame, state)
    _stream_states[stream_id] = state
    elapsed = time.time() - start

    import torch
    import torch.nn.functional as F

    t = torch.from_numpy(scores_arr).float() if isinstance(scores_arr, np.ndarray) else scores_arr.float()
    scores = F.softmax(t, dim=-1).tolist()
    confidence = float(scores[gesture_id]) if gesture_id < len(scores) else 0.0
    gesture_cn = GESTURE_NAMES_CN[gesture_id] if gesture_id < len(GESTURE_NAMES_CN) else "未知"

    top5 = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)[:5]
    top5_list = [
        {
            "gesture": GESTURE_NAMES_CN[i] if i < len(GESTURE_NAMES_CN) else "未知",
            "gestureId": i,
            "confidence": round(float(score), 4),
        }
        for i, score in top5
    ]

    return {
        "code": 200,
        "message": "success",
        "data": {
            "streamId": stream_id,
            "gesture": gesture_cn,
            "gestureId": gesture_id,
            "confidence": round(confidence, 4),
            "timestamp": int(time.time() * 1000),
            "top5": top5_list,
            "inference_ms": round(elapsed * 1000, 1),
        },
    }


@app.post("/api/police-gesture/preview")
async def create_police_gesture_preview(file: UploadFile = File(...)):
    """将上传视频转为浏览器友好的 MP4(H.264/yuv420p)，仅用于前端预览播放。"""
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


@app.post("/api/police-gesture/recognize")
async def recognize_police_gesture(file: UploadFile = File(...)):
    """交警手势识别 - 上传图片或视频"""
    contents = await file.read()
    file_ext = Path(file.filename or "image.jpg").suffix.lower()
    timestamp = int(time.time() * 1000)

    try:
        if file_ext in VIDEO_EXTENSIONS:
            return await _process_video(contents, file_ext, timestamp)
        else:
            return await _process_image(contents, timestamp)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"识别失败: {e}")
        raise HTTPException(500, f"识别失败: {str(e)}")


@app.post("/api/police-gesture/recognize/stream")
async def recognize_police_gesture_stream_video(file: UploadFile = File(...)):
    """流式视频识别: 边分析边返回采样帧结果，最后返回平滑后的完整时间线。"""
    contents = await file.read()
    file_ext = Path(file.filename or "video.mp4").suffix.lower()
    if file_ext not in VIDEO_EXTENSIONS:
        raise HTTPException(400, "流式识别仅支持视频文件")

    timestamp = int(time.time() * 1000)

    def generate():
        with tempfile.NamedTemporaryFile(suffix=file_ext, delete=False) as tmp:
            tmp.write(contents)
            tmp_path = tmp.name

        cap = None
        try:
            cap = cv2.VideoCapture(tmp_path)
            total_frames, fps, target_sample_fps, sample_interval, duration = _video_meta(cap)
            logger.info(
                "流式视频推理: %s帧, fps=%.1f, 采样间隔=%s",
                total_frames,
                fps,
                sample_interval,
            )

            yield _sse_event("meta", {
                "timestamp": timestamp,
                "frames_total": total_frames,
                "video_duration": round(duration, 1),
                "video_fps": round(fps, 1),
                "sample_fps": round(target_sample_fps, 1),
                "sample_interval": sample_interval,
            })

            start = time.time()
            frame_results = []
            frame_idx = 0
            processed = 0
            lstm_state = (_shared_lstm.h0(), _shared_lstm.c0())

            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                if frame_idx % sample_interval == 0:
                    re_frame = resize_keep_ratio(frame, (512, 512))
                    gesture_id, scores_arr, lstm_state = predict_video_frame(re_frame, lstm_state)
                    scores = _scores_to_probs(scores_arr)
                    confidence = float(scores[gesture_id]) if gesture_id < len(scores) else 0.0
                    frame_seconds = frame_idx / fps if fps > 0 else 0
                    frame_result = {
                        "frame": frame_idx,
                        "time": round(frame_seconds, 2),
                        "gesture": GESTURE_NAMES_CN[gesture_id] if gesture_id < len(GESTURE_NAMES_CN) else "未知",
                        "gestureId": gesture_id,
                        "confidence": round(confidence, 4),
                    }
                    frame_results.append(frame_result)
                    processed += 1
                    yield _sse_event("frame", {
                        **_with_display_time(frame_result),
                        "frames_processed": processed,
                        "progress": round(min(99, (frame_idx + 1) / total_frames * 100), 1),
                    })

                frame_idx += 1

            elapsed = time.time() - start
            result = _build_video_result(
                frame_results,
                timestamp=timestamp,
                elapsed=elapsed,
                total_frames=total_frames,
                fps=fps,
                target_sample_fps=target_sample_fps,
                sample_interval=sample_interval,
                duration=duration,
                processed=processed,
            )
            logger.info(
                "流式视频识别完成: %s (%s帧, %s个手势段, %.0fms)",
                result["gesture"],
                processed,
                len(result["segments"]),
                elapsed * 1000,
            )
            yield _sse_event("done", result)
        except Exception as e:
            logger.exception("流式视频识别失败: %s", e)
            yield _sse_event("error", {"message": str(e)})
        finally:
            if cap is not None:
                cap.release()
            os.unlink(tmp_path)

    return StreamingResponse(generate(), media_type="text/event-stream")


async def _process_image(contents: bytes, timestamp: int):
    """处理单张图片"""
    try:
        image = Image.open(io.BytesIO(contents))
        if image.mode != "RGB":
            image = image.convert("RGB")
    except Exception:
        raise HTTPException(400, "无法解析图片文件")

    img_array = np.array(image)  # HWC, RGB
    img_bgr = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)

    start = time.time()
    gesture_id, scores_arr = predict_single_frame(img_bgr)
    elapsed = time.time() - start
    # 模型输出是 logits, 转为概率
    import torch.nn.functional as F
    import torch
    if isinstance(scores_arr, np.ndarray):
        t = torch.from_numpy(scores_arr).float()
    else:
        t = scores_arr.float()
    probs = F.softmax(t, dim=-1)
    scores = probs.tolist() if hasattr(probs, 'tolist') else list(probs)

    gesture_cn = GESTURE_NAMES_CN[gesture_id] if gesture_id < len(GESTURE_NAMES_CN) else "未知"
    confidence = float(scores[gesture_id]) if gesture_id < len(scores) else 0.0

    # Top-5
    top5 = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)[:5]
    top5_list = [
        {"gesture": GESTURE_NAMES_CN[i] if i < len(GESTURE_NAMES_CN) else "未知",
         "gestureId": i, "confidence": round(s, 4)}
        for i, s in top5
    ]

    logger.info(f"图片识别: {gesture_cn} (置信度 {confidence:.2%}, {elapsed*1000:.0f}ms)")

    return {
        "code": 200, "message": "success",
        "data": {
            "gesture": gesture_cn, "gestureId": gesture_id,
            "confidence": round(confidence, 4),
            "timestamp": timestamp,
            "top5": top5_list,
            "inference_ms": round(elapsed * 1000, 1),
        },
    }


async def _process_video(contents: bytes, file_ext: str, timestamp: int):
    """处理视频文件 (逐帧推理, 返回每帧的手势标注)"""
    with tempfile.NamedTemporaryFile(suffix=file_ext, delete=False) as tmp:
        tmp.write(contents)
        tmp_path = tmp.name

    try:
        cap = cv2.VideoCapture(tmp_path)
        total_frames, fps, target_sample_fps, sample_interval, duration = _video_meta(cap)
        logger.info(f"视频推理: {total_frames}帧, fps={fps:.1f}, 采样间隔={sample_interval}")

        start = time.time()
        frame_results = []
        frame_idx = 0
        processed = 0
        lstm_state = (_shared_lstm.h0(), _shared_lstm.c0())

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            if frame_idx % sample_interval == 0:
                re_frame = resize_keep_ratio(frame, (512, 512))
                gesture_id, scores_arr, lstm_state = predict_video_frame(re_frame, lstm_state)
                scores = _scores_to_probs(scores_arr)
                confidence = float(scores[gesture_id]) if gesture_id < len(scores) else 0.0

                # 记录每帧结果: 视频时间戳 + 手势
                frame_seconds = frame_idx / fps if fps > 0 else 0
                frame_results.append({
                    "frame": frame_idx,
                    "time": round(frame_seconds, 2),
                    "gesture": GESTURE_NAMES_CN[gesture_id] if gesture_id < len(GESTURE_NAMES_CN) else "未知",
                    "gestureId": gesture_id,
                    "confidence": round(confidence, 4),
                })
                processed += 1

            frame_idx += 1

        cap.release()
        elapsed = time.time() - start
        result = _build_video_result(
            frame_results,
            timestamp=timestamp,
            elapsed=elapsed,
            total_frames=total_frames,
            fps=fps,
            target_sample_fps=target_sample_fps,
            sample_interval=sample_interval,
            duration=duration,
            processed=processed,
        )
        logger.info(f"视频识别: {result['gesture']} ({processed}帧, {len(result['segments'])}个手势段, {elapsed*1000:.0f}ms)")

        return {
            "code": 200, "message": "success",
            "data": result,
        }
    finally:
        os.unlink(tmp_path)


# ---- 预留接口 ----
@app.post("/api/plate/recognize")
async def recognize_plate(file: UploadFile = File(...)):
    return {"code": 200, "message": "车牌识别功能开发中", "data": []}


@app.post("/api/driver-gesture/recognize")
async def recognize_driver_gesture(file: UploadFile = File(...)):
    return {"code": 200, "message": "车主手势识别功能开发中", "data": {}}


if __name__ == "__main__":
    import uvicorn
    print("=" * 60)
    print("CarMate 视觉推理服务 (ctpgr-pytorch)")
    print("=" * 60)
    print(f"框架: Pose Estimation + LSTM")
    print(f"手势类别: {len(GESTURE_NAMES_CN)} 类")
    print(f"API 文档: http://localhost:8000/docs")
    print("=" * 60)
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
