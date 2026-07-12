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
from app.services.record_service import build_gesture_summary
from app.services.police_officer_detector import PoliceOfficerDetection, detect_police_officer
from app.services.police_gesture_logger import (
    GESTURE_LOG_LEVEL,
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
POLICE_RECOGNITION_MODE = os.getenv("CARMATE_POLICE_RECOGNITION_MODE", "all").lower()
POLICE_ONLY_DETECT_INTERVAL = max(1, _env_int("CARMATE_POLICE_ONLY_DETECT_INTERVAL", 3))
POLICE_ONLY_CONFIRM_FRAMES = max(1, _env_int("CARMATE_POLICE_ONLY_CONFIRM_FRAMES", 3))
POLICE_ONLY_LOSE_DETECTIONS = max(1, _env_int("CARMATE_POLICE_ONLY_LOSE_DETECTIONS", 2))
POLICE_ONLY_HOLD_FRAMES = max(1, _env_int("CARMATE_POLICE_ONLY_HOLD_FRAMES", 8))
POLICE_ONLY_TRACK_PAD_RATIO = max(0.05, _env_float("CARMATE_POLICE_ONLY_TRACK_PAD_RATIO", 0.30))


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


def unletterbox_keypoints(coord_norm: np.ndarray, original_shape, target_size=(512, 512)) -> np.ndarray:
    """Map normalized keypoints from the padded inference canvas back to the original frame."""
    arr = np.asarray(coord_norm, dtype=np.float32).copy()
    if arr.ndim != 2 or arr.shape[0] != 2:
        return arr

    img_h, img_w = original_shape[:2]
    target_w, target_h = target_size
    if img_w <= 0 or img_h <= 0:
        return arr

    scale = min(target_w / img_w, target_h / img_h)
    resized_w = max(1, int(round(img_w * scale)))
    resized_h = max(1, int(round(img_h * scale)))
    left = (target_w - resized_w) / 2.0
    top = (target_h - resized_h) / 2.0

    x = (arr[0] * target_w - left) / max(scale, 1e-6)
    y = (arr[1] * target_h - top) / max(scale, 1e-6)
    arr[0] = np.clip(x / img_w, 0.0, 1.0)
    arr[1] = np.clip(y / img_h, 0.0, 1.0)
    return arr


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
        coord_norm_2d = p_res[_PG.COORD_NORM]  # shape (2, 14) — for API serialization
        coord_norm = coord_norm_2d[np.newaxis]

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
        return gesture_id, scores_arr, (h.detach(), c.detach()), coord_norm_2d
    finally:
        os.chdir(old_cwd)


def _coord_pose_quality(coord_norm: np.ndarray) -> dict:
    coords = np.asarray(coord_norm)
    if coords.ndim != 2:
        return {
            "score": 0.0,
            "valid": False,
            "validKeypoints": 0,
            "validUpperKeypoints": 0,
            "validArmKeypoints": 0,
            "bboxArea": 0.0,
        }

    if coords.shape[0] == 2:
        xy = coords.T
    elif coords.shape[1] >= 2:
        xy = coords[:, :2]
    else:
        return {
            "score": 0.0,
            "valid": False,
            "validKeypoints": 0,
            "validUpperKeypoints": 0,
            "validArmKeypoints": 0,
            "bboxArea": 0.0,
        }

    valid_mask = (
        np.isfinite(xy[:, 0])
        & np.isfinite(xy[:, 1])
        & (xy[:, 0] > 0.01)
        & (xy[:, 1] > 0.01)
        & (xy[:, 0] < 0.99)
        & (xy[:, 1] < 0.99)
    )

    # AI Challenger order: shoulders/elbows/wrists + neck are most important for police gestures.
    upper_indices = [0, 1, 2, 3, 4, 5, 13]
    arm_indices = [0, 1, 2, 3, 4, 5]
    upper_indices = [idx for idx in upper_indices if idx < len(valid_mask)]
    arm_indices = [idx for idx in arm_indices if idx < len(valid_mask)]

    valid_points = xy[valid_mask]
    if valid_points.size:
        min_xy = valid_points.min(axis=0)
        max_xy = valid_points.max(axis=0)
        bbox_area = float(max(0.0, max_xy[0] - min_xy[0]) * max(0.0, max_xy[1] - min_xy[1]))
    else:
        bbox_area = 0.0

    valid_upper = int(valid_mask[upper_indices].sum()) if upper_indices else 0
    valid_arm = int(valid_mask[arm_indices].sum()) if arm_indices else 0
    upper_ratio = valid_upper / max(1, len(upper_indices))
    arm_ratio = valid_arm / max(1, len(arm_indices))
    area_score = min(1.0, bbox_area / 0.08)
    score = 0.5 * upper_ratio + 0.4 * arm_ratio + 0.1 * area_score

    return {
        "score": round(float(score), 4),
        "valid": bool(score >= STREAM_POSE_MIN_QUALITY and valid_upper >= 3 and valid_arm >= 2),
        "validKeypoints": int(valid_mask.sum()),
        "validUpperKeypoints": valid_upper,
        "validArmKeypoints": valid_arm,
        "bboxArea": round(bbox_area, 4),
    }


def predict_stream_frame_candidate(
    img_bgr: np.ndarray,
    state,
    fallback_coord_norm_2d: np.ndarray | None = None,
):
    """Realtime stream inference with pose-quality gating.

    Bad pose frames are not fed into the LSTM, which prevents one blurry or
    cropped frame from poisoning the sequence state.
    """
    import torch
    from constants.enum_keys import PG as _PG

    old_cwd = os.getcwd()
    os.chdir(str(_CTPGR_DIR))
    try:
        p_res = _shared_pose.get_coordinates(img_bgr)
        coord_norm_2d = p_res[_PG.COORD_NORM]  # shape (2, 14) — for API serialization
        pose_quality = _coord_pose_quality(coord_norm_2d)
        if not pose_quality["valid"] and fallback_coord_norm_2d is not None:
            fallback_quality = _coord_pose_quality(fallback_coord_norm_2d)
            if fallback_quality["valid"]:
                coord_norm_2d = fallback_coord_norm_2d
                pose_quality = {
                    **fallback_quality,
                    "imputed": True,
                    "source": "last_valid_pose",
                }
        if not pose_quality["valid"]:
            scores_arr = np.zeros(len(GESTURE_NAMES_CN), dtype=np.float32)
            scores_arr[0] = 1.0
            return 0, scores_arr, state, pose_quality, False, coord_norm_2d

        coord_norm = coord_norm_2d[np.newaxis]
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
        return gesture_id, scores_arr, (h.detach(), c.detach()), pose_quality, True, coord_norm_2d
    finally:
        os.chdir(old_cwd)


# ═══════════════════════════════════════════════════════════════
#  Stream state management
# ═══════════════════════════════════════════════════════════════

_stream_states: dict[str, tuple] = {}          # LSTM 隐藏状态
_stream_histories: dict[str, list[dict]] = {}  # 帧历史缓冲区 (用于平滑/分段)
_stream_segments: dict[str, list[dict]] = {}   # 已确认的手势段列表
_stream_frame_count: dict[str, int] = {}       # 流已处理的帧计数
_stream_start_times: dict[str, float] = {}     # 流开始时间
_stream_stable_results: dict[str, dict] = {}   # 当前稳定输出
_stream_candidates: dict[str, dict] = {}       # 等待确认的候选输出
_stream_stats: dict[str, dict] = {}            # 推理耗时统计 (用于周期性日志输出)
_stream_pose_skip_counters: dict[str, int] = {}  # 姿势质量不足跳过计数 (用于节流日志)
_stream_police_detections: dict[str, dict] = {}  # YOLO-World gate cache for police-only mode
_stream_last_valid_pose: dict[str, dict] = {}     # 最近一次有效姿态，用于短时补帧


def is_police_only_mode(police_only: Optional[bool] = None) -> bool:
    if police_only is not None:
        return bool(police_only)
    return POLICE_RECOGNITION_MODE in {"police_only", "traffic_police_only", "police"}


def reset_stream_state(stream_id: str = "default") -> None:
    """重置摄像头的 LSTM 流状态"""
    _stream_states.pop(stream_id, None)
    _stream_histories.pop(stream_id, None)
    _stream_segments.pop(stream_id, None)
    _stream_frame_count.pop(stream_id, None)
    _stream_start_times.pop(stream_id, None)
    _stream_stable_results.pop(stream_id, None)
    _stream_candidates.pop(stream_id, None)
    _stream_stats.pop(stream_id, None)
    _stream_pose_skip_counters.pop(stream_id, None)
    _stream_police_detections.pop(stream_id, None)
    _stream_last_valid_pose.pop(stream_id, None)


def _police_detection_payload(
    detection: PoliceOfficerDetection | None,
    police_only: bool,
    image_shape=None,
    *,
    confirmed: bool = False,
    streak: int = 0,
    required_frames: int = POLICE_ONLY_CONFIRM_FRAMES,
) -> dict:
    payload = {
        "policeOnly": bool(police_only),
        "policeConfirmed": bool(confirmed),
        "policeConfirmStreak": int(streak),
        "policeRequiredConfirmFrames": int(required_frames),
    }
    if detection is not None:
        payload.update(detection.to_dict())
        payload["policeCandidateDetected"] = bool(detection.detected)
        payload["policeDetected"] = bool(confirmed)
        if detection.box and image_shape is not None:
            img_h, img_w = image_shape[:2]
            if img_w > 0 and img_h > 0:
                x1, y1, x2, y2 = detection.box
                payload["policeBoxNorm"] = [
                    round(max(0.0, min(1.0, float(x1) / img_w)), 4),
                    round(max(0.0, min(1.0, float(y1) / img_h)), 4),
                    round(max(0.0, min(1.0, float(x2) / img_w)), 4),
                    round(max(0.0, min(1.0, float(y2) / img_h)), 4),
                ]
    return payload


def _create_tracker_with_fallback(img_bgr: np.ndarray, box_xyxy: list[float]):
    factories = []
    legacy = getattr(cv2, "legacy", None)
    if legacy is not None:
        for name in ("TrackerCSRT_create", "TrackerKCF_create", "TrackerMOSSE_create"):
            factory = getattr(legacy, name, None)
            if callable(factory):
                factories.append(factory)
    for name in ("TrackerCSRT_create", "TrackerKCF_create", "TrackerMOSSE_create"):
        factory = getattr(cv2, name, None)
        if callable(factory):
            factories.append(factory)

    x1, y1, x2, y2 = [float(v) for v in box_xyxy]
    w = max(1.0, x2 - x1)
    h = max(1.0, y2 - y1)
    for factory in factories:
        try:
            tracker = factory()
            ok = tracker.init(img_bgr, (x1, y1, w, h))
            if ok is False:
                continue
            return tracker
        except Exception:
            continue
    return None


def _update_tracker_box(tracker, img_bgr: np.ndarray) -> list[float] | None:
    if tracker is None:
        return None
    try:
        ok, bbox = tracker.update(img_bgr)
    except Exception:
        return None
    if not ok or bbox is None:
        return None
    x, y, w, h = [float(v) for v in bbox]
    if w <= 1.0 or h <= 1.0:
        return None
    return [x, y, x + w, y + h]


def _expand_box_to_crop(
    img_bgr: np.ndarray,
    box_xyxy: list[float],
    image_shape,
    pad_ratio: float = POLICE_ONLY_TRACK_PAD_RATIO,
) -> tuple[np.ndarray, tuple[int, int, int, int]] | tuple[None, None]:
    if not box_xyxy or image_shape is None:
        return None, None
    img_h, img_w = image_shape[:2]
    if img_w <= 0 or img_h <= 0:
        return None, None
    x1, y1, x2, y2 = [float(v) for v in box_xyxy]
    bw = max(1.0, x2 - x1)
    bh = max(1.0, y2 - y1)
    pad_x = bw * pad_ratio
    pad_y = bh * pad_ratio
    left = max(0, int(np.floor(x1 - pad_x)))
    top = max(0, int(np.floor(y1 - pad_y)))
    right = min(img_w, int(np.ceil(x2 + pad_x)))
    bottom = min(img_h, int(np.ceil(y2 + pad_y)))
    if right - left < 2 or bottom - top < 2:
        return None, None
    crop = img_bgr[top:bottom, left:right]
    if crop is None or crop.size == 0:
        return None, None
    return crop, (left, top, right, bottom)


def _remap_keypoints_from_crop(coord_norm: np.ndarray, crop_box: tuple[int, int, int, int] | None, image_shape) -> np.ndarray:
    if crop_box is None:
        return coord_norm
    arr = np.asarray(coord_norm, dtype=np.float32).copy()
    if arr.ndim != 2 or arr.shape[0] != 2 or image_shape is None:
        return arr
    img_h, img_w = image_shape[:2]
    if img_w <= 0 or img_h <= 0:
        return arr
    left, top, right, bottom = crop_box
    crop_w = max(1.0, float(right - left))
    crop_h = max(1.0, float(bottom - top))
    abs_x = left + arr[0] * crop_w
    abs_y = top + arr[1] * crop_h
    arr[0] = np.clip(abs_x / img_w, 0.0, 1.0)
    arr[1] = np.clip(abs_y / img_h, 0.0, 1.0)
    return arr


def _default_police_detection_state(frame_count: int = 0) -> dict:
    return {
        "frame": frame_count,
        "raw_detection": None,
        "display_detection": None,
        "confirmed_detection": None,
        "streak": 0,
        "miss_streak": 0,
        "confirmed_until_frame": 0,
        "confirmed": False,
        "tracked_box": None,
        "tracker": None,
        "tracker_miss_streak": 0,
    }


def _refresh_police_detection_state(
    state: dict | None,
    img_bgr: np.ndarray,
    frame_count: int,
    police_only: bool,
) -> dict | None:
    if not police_only:
        return None

    cached = dict(state) if state else _default_police_detection_state(frame_count)
    should_detect = cached["raw_detection"] is None or frame_count % POLICE_ONLY_DETECT_INTERVAL == 1
    confirmed = bool(cached.get("confirmed", False))
    streak = int(cached.get("streak", 0))
    miss_streak = int(cached.get("miss_streak", 0))
    confirmed_detection = cached.get("confirmed_detection")
    confirmed_until_frame = int(cached.get("confirmed_until_frame", 0))
    tracker = cached.get("tracker")
    tracked_box = cached.get("tracked_box")
    tracker_miss_streak = int(cached.get("tracker_miss_streak", 0))
    raw_detection = cached.get("raw_detection")
    display_detection = None

    detection = detect_police_officer(img_bgr) if should_detect else None
    if detection is not None:
        raw_detection = detection

    if detection is not None and detection.detected:
        previous_raw_detected = bool(cached.get("raw_detection") and cached["raw_detection"].detected)
        streak = streak + 1 if previous_raw_detected else 1
        miss_streak = 0
        tracked_box = detection.box or tracked_box
        if detection.box is not None:
            tracker = _create_tracker_with_fallback(img_bgr, detection.box)
            tracker_miss_streak = 0
        if not confirmed and streak >= POLICE_ONLY_CONFIRM_FRAMES:
            confirmed = True
            confirmed_detection = detection
            confirmed_until_frame = frame_count + POLICE_ONLY_HOLD_FRAMES
        elif confirmed:
            confirmed_detection = detection
            confirmed_until_frame = max(confirmed_until_frame, frame_count + POLICE_ONLY_HOLD_FRAMES)
    else:
        streak = 0 if detection is not None else streak
        miss_streak = miss_streak + 1 if detection is not None else miss_streak
        if confirmed and tracker is not None:
            updated_box = _update_tracker_box(tracker, img_bgr)
            if updated_box is not None:
                tracked_box = updated_box
                tracker_miss_streak = 0
            else:
                tracker_miss_streak += 1
        elif confirmed and tracked_box is not None:
            tracker_miss_streak += 1

        if confirmed and confirmed_detection is not None and tracked_box is not None and (
            frame_count <= confirmed_until_frame
            or miss_streak < POLICE_ONLY_LOSE_DETECTIONS
            or tracker_miss_streak <= POLICE_ONLY_HOLD_FRAMES
        ):
            display_detection = confirmed_detection
            display_detection.box = [round(float(v), 2) for v in tracked_box]
        else:
            confirmed = False
            confirmed_detection = None
            if tracker_miss_streak > POLICE_ONLY_HOLD_FRAMES:
                tracked_box = None
                tracker = None

    if display_detection is None:
        if detection is not None and detection.detected:
            display_detection = detection
        elif confirmed and confirmed_detection is not None and tracked_box is not None:
            display_detection = confirmed_detection
            display_detection.box = [round(float(v), 2) for v in tracked_box]
        else:
            display_detection = detection

    cached.update({
        "frame": frame_count,
        "raw_detection": raw_detection,
        "display_detection": display_detection,
        "confirmed_detection": confirmed_detection,
        "streak": streak,
        "miss_streak": miss_streak,
        "confirmed_until_frame": confirmed_until_frame,
        "confirmed": confirmed,
        "tracked_box": tracked_box,
        "tracker": tracker,
        "tracker_miss_streak": tracker_miss_streak,
    })
    return cached


def _stream_police_detection(
    stream_id: str,
    img_bgr: np.ndarray,
    frame_count: int,
    police_only: bool,
) -> dict | None:
    if not police_only:
        return None

    cached = _stream_police_detections.get(stream_id)
    cached = _refresh_police_detection_state(cached, img_bgr, frame_count, police_only)
    if cached is not None:
        _stream_police_detections[stream_id] = cached
    return cached


def _prepare_police_pose_source(
    img_bgr: np.ndarray,
    police_detection: PoliceOfficerDetection | None,
) -> tuple[np.ndarray, tuple[int, int, int, int] | None]:
    if police_detection is None or not police_detection.box:
        return img_bgr, None
    cropped, crop_box = _expand_box_to_crop(img_bgr, police_detection.box, img_bgr.shape)
    if cropped is None or crop_box is None:
        return img_bgr, None
    return cropped, crop_box


def _write_stream_recognition_record(
    *,
    record_type: str,
    source_type: str,
    success: bool,
    summary: str,
    result: dict | None = None,
    file_name: str | None = None,
    session_id: str | None = None,
) -> None:
    """同步写入 RecognitionRecord (用于流式端点, 使用独立 Session)"""
    import json as _json
    from app.core.database import SessionLocal
    from app.models.db_models import HistoryRecord, RecognitionRecord

    db = SessionLocal()
    try:
        payload: dict = {}
        if isinstance(result, dict):
            payload = dict(result)
        payload.pop("frames", None)
        payload.pop("segments", None)
        if file_name:
            payload["fileName"] = file_name
        if source_type:
            payload["sourceType"] = source_type
        if session_id:
            payload["sessionId"] = session_id
        payload["success"] = success
        payload["summary"] = summary

        history = HistoryRecord(
            type=record_type,
            session_id=session_id,
            image_url="",
            result_json=_json.dumps(payload, ensure_ascii=False) if payload else None,
        )
        db.add(history)
        db.flush()

        confidence = None
        if isinstance(result, dict):
            confidence = result.get("confidence")

        db.add(
            RecognitionRecord(
                type=record_type,
                result_summary=summary[:255] if summary else None,
                confidence=float(confidence) if confidence is not None else None,
                success=success,
            )
        )
        db.commit()
        logger.debug("流式识别 RecognitionRecord 已写入: type=%s, summary=%s", record_type, summary)
    except Exception as exc:
        db.rollback()
        logger.warning("流式识别 RecognitionRecord 写入失败 (非致命): %s", exc)
    finally:
        db.close()


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
#  Keypoint serialization
# ═══════════════════════════════════════════════════════════════

def _keypoints_to_list(coord_norm) -> list:
    """Convert (2, N) ndarray of normalized keypoints to a JSON-safe list of [x, y] pairs.

    Returns an empty list when input is None or degenerate, so callers never
    have to guard against None.
    """
    if coord_norm is None:
        return []
    arr = np.asarray(coord_norm)
    if arr.ndim != 2 or arr.shape[0] != 2:
        return []
    return [[round(float(v), 4) for v in row] for row in arr.T]


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

def process_police_gesture_video(
    contents: bytes,
    file_ext: str,
    timestamp: Optional[int] = None,
    filename: Optional[str] = None,
    police_only: Optional[bool] = None,
) -> dict:
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
        police_state: dict | None = None
        police_only_enabled = is_police_only_mode(police_only)
        lstm_state = (_shared_lstm.h0(), _shared_lstm.c0())

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            if frame_idx % sample_interval == 0:
                sample_index = processed + 1
                police_state = _refresh_police_detection_state(police_state, frame, sample_index, police_only_enabled)
                police_detection = police_state["display_detection"] if police_state else None
                police_confirmed = bool(police_state and police_state["confirmed"])
                police_streak = int(police_state["streak"]) if police_state else 0

                if police_only_enabled and not police_confirmed:
                    frame_seconds = frame_idx / fps if fps > 0 else 0
                    frame_results.append(
                        {
                            "frame": frame_idx,
                            "time": round(frame_seconds, 2),
                            "gesture": GESTURE_NAMES_CN[0],
                            "gestureId": 0,
                            "confidence": 0.0,
                            "keypoints": [],
                            **_police_detection_payload(police_detection, police_only_enabled, frame.shape, confirmed=police_confirmed, streak=police_streak),
                        }
                    )
                    processed += 1
                    frame_idx += 1
                    continue

                pose_src, pose_crop_box = _prepare_police_pose_source(
                    frame,
                    police_detection if police_only_enabled and police_confirmed else None,
                )
                re_frame = resize_keep_ratio(pose_src, (512, 512))
                gesture_id, scores_arr, lstm_state, coord_norm = predict_video_frame(re_frame, lstm_state)
                display_coord_norm = unletterbox_keypoints(coord_norm, pose_src.shape)
                display_coord_norm = _remap_keypoints_from_crop(display_coord_norm, pose_crop_box, frame.shape)
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
                        "keypoints": _keypoints_to_list(display_coord_norm),
                        **_police_detection_payload(police_detection, police_only_enabled, frame.shape, confirmed=police_confirmed, streak=police_streak),
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
        result["policeOnly"] = police_only_enabled
        result["policeDetectionInterval"] = POLICE_ONLY_DETECT_INTERVAL if police_only_enabled else None
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

def generate_police_gesture_video_stream(
    contents: bytes,
    file_ext: str,
    filename: Optional[str] = None,
    police_only: Optional[bool] = None,
) -> Generator[str, None, None]:
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
        police_state: dict | None = None
        police_only_enabled = is_police_only_mode(police_only)
        lstm_state = (_shared_lstm.h0(), _shared_lstm.c0())

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            if frame_idx % sample_interval == 0:
                sample_index = processed + 1
                police_state = _refresh_police_detection_state(police_state, frame, sample_index, police_only_enabled)
                police_detection = police_state["display_detection"] if police_state else None
                police_confirmed = bool(police_state and police_state["confirmed"])
                police_streak = int(police_state["streak"]) if police_state else 0

                if police_only_enabled and not police_confirmed:
                    frame_seconds = frame_idx / fps if fps > 0 else 0
                    frame_result = {
                        "frame": frame_idx,
                        "time": round(frame_seconds, 2),
                        "gesture": GESTURE_NAMES_CN[0],
                        "gestureId": 0,
                        "confidence": 0.0,
                        "keypoints": [],
                        **_police_detection_payload(police_detection, police_only_enabled, frame.shape, confirmed=police_confirmed, streak=police_streak),
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
                    continue

                pose_src, pose_crop_box = _prepare_police_pose_source(
                    frame,
                    police_detection if police_only_enabled and police_confirmed else None,
                )
                re_frame = resize_keep_ratio(pose_src, (512, 512))
                gesture_id, scores_arr, lstm_state, coord_norm = predict_video_frame(re_frame, lstm_state)
                display_coord_norm = unletterbox_keypoints(coord_norm, pose_src.shape)
                display_coord_norm = _remap_keypoints_from_crop(display_coord_norm, pose_crop_box, frame.shape)
                scores = _scores_to_probs(scores_arr)
                confidence = float(scores[gesture_id]) if gesture_id < len(scores) else 0.0
                frame_seconds = frame_idx / fps if fps > 0 else 0
                frame_result = {
                    "frame": frame_idx,
                    "time": round(frame_seconds, 2),
                    "gesture": GESTURE_NAMES_CN[gesture_id] if gesture_id < len(GESTURE_NAMES_CN) else "未知",
                    "gestureId": gesture_id,
                    "confidence": round(confidence, 4),
                    "keypoints": _keypoints_to_list(display_coord_norm),
                    **_police_detection_payload(police_detection, police_only_enabled, frame.shape, confirmed=police_confirmed, streak=police_streak),
                }
                frame_results.append(frame_result)
                processed += 1
                yield _sse_event(
                    "frame",
                    {
                        **_with_display_time(frame_result),
                        "frames_processed": processed,
                        "progress": round(min(99, (frame_idx + 1) / total_frames * 100), 1),
                        "keypoints": _keypoints_to_list(display_coord_norm),
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
        result["policeOnly"] = police_only_enabled
        result["policeDetectionInterval"] = POLICE_ONLY_DETECT_INTERVAL if police_only_enabled else None
        logger.info(
            "交警手势流式视频识别完成: %s (%d帧, %d个手势段, %.0fms)",
            result["gesture"],
            processed,
            len(result["segments"]),
            elapsed * 1000,
        )

        # 同步写入 RecognitionRecord (仪表盘统计依赖)
        _write_stream_recognition_record(
            record_type="police_gesture",
            source_type="video_stream",
            success=True,
            summary=build_gesture_summary(result),
            result=result,
            file_name=filename,
            session_id=video_session_id,
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
        # 同步写入失败的 RecognitionRecord
        _write_stream_recognition_record(
            record_type="police_gesture",
            source_type="video_stream",
            success=False,
            summary=f"识别失败: {e}",
            file_name=filename,
            session_id=video_session_id,
        )
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

# 流式帧处理参数
STREAM_HISTORY_MAX = 15       # 累积帧数 (~7.5s@500ms), 用于平滑分段
STREAM_SMOOTH_WINDOW = 3      # 平滑滑动窗口
STREAM_WARMUP_FRAMES = 10     # LSTM 预热帧数
STREAM_MIN_SEGMENT_FRAMES = 2  # 手势至少连续 N 帧才确认新段
STREAM_POSE_MIN_QUALITY = _env_float("CARMATE_STREAM_POSE_MIN_QUALITY", 0.45)
STREAM_MIN_CONFIDENCE = _env_float("CARMATE_STREAM_MIN_CONFIDENCE", 0.12)
STREAM_SWITCH_MIN_FRAMES = max(1, _env_int("CARMATE_STREAM_SWITCH_MIN_FRAMES", 1))
STREAM_KEEP_LAST_SECONDS = _env_float("CARMATE_STREAM_KEEP_LAST_SECONDS", 1.2)
STREAM_POSE_REUSE_FRAMES = max(0, _env_int("CARMATE_STREAM_POSE_REUSE_FRAMES", 2))


def _stream_smooth_vote(history: list[dict]) -> tuple[int, float]:
    """滑动窗口投票: 返回 (最佳手势ID, 平滑置信度)"""
    window = [
        item
        for item in history[-STREAM_SMOOTH_WINDOW:]
        if item.get("validPose", True)
    ]
    if not window:
        return 0, 0.0

    gesture_window = [
        item
        for item in window
        if item["gestureId"] > 0 and item["confidence"] >= STREAM_MIN_CONFIDENCE
    ]
    vote_window = gesture_window or [item for item in window if item["gestureId"] == 0]
    if not vote_window:
        return 0, 0.0

    votes: dict[int, int] = {}
    confs: dict[int, float] = {}
    for item in vote_window:
        gid = item["gestureId"]
        votes[gid] = votes.get(gid, 0) + 1
        confs[gid] = confs.get(gid, 0.0) + item["confidence"]
    best = max(votes, key=lambda g: (votes[g], confs[g] / votes[g]))
    return int(best), round(confs[best] / votes[best], 4)


def _stable_stream_result(stream_id: str, proposed_gid: int, proposed_conf: float, now: float, valid_pose: bool) -> tuple[int, float, bool]:
    stable = _stream_stable_results.get(stream_id)
    if not valid_pose:
        if stable and now - stable.get("updatedAt", now) <= STREAM_KEEP_LAST_SECONDS:
            return int(stable["gestureId"]), float(stable["confidence"]), False
        proposed_gid = 0
        proposed_conf = 0.0

    if proposed_gid > 0 and proposed_conf < STREAM_MIN_CONFIDENCE:
        if stable:
            return int(stable["gestureId"]), float(stable["confidence"]), False
        proposed_gid = 0
        proposed_conf = 0.0

    if stable is None:
        _stream_stable_results[stream_id] = {
            "gestureId": proposed_gid,
            "confidence": proposed_conf,
            "updatedAt": now,
        }
        _stream_candidates.pop(stream_id, None)
        return proposed_gid, proposed_conf, True

    stable_gid = int(stable["gestureId"])
    if proposed_gid == stable_gid:
        stable["confidence"] = proposed_conf
        stable["updatedAt"] = now
        _stream_candidates.pop(stream_id, None)
        return proposed_gid, proposed_conf, False

    candidate = _stream_candidates.get(stream_id)
    if candidate and candidate["gestureId"] == proposed_gid:
        candidate["count"] += 1
        candidate["confidence"] = max(float(candidate["confidence"]), proposed_conf)
    else:
        candidate = {"gestureId": proposed_gid, "confidence": proposed_conf, "count": 1}
        _stream_candidates[stream_id] = candidate

    if candidate["count"] >= STREAM_SWITCH_MIN_FRAMES:
        _stream_stable_results[stream_id] = {
            "gestureId": proposed_gid,
            "confidence": float(candidate["confidence"]),
            "updatedAt": now,
        }
        _stream_candidates.pop(stream_id, None)
        return proposed_gid, float(candidate["confidence"]), True

    return stable_gid, float(stable["confidence"]), False


def process_stream_frame(contents: bytes, stream_id: str = "default", police_only: Optional[bool] = None) -> dict:
    """处理实时摄像头的单帧图像

    改进策略:
    1. 双模推理: 仅预热期同时跑 LSTM + 单帧, 成熟后避免重复姿态推理
    2. 大帧缓冲: 累积 15 帧用于平滑和分段
    3. 视频级后处理: 复用 _build_segments 做段检测
    """
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

    now = time.time()
    now_ms = int(now * 1000)

    # ---- 帧计数 (用于预热判断) ----
    fc = _stream_frame_count.get(stream_id, 0) + 1
    _stream_frame_count[stream_id] = fc
    police_only_enabled = is_police_only_mode(police_only)
    police_state = _stream_police_detection(stream_id, img_bgr, fc, police_only_enabled)
    police_detection = police_state["display_detection"] if police_state else None
    police_confirmed = bool(police_state and police_state["confirmed"])
    police_streak = int(police_state["streak"]) if police_state else 0
    if police_only_enabled and not police_confirmed:
        return {
            "code": 200,
            "message": "success",
            "data": {
                "streamId": stream_id,
                "frameCount": fc,
                "gesture": GESTURE_NAMES_CN[0],
                "gestureId": 0,
                "confidence": 0.0,
                "timestamp": now_ms,
                "top5": [],
                "inference_ms": 0.0,
                "poseQuality": {"score": 0.0, "valid": False},
                "keypoints": [],
                "validPose": False,
                "history": [],
                "segments": _stream_segments.get(stream_id, []),
                "currentSegment": _stream_segments.get(stream_id, [])[-1] if _stream_segments.get(stream_id) else None,
                "segmentChanged": False,
                "stableChanged": False,
                "warmup": fc <= STREAM_WARMUP_FRAMES,
                **_police_detection_payload(police_detection, police_only_enabled, img_bgr.shape, confirmed=police_confirmed, streak=police_streak),
            },
        }

    # 首帧 & 入口日志 (DEBUG)
    if fc == 1:
        logger.info("实时流开始: stream_id=%s, 首帧大小=%dx%d", stream_id, img_array.shape[1], img_array.shape[0])
    else:
        logger.debug("实时流帧 #%d: stream_id=%s, size=%dx%d", fc, stream_id, img_array.shape[1], img_array.shape[0])

    # ---- LSTM 推理 ----
    inference_start = time.time()
    lstm_state = _stream_states.get(stream_id)
    if lstm_state is None:
        lstm_state = (_shared_lstm.h0(), _shared_lstm.c0())

    pose_source_img, pose_crop_box = _prepare_police_pose_source(
        img_bgr,
        police_detection if police_only_enabled and police_confirmed else None,
    )
    pose_source_key = "crop" if pose_crop_box is not None else "full"
    last_pose_entry = _stream_last_valid_pose.get(stream_id)
    last_pose_coord = last_pose_entry.get("coord") if last_pose_entry else None
    last_pose_age = int(last_pose_entry.get("age", 0)) if last_pose_entry else 0
    fallback_coord = (
        last_pose_coord
        if last_pose_entry is not None
        and last_pose_entry.get("source_key") == pose_source_key
        and last_pose_age <= STREAM_POSE_REUSE_FRAMES
        else None
    )
    re_frame = resize_keep_ratio(pose_source_img, (512, 512))
    lstm_gid, scores_arr, lstm_state, pose_quality, state_updated, coord_norm = predict_stream_frame_candidate(
        re_frame,
        lstm_state,
        fallback_coord_norm_2d=fallback_coord,
    )
    display_coord_norm = unletterbox_keypoints(coord_norm, pose_source_img.shape)
    display_coord_norm = _remap_keypoints_from_crop(display_coord_norm, pose_crop_box, img_bgr.shape)
    if state_updated:
        _stream_states[stream_id] = lstm_state
        _stream_last_valid_pose[stream_id] = {"coord": coord_norm, "age": 0, "source_key": pose_source_key}
    elif last_pose_entry is not None:
        last_pose_entry["age"] = last_pose_age + 1
        _stream_last_valid_pose[stream_id] = last_pose_entry

    if isinstance(scores_arr, np.ndarray):
        t = _torch.from_numpy(scores_arr).float()
    else:
        t = scores_arr.float()
    lstm_scores = F.softmax(t, dim=-1).tolist()
    lstm_conf = float(lstm_scores[lstm_gid]) if lstm_gid < len(lstm_scores) else 0.0
    if not state_updated:
        lstm_scores = [0.0] * len(GESTURE_NAMES_CN)
        lstm_scores[0] = 1.0
        lstm_conf = 1.0

    if state_updated and fc <= STREAM_WARMUP_FRAMES:
        # ---- 单帧独立推理 (仅预热期辅助，复用 512 输入尺寸) ----
        single_gid, single_scores_arr = predict_single_frame(re_frame)
        if isinstance(single_scores_arr, np.ndarray):
            st = _torch.from_numpy(single_scores_arr).float()
        else:
            st = single_scores_arr.float() if hasattr(single_scores_arr, 'float') else _torch.tensor(single_scores_arr)
        single_scores = F.softmax(st, dim=-1).tolist()
        single_conf = float(single_scores[single_gid]) if single_gid < len(single_scores) else 0.0

        # 预热期: 单帧 + LSTM 加权融合
        single_weight = max(0, 1.0 - fc / STREAM_WARMUP_FRAMES)  # 逐渐降低
        lstm_weight = 1.0 - single_weight

        # 计算融合分
        fused: dict[int, float] = {}
        for i in range(len(lstm_scores)):
            fused[i] = lstm_scores[i] * lstm_weight + single_scores[i] * single_weight
        raw_gid = int(max(fused, key=fused.get))
        raw_conf = round(float(fused[raw_gid]), 4)
    else:
        single_gid = lstm_gid
        single_conf = lstm_conf
        raw_gid = lstm_gid
        raw_conf = round(lstm_conf, 4)
    elapsed = time.time() - inference_start

    # ---- 推理耗时统计 ----
    stats = _stream_stats.setdefault(stream_id, {"times": [], "total_frames": 0, "skip_frames": 0})
    stats["total_frames"] = fc
    if state_updated:
        stats["times"].append(elapsed * 1000)
    else:
        stats["skip_frames"] += 1

    # ---- 预热期日志 (DEBUG) ----
    if fc <= STREAM_WARMUP_FRAMES:
        warmup_phase = "LSTM" if fc > STREAM_WARMUP_FRAMES else "融合"
        logger.debug(
            "实时流预热 #%d/%d [%s]: raw=%d(%.2f) lstm=%d(%.2f) single=%d(%.2f) fused=%d(%.2f) pose_q=%.2f valid=%s",
            fc, STREAM_WARMUP_FRAMES, warmup_phase,
            raw_gid, raw_conf, lstm_gid, lstm_conf, single_gid, single_conf,
            raw_gid, raw_conf, pose_quality["score"], state_updated,
        )

    # ---- 预热完成日志 (INFO) ----
    if fc == STREAM_WARMUP_FRAMES:
        logger.info(
            "实时流预热完成: stream_id=%s, 预热帧数=%d, 耗时=%.1fms",
            stream_id, fc, elapsed * 1000,
        )

    # ---- 姿势质量不足日志 (DEBUG, 每10帧节流) ----
    if not state_updated:
        skip_cnt = _stream_pose_skip_counters.get(stream_id, 0) + 1
        _stream_pose_skip_counters[stream_id] = skip_cnt
        if skip_cnt % 10 == 1:
            logger.debug(
                "实时流姿势质量不足: stream_id=%s, frame=#%d, pose_q=%.3f, valid_kp=%d, skip_count=%d",
                stream_id, fc, pose_quality["score"], pose_quality["validKeypoints"], skip_cnt,
            )
    else:
        _stream_pose_skip_counters[stream_id] = 0

    # ---- 帧历史缓冲区 ----
    history: list[dict] = _stream_histories.get(stream_id, [])
    # 首帧参考时间 (转为相对秒)
    t0 = _stream_start_times.setdefault(stream_id, now)

    raw_item = {
        "frame": fc,
        "time": round(now - t0, 3),
        "gestureId": raw_gid,
        "confidence": raw_conf,
        "lstmGid": lstm_gid,
        "lstmConf": round(lstm_conf, 4),
        "singleGid": single_gid,
        "singleConf": round(single_conf, 4),
        "validPose": bool(state_updated),
        "poseQuality": pose_quality["score"],
    }

    history.append(raw_item)
    if len(history) > STREAM_HISTORY_MAX:
        history = history[-STREAM_HISTORY_MAX:]

    # ---- 滑动窗口平滑 ----
    proposed_gid, proposed_conf = _stream_smooth_vote(history)
    best_gid, smoothed_conf, stable_changed = _stable_stream_result(
        stream_id,
        proposed_gid,
        proposed_conf,
        now,
        bool(state_updated),
    )
    smoothed_gesture = GESTURE_NAMES_CN[best_gid] if best_gid < len(GESTURE_NAMES_CN) else "未知"
    raw_item["stableGestureId"] = best_gid
    raw_item["stableConfidence"] = smoothed_conf
    raw_item["gesture"] = smoothed_gesture
    _stream_histories[stream_id] = history

    # ---- 手势切换日志 (INFO) ----
    if stable_changed and fc > STREAM_WARMUP_FRAMES:
        old_stable = _stream_stable_results.get(stream_id)
        old_gid = old_stable.get("gestureId", 0) if old_stable else 0
        old_name = GESTURE_NAMES_CN[old_gid] if old_gid < len(GESTURE_NAMES_CN) else "未知"
        if old_gid != best_gid:
            logger.info(
                "实时流手势切换: stream_id=%s, frame=#%d, %s(id=%d) → %s(id=%d), conf=%.2f, pose_q=%.2f",
                stream_id, fc, old_name, old_gid, smoothed_gesture, best_gid, smoothed_conf, pose_quality["score"],
            )

    # ---- 分段检测 (复用视频模式的 _build_segments) ----
    stable_history = [
        {
            "frame": item["frame"],
            "time": item["time"],
            "gestureId": item.get("stableGestureId", item["gestureId"]),
            "gesture": GESTURE_NAMES_CN[item.get("stableGestureId", item["gestureId"])]
            if item.get("stableGestureId", item["gestureId"]) < len(GESTURE_NAMES_CN)
            else "未知",
            "confidence": item.get("stableConfidence", item["confidence"]),
        }
        for item in history
    ]
    segments = _build_segments(stable_history) if len(stable_history) >= STREAM_SMOOTH_WINDOW else []
    all_segments = _stream_segments.get(stream_id, [])
    segment_changed = False

    if segments:
        # 检查是否有新段 (最后一段)
        last_seg = segments[-1]
        already_seen = any(s["start"] == last_seg["start"] and s["gestureId"] == last_seg["gestureId"] for s in all_segments)
        if not already_seen:
            all_segments.append(last_seg)
            _stream_segments[stream_id] = all_segments
            segment_changed = True
            seg_duration = round(last_seg["end"] - last_seg["start"], 2)
            logger.info(
                "实时流新段确认: stream_id=%s, frame=#%d, gesture=%s(id=%d), start=%.1fs, end=%.1fs, duration=%.1fs",
                stream_id, fc, last_seg["gesture"], last_seg["gestureId"],
                last_seg["start"], last_seg["end"], seg_duration,
            )

    current_segment = all_segments[-1] if all_segments else None

    # ---- Top-5 ----
    top5 = sorted(enumerate(lstm_scores), key=lambda x: x[1], reverse=True)[:5]
    top5_list = [
        {
            "gesture": GESTURE_NAMES_CN[i] if i < len(GESTURE_NAMES_CN) else "未知",
            "gestureId": i,
            "confidence": round(float(score), 4),
        }
        for i, score in top5
    ]

    # ---- 历史数组 (前端趋势) ----
    recent_history = [
        {
            "gesture": GESTURE_NAMES_CN[item["gestureId"]] if item["gestureId"] < len(GESTURE_NAMES_CN) else "未知",
            "gestureId": item["gestureId"],
            "confidence": item["confidence"],
            "validPose": item.get("validPose", True),
            "poseQuality": item.get("poseQuality", 0.0),
        }
        for item in history[-10:]
    ]

    # ---- 写入云数据库 (新段确认时 或 full模式每帧) ----
    if best_gid > 0 and segment_changed:
        log_gesture_async(
            GestureLogEntry(
                recognition_type="camera_stream",
                gesture=smoothed_gesture,
                gesture_id=best_gid,
                confidence=smoothed_conf,
                inference_ms=round(elapsed * 1000, 1),
                top5_json=build_top5_json(top5_list),
            )
        )
    elif GESTURE_LOG_LEVEL == "full":
        # full 模式: 每帧都写入 DB 日志
        log_gesture_async(
            GestureLogEntry(
                recognition_type="camera_stream",
                gesture=smoothed_gesture,
                gesture_id=best_gid,
                confidence=smoothed_conf,
                inference_ms=round(elapsed * 1000, 1),
                top5_json=build_top5_json(top5_list),
                segments_json=build_segments_json(all_segments),
            )
        )

    # ---- 周期性统计日志 (每50帧, INFO) ----
    if fc % 50 == 0 and stats["times"]:
        times_arr = stats["times"]
        avg_ms = round(sum(times_arr) / len(times_arr), 1)
        min_ms = round(min(times_arr), 1)
        max_ms = round(max(times_arr), 1)
        skip_pct = round(stats["skip_frames"] / max(1, fc) * 100, 1)
        stream_duration = round(now - _stream_start_times.get(stream_id, now), 1)
        logger.info(
            "实时流统计 #%d: stream_id=%s, stable=%s(id=%d), conf=%.2f, "
            "推理耗时 avg=%.1fms/min=%.1fms/max=%.1fms, 跳过帧=%d(%.1f%%), 流时长=%.1fs, 段数=%d",
            fc, stream_id, smoothed_gesture, best_gid, smoothed_conf,
            avg_ms, min_ms, max_ms, stats["skip_frames"], skip_pct,
            stream_duration, len(all_segments),
        )
        # 重置统计窗口 (避免 long-tail 效应)
        stats["times"] = []
        stats["skip_frames"] = 0

    return {
        "code": 200,
        "message": "success",
        "data": {
            "streamId": stream_id,
            "frameCount": fc,
            "gesture": smoothed_gesture,            # 平滑后结果
            "gestureId": best_gid,
            "confidence": smoothed_conf,
            "proposedGesture": GESTURE_NAMES_CN[proposed_gid] if proposed_gid < len(GESTURE_NAMES_CN) else "未知",
            "proposedGestureId": proposed_gid,
            "proposedConfidence": proposed_conf,
            "rawGesture": GESTURE_NAMES_CN[lstm_gid] if lstm_gid < len(GESTURE_NAMES_CN) else "未知",
            "rawGestureId": lstm_gid,
            "rawConfidence": round(lstm_conf, 4),
            "singleGesture": GESTURE_NAMES_CN[single_gid] if single_gid < len(GESTURE_NAMES_CN) else "未知",
            "singleGestureId": single_gid,
            "singleConfidence": round(single_conf, 4),
            "timestamp": now_ms,
            "top5": top5_list,
            "inference_ms": round(elapsed * 1000, 1),
            "poseQuality": pose_quality,
            "keypoints": _keypoints_to_list(display_coord_norm),
            "validPose": bool(state_updated),
            "history": recent_history,
            "segments": all_segments,               # 所有已确认手势段
            "currentSegment": current_segment,
            "segmentChanged": segment_changed,
            "stableChanged": stable_changed,
            "warmup": fc <= STREAM_WARMUP_FRAMES,
            **_police_detection_payload(police_detection, police_only_enabled, img_bgr.shape, confirmed=police_confirmed, streak=police_streak),
        },
    }
