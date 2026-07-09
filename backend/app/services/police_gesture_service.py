"""
交警手势识别推理服务
====================
基于 ctpgr-pytorch 预训练模型 (Pose Estimation + LSTM)

本模块被 app/api/v1/police_gesture.py 使用,
运行在统一后端 app.main:app (端口 8001) 中。
"""

import os
import io
import time
import tempfile
import logging
import json
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Optional, Generator, Any

import cv2
import numpy as np
from PIL import Image

from app.utils.logger import logger
from app.services.police_gesture_logger import (
    GestureLogEntry,
    log_gesture_async,
    log_gestures_batch_async,
    build_top5_json,
    build_segments_json,
)

# ---- 将 ctpgr 加入路径 ----
_CTPGR_DIR = Path(__file__).parent.parent.parent / "ctpgr"
import sys as _sys

if str(_CTPGR_DIR) not in _sys.path:
    _sys.path.insert(0, str(_CTPGR_DIR))


# ═══════════════════════════════════════════════════════════════
#  Constants
# ═══════════════════════════════════════════════════════════════

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

VIDEO_EXTENSIONS = (".mp4", ".avi", ".mov", ".webm", ".mkv")


# ═══════════════════════════════════════════════════════════════
#  Configuration (environment variables)
# ═══════════════════════════════════════════════════════════════

DEVICE_MODE = os.getenv("CARMATE_DEVICE", "auto").lower()
if DEVICE_MODE not in {"auto", "cpu", "cuda"}:
    DEVICE_MODE = "auto"

if DEVICE_MODE == "cpu":
    os.environ.setdefault("CUDA_VISIBLE_DEVICES", "-1")


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


# ═══════════════════════════════════════════════════════════════
#  Device / Torch utilities
# ═══════════════════════════════════════════════════════════════

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


def _force_cpu_if_needed():
    if DEVICE_MODE != "cpu":
        return
    import torch

    torch.cuda.is_available = lambda: False


def _validate_device_mode():
    import torch

    if DEVICE_MODE == "cuda" and not torch.cuda.is_available():
        raise RuntimeError(
            "CARMATE_DEVICE=cuda 但当前 PyTorch 无法使用 CUDA。"
            "请检查 NVIDIA 驱动、CUDA 版 PyTorch，或改为 CARMATE_DEVICE=auto/cpu。"
        )


# ═══════════════════════════════════════════════════════════════
#  Shared model instances (singleton, lazy-loaded)
# ═══════════════════════════════════════════════════════════════

_shared_pose = None   # 姿态估计模型
_shared_bla = None    # 骨骼特征提取器
_shared_lstm = None   # LSTM 手势分类模型
_models_loaded = False


def is_model_loaded() -> bool:
    return _models_loaded


def preload_model():
    """预加载所有模型 (姿态估计 + 骨骼特征 + LSTM 分类)"""
    global _shared_pose, _shared_bla, _shared_lstm, _models_loaded

    if _models_loaded:
        return

    _force_cpu_if_needed()
    _validate_device_mode()

    device_info = get_torch_device_info()
    logger.info(
        "交警手势推理设备: %s (mode=%s, gpu=%s)",
        device_info["device"],
        device_info["device_mode"],
        device_info["gpu_name"] or "-",
    )

    old_cwd = os.getcwd()
    os.chdir(str(_CTPGR_DIR))
    try:
        from pred.human_keypoint_pred import HumanKeypointPredict
        from pgdataset.s3_handcraft import BoneLengthAngle
        from models.gesture_recognition_model import GestureRecognitionModel

        logger.info("加载姿态估计模型 ...")
        _shared_pose = HumanKeypointPredict()
        _shared_bla = BoneLengthAngle()

        logger.info("加载 LSTM 手势分类模型 ...")
        _shared_lstm = GestureRecognitionModel(1)
        _shared_lstm.load_ckpt()
        _shared_lstm.eval()

        # 预热
        dummy = np.random.randint(0, 255, (512, 512, 3), dtype=np.uint8)
        _shared_pose.get_coordinates(dummy)

        _models_loaded = True
        logger.info("交警手势模型预加载完成")
    finally:
        os.chdir(old_cwd)


# ═══════════════════════════════════════════════════════════════
#  Image preprocessing
# ═══════════════════════════════════════════════════════════════

def resize_keep_ratio(img_bgr: np.ndarray, target_size=(512, 512)) -> np.ndarray:
    """等比例缩放并居中补边"""
    target_w, target_h = target_size
    img_h, img_w = img_bgr.shape[:2]
    scale = min(target_w / img_w, target_h / img_h)
    resized_w = max(1, int(round(img_w * scale)))
    resized_h = max(1, int(round(img_h * scale)))

    resized = cv2.resize(img_bgr, (resized_w, resized_h))
    canvas = np.zeros((target_h, target_w, 3), dtype=img_bgr.dtype)
    left = (target_w - resized_w) // 2
    top = (target_h - resized_h) // 2
    canvas[top : top + resized_h, left : left + resized_w] = resized
    return canvas


# ═══════════════════════════════════════════════════════════════
#  Frame inference
# ═══════════════════════════════════════════════════════════════

def predict_single_frame(img_bgr: np.ndarray):
    """单帧推理: 每帧独立 LSTM 状态"""
    import torch
    from constants.enum_keys import PG as _PG

    old_cwd = os.getcwd()
    os.chdir(str(_CTPGR_DIR))
    try:
        p_res = _shared_pose.get_coordinates(img_bgr)
        coord_norm = p_res[_PG.COORD_NORM][np.newaxis]

        ges_data = _shared_bla.handcrafted_features(coord_norm)
        features = np.concatenate(
            (
                ges_data[_PG.BONE_LENGTH],
                ges_data[_PG.BONE_ANGLE_COS],
                ges_data[_PG.BONE_ANGLE_SIN],
            ),
            axis=1,
        )
        features = features[np.newaxis].transpose((1, 0, 2))
        features = torch.from_numpy(features).float().to(_shared_lstm.device)

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
    """视频序列推理: 保持 LSTM 状态"""
    import torch
    from constants.enum_keys import PG as _PG

    old_cwd = os.getcwd()
    os.chdir(str(_CTPGR_DIR))
    try:
        p_res = _shared_pose.get_coordinates(img_bgr)
        coord_norm = p_res[_PG.COORD_NORM][np.newaxis]

        ges_data = _shared_bla.handcrafted_features(coord_norm)
        features = np.concatenate(
            (
                ges_data[_PG.BONE_LENGTH],
                ges_data[_PG.BONE_ANGLE_COS],
                ges_data[_PG.BONE_ANGLE_SIN],
            ),
            axis=1,
        )
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


# ═══════════════════════════════════════════════════════════════
#  Stream state management
# ═══════════════════════════════════════════════════════════════

_stream_states: dict[str, tuple] = {}


def reset_stream_state(stream_id: str = "default") -> None:
    """重置摄像头的 LSTM 流状态"""
    _stream_states.pop(stream_id, None)


# ═══════════════════════════════════════════════════════════════
#  Post-processing (smoothing, segmentation, voting)
# ═══════════════════════════════════════════════════════════════

def _scores_to_probs(scores_arr):
    import torch
    import torch.nn.functional as F

    t = torch.from_numpy(scores_arr).float() if isinstance(scores_arr, np.ndarray) else scores_arr.float()
    probs = F.softmax(t, dim=-1)
    return probs.tolist() if hasattr(probs, "tolist") else list(probs)


def _smooth_frame_results(frame_results: list[dict]) -> list[dict]:
    if not frame_results:
        return []

    half_window = SMOOTH_WINDOW // 2
    smoothed = []
    for idx, fr in enumerate(frame_results):
        left = max(0, idx - half_window)
        right = min(len(frame_results), idx + half_window + 1)
        window = frame_results[left:right]
        votes: dict[int, int] = {}
        confs: dict[int, float] = {}
        for item in window:
            gid = item["gestureId"]
            votes[gid] = votes.get(gid, 0) + 1
            confs[gid] = confs.get(gid, 0.0) + item["confidence"]

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
                    segments.append(
                        {
                            "start": seg_start["time"],
                            "end": end_time,
                            "gesture": GESTURE_NAMES_CN[seg_gesture],
                            "gestureId": seg_gesture,
                        }
                    )
            seg_start = fr
            seg_gesture = gid

    if seg_start is not None and seg_gesture is not None and seg_gesture > 0:
        if last_time - seg_start["time"] >= MIN_SEGMENT_SECONDS:
            segments.append(
                {
                    "start": seg_start["time"],
                    "end": last_time,
                    "gesture": GESTURE_NAMES_CN[seg_gesture],
                    "gestureId": seg_gesture,
                }
            )

    return segments


def _vote_best_gesture(frame_results: list[dict]) -> tuple[int, float, list[dict]]:
    valid_frames = frame_results[LSTM_WARMUP_FRAMES:] if len(frame_results) > LSTM_WARMUP_FRAMES else frame_results
    gesture_scores: dict[int, float] = {}
    gesture_counts: dict[int, int] = {}

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
        raise ValueError("无法读取视频")

    target_sample_fps = min(VIDEO_SAMPLE_FPS, fps) if fps > 0 else VIDEO_SAMPLE_FPS
    sample_interval = max(1, int(round(fps / target_sample_fps))) if fps > 0 else 1
    duration = total_frames / fps if fps > 0 else 0
    return total_frames, fps, target_sample_fps, sample_interval, duration


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


# ═══════════════════════════════════════════════════════════════
#  FFmpeg / Transcoding utilities
# ═══════════════════════════════════════════════════════════════

def _ffmpeg_path() -> Optional[str]:
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


def remove_files(paths: list[str]):
    """清理临时文件"""
    for path in paths:
        try:
            if path and Path(path).exists():
                os.unlink(path)
        except OSError:
            logger.warning("临时文件清理失败: %s", path)


def transcode_browser_preview(input_path: str, output_path: str):
    """将视频转为浏览器兼容的 H.264 MP4"""
    ffmpeg_bin = _ffmpeg_path()
    if not ffmpeg_bin:
        raise RuntimeError("后端未找到 FFmpeg。请安装 ffmpeg 或安装 Python 依赖 imageio-ffmpeg 后重启服务。")

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
        raise RuntimeError("预览视频转码超时，请尝试更短的视频")

    if completed.returncode != 0 or not Path(output_path).is_file():
        detail = completed.stderr.strip() or "FFmpeg 转码失败"
        raise RuntimeError(f"预览视频转码失败: {detail}")


# ═══════════════════════════════════════════════════════════════
#  SSE event formatting
# ═══════════════════════════════════════════════════════════════

def _sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


# ═══════════════════════════════════════════════════════════════
#  Image processing
# ═══════════════════════════════════════════════════════════════

def process_police_gesture_image(contents: bytes, timestamp: Optional[int] = None) -> dict:
    """处理单张图片，返回识别结果"""
    import torch.nn.functional as F
    import torch as _torch

    if timestamp is None:
        timestamp = int(time.time() * 1000)

    try:
        image = Image.open(io.BytesIO(contents))
        if image.mode != "RGB":
            image = image.convert("RGB")
    except Exception:
        raise ValueError("无法解析图片文件")

    img_array = np.array(image)
    img_bgr = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)

    start = time.time()
    gesture_id, scores_arr = predict_single_frame(img_bgr)
    elapsed = time.time() - start

    if isinstance(scores_arr, np.ndarray):
        t = _torch.from_numpy(scores_arr).float()
    else:
        t = scores_arr.float()
    probs = F.softmax(t, dim=-1)
    scores = probs.tolist() if hasattr(probs, "tolist") else list(probs)

    gesture_cn = GESTURE_NAMES_CN[gesture_id] if gesture_id < len(GESTURE_NAMES_CN) else "未知"
    confidence = float(scores[gesture_id]) if gesture_id < len(scores) else 0.0

    top5 = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)[:5]
    top5_list = [
        {
            "gesture": GESTURE_NAMES_CN[i] if i < len(GESTURE_NAMES_CN) else "未知",
            "gestureId": i,
            "confidence": round(s, 4),
        }
        for i, s in top5
    ]

    logger.info(
        "交警手势图片识别: %s (置信度 %.1f%%, %.0fms)",
        gesture_cn,
        confidence * 100,
        elapsed * 1000,
    )

    # 异步写入云数据库日志
    log_gesture_async(
        GestureLogEntry(
            recognition_type="image",
            gesture=gesture_cn,
            gesture_id=gesture_id,
            confidence=round(confidence, 4),
            inference_ms=round(elapsed * 1000, 1),
            top5_json=build_top5_json(top5_list),
        )
    )

    return {
        "code": 200,
        "message": "success",
        "data": {
            "gesture": gesture_cn,
            "gestureId": gesture_id,
            "confidence": round(confidence, 4),
            "timestamp": timestamp,
            "top5": top5_list,
            "inference_ms": round(elapsed * 1000, 1),
        },
    }


# ═══════════════════════════════════════════════════════════════
#  Video processing
# ═══════════════════════════════════════════════════════════════

def process_police_gesture_video(contents: bytes, file_ext: str, timestamp: Optional[int] = None, filename: Optional[str] = None) -> dict:
    """处理视频文件，返回逐帧识别结果"""
    if timestamp is None:
        timestamp = int(time.time() * 1000)

    video_session_id = str(uuid.uuid4())  # 本次视频的唯一标识

    with tempfile.NamedTemporaryFile(suffix=file_ext, delete=False) as tmp:
        tmp.write(contents)
        tmp_path = tmp.name

    try:
        cap = cv2.VideoCapture(tmp_path)
        total_frames, fps, target_sample_fps, sample_interval, duration = _video_meta(cap)
        logger.info(
            "交警手势视频推理: %d帧, fps=%.1f, 采样间隔=%d",
            total_frames,
            fps,
            sample_interval,
        )

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
                frame_results.append(
                    {
                        "frame": frame_idx,
                        "time": round(frame_seconds, 2),
                        "gesture": GESTURE_NAMES_CN[gesture_id] if gesture_id < len(GESTURE_NAMES_CN) else "未知",
                        "gestureId": gesture_id,
                        "confidence": round(confidence, 4),
                    }
                )
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
        logger.info(
            "交警手势视频识别: %s (%d帧, %d个手势段, %.0fms)",
            result["gesture"],
            processed,
            len(result["segments"]),
            elapsed * 1000,
        )

        # 异步写入云数据库日志: 每个手势段单独记录一条
        segments = result.get("segments", [])
        if segments:
            segment_entries = [
                GestureLogEntry(
                    recognition_type="video",
                    gesture=seg["gesture"],
                    gesture_id=seg["gestureId"],
                    confidence=result["confidence"],
                    inference_ms=round(elapsed * 1000, 1),
                    filename=filename,
                    video_session_id=video_session_id,
                    top5_json=build_top5_json(result.get("top5", [])),
                    frames_total=total_frames,
                    frames_processed=processed,
                    video_fps=round(fps, 1),
                    video_duration=round(duration, 1),
                    segments_json=build_segments_json([seg]),
                )
                for seg in segments
            ]
            log_gestures_batch_async(segment_entries)
        else:
            # 没有手势段时仍记录一条汇总日志
            log_gesture_async(
                GestureLogEntry(
                    recognition_type="video",
                    gesture=result["gesture"],
                    gesture_id=result["gestureId"],
                    confidence=result["confidence"],
                    inference_ms=round(elapsed * 1000, 1),
                    filename=filename,
                    video_session_id=video_session_id,
                    top5_json=build_top5_json(result.get("top5", [])),
                    frames_total=total_frames,
                    frames_processed=processed,
                    video_fps=round(fps, 1),
                    video_duration=round(duration, 1),
                    segments_json=build_segments_json([]),
                )
            )

        return {"code": 200, "message": "success", "data": result}
    finally:
        os.unlink(tmp_path)


# ═══════════════════════════════════════════════════════════════
#  Video stream processing (SSE generator)
# ═══════════════════════════════════════════════════════════════

def generate_police_gesture_video_stream(contents: bytes, file_ext: str, filename: Optional[str] = None) -> Generator[str, None, None]:
    """视频流式识别生成器: 边分析边产生 SSE 事件"""
    timestamp = int(time.time() * 1000)
    video_session_id = str(uuid.uuid4())  # 本次视频的唯一标识

    with tempfile.NamedTemporaryFile(suffix=file_ext, delete=False) as tmp:
        tmp.write(contents)
        tmp_path = tmp.name

    cap = None
    try:
        cap = cv2.VideoCapture(tmp_path)
        total_frames, fps, target_sample_fps, sample_interval, duration = _video_meta(cap)
        logger.info(
            "交警手势流式视频推理: %d帧, fps=%.1f, 采样间隔=%d",
            total_frames,
            fps,
            sample_interval,
        )

        yield _sse_event(
            "meta",
            {
                "timestamp": timestamp,
                "frames_total": total_frames,
                "video_duration": round(duration, 1),
                "video_fps": round(fps, 1),
                "sample_fps": round(target_sample_fps, 1),
                "sample_interval": sample_interval,
            },
        )

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
                yield _sse_event(
                    "frame",
                    {
                        **_with_display_time(frame_result),
                        "frames_processed": processed,
                        "progress": round(min(99, (frame_idx + 1) / total_frames * 100), 1),
                    },
                )

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
            "交警手势流式视频识别完成: %s (%d帧, %d个手势段, %.0fms)",
            result["gesture"],
            processed,
            len(result["segments"]),
            elapsed * 1000,
        )

        # 异步写入云数据库日志: 每个手势段单独记录一条
        segments = result.get("segments", [])
        if segments:
            segment_entries = [
                GestureLogEntry(
                    recognition_type="video_stream",
                    gesture=seg["gesture"],
                    gesture_id=seg["gestureId"],
                    confidence=result["confidence"],
                    inference_ms=round(elapsed * 1000, 1),
                    filename=filename,
                    video_session_id=video_session_id,
                    top5_json=build_top5_json(result.get("top5", [])),
                    frames_total=total_frames,
                    frames_processed=processed,
                    video_fps=round(fps, 1),
                    video_duration=round(duration, 1),
                    segments_json=build_segments_json([seg]),
                )
                for seg in segments
            ]
            log_gestures_batch_async(segment_entries)
        else:
            log_gesture_async(
                GestureLogEntry(
                    recognition_type="video_stream",
                    gesture=result["gesture"],
                    gesture_id=result["gestureId"],
                    confidence=result["confidence"],
                    inference_ms=round(elapsed * 1000, 1),
                    filename=filename,
                    video_session_id=video_session_id,
                    top5_json=build_top5_json(result.get("top5", [])),
                    frames_total=total_frames,
                    frames_processed=processed,
                    video_fps=round(fps, 1),
                    video_duration=round(duration, 1),
                    segments_json=build_segments_json([]),
                )
            )

        yield _sse_event("done", result)
    except Exception as e:
        logger.exception("交警手势流式视频识别失败: %s", e)
        # 异步写入失败日志到云数据库
        log_gesture_async(
            GestureLogEntry(
                recognition_type="video_stream",
                gesture="未知",
                gesture_id=-1,
                confidence=0.0,
                inference_ms=0.0,
                success=False,
                filename=filename,
                video_session_id=video_session_id,
                error_message=str(e),
            )
        )
        yield _sse_event("error", {"message": str(e)})
    finally:
        if cap is not None:
            cap.release()
        os.unlink(tmp_path)


# ═══════════════════════════════════════════════════════════════
#  Stream frame processing (realtime camera)
# ═══════════════════════════════════════════════════════════════

def process_stream_frame(contents: bytes, stream_id: str = "default") -> dict:
    """处理实时摄像头的单帧图像"""
    import torch as _torch
    import torch.nn.functional as F

    try:
        image = Image.open(io.BytesIO(contents))
        if image.mode != "RGB":
            image = image.convert("RGB")
    except Exception:
        raise ValueError("无法解析摄像头帧")

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

    if isinstance(scores_arr, np.ndarray):
        t = _torch.from_numpy(scores_arr).float()
    else:
        t = scores_arr.float()
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

    # 注意: 摄像头流每帧都写日志会产生大量数据,
    # 此处仅在检测到有效手势 (gesture_id > 0) 时写入云数据库
    if gesture_id > 0:
        log_gesture_async(
            GestureLogEntry(
                recognition_type="camera_stream",
                gesture=gesture_cn,
                gesture_id=gesture_id,
                confidence=round(confidence, 4),
                inference_ms=round(elapsed * 1000, 1),
                top5_json=build_top5_json(top5_list),
            )
        )

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
