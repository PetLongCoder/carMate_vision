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
from pathlib import Path

# Windows 上 CUDA/PyTorch 底层崩溃会直接弹 python.exe 应用程序错误，
# 先默认使用 CPU，便于稳定验证模型链路。需要 GPU 时可设置 CARMATE_DEVICE=cuda。
DEVICE_MODE = os.getenv("CARMATE_DEVICE", "cpu").lower()
if DEVICE_MODE == "cpu":
    os.environ.setdefault("CUDA_VISIBLE_DEVICES", "-1")

import cv2
import numpy as np
from PIL import Image
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware

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


def force_cpu_if_needed():
    if DEVICE_MODE != "cpu":
        return
    import torch
    torch.cuda.is_available = lambda: False


def preload_model():
    """预加载所有模型"""
    global _shared_pose, _shared_bla, _shared_lstm
    import os
    force_cpu_if_needed()
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


@app.get("/api/health")
async def health_check():
    import torch
    return {
        "status": "ok",
        "model": "ctpgr-pytorch (Pose + LSTM)",
        "classes": len(GESTURE_NAMES_CN),
        "device": "cuda" if torch.cuda.is_available() else "cpu",
        "device_mode": DEVICE_MODE,
    }


@app.post("/api/police-gesture/recognize")
async def recognize_police_gesture(file: UploadFile = File(...)):
    """交警手势识别 - 上传图片或视频"""
    contents = await file.read()
    file_ext = Path(file.filename or "image.jpg").suffix.lower()
    timestamp = int(time.time() * 1000)

    try:
        if file_ext in (".mp4", ".avi", ".mov", ".webm", ".mkv"):
            return await _process_video(contents, file_ext, timestamp)
        else:
            return await _process_image(contents, timestamp)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"识别失败: {e}")
        raise HTTPException(500, f"识别失败: {str(e)}")


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
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS)

        if total_frames <= 0:
            raise HTTPException(400, "无法读取视频")

        # CTPGR 是序列模型，视频需要连续输入。长视频按 15fps 约每 0.5 秒采样一次，
        # 避免只抽 30 帧导致动作被跳过。
        target_sample_fps = 2.0
        sample_interval = max(1, int(round(fps / target_sample_fps))) if fps > 0 else 1
        logger.info(f"视频推理: {total_frames}帧, fps={fps:.1f}, 采样间隔={sample_interval}")

        start = time.time()
        gesture_votes = {}
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
                import torch.nn.functional as F
                import torch
                if isinstance(scores_arr, np.ndarray):
                    t = torch.from_numpy(scores_arr).float()
                else:
                    t = scores_arr.float()
                probs = F.softmax(t, dim=-1)
                scores = probs.tolist() if hasattr(probs, 'tolist') else list(probs)

                confidence = float(scores[gesture_id]) if gesture_id < len(scores) else 0.0
                if gesture_id > 0:
                    gesture_votes[gesture_id] = gesture_votes.get(gesture_id, 0) + 1

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

        # 取投票最多的手势
        if gesture_votes:
            best_gesture_id = max(gesture_votes, key=gesture_votes.get)
        else:
            best_gesture_id = 0

        # 计算平均置信度
        best_confs = [f["confidence"] for f in frame_results if f["gestureId"] == best_gesture_id]
        avg_confidence = float(np.mean(best_confs)) if best_confs else 0.0
        gesture_cn = GESTURE_NAMES_CN[best_gesture_id] if best_gesture_id < len(GESTURE_NAMES_CN) else "未知"

        # 手势分段: 合并连续的相同手势
        segments = []
        seg_start = None
        seg_gesture = None
        for fr in frame_results:
            gid = fr["gestureId"]
            if gid != seg_gesture:
                if seg_start is not None and seg_gesture is not None and seg_gesture > 0:
                    segments.append({
                        "start": seg_start["time"],
                        "end": fr["time"],
                        "gesture": GESTURE_NAMES_CN[seg_gesture],
                        "gestureId": seg_gesture,
                    })
                seg_start = fr
                seg_gesture = gid
        # 最后一段
        if seg_start is not None and seg_gesture is not None and seg_gesture > 0:
            segments.append({
                "start": seg_start["time"],
                "end": frame_results[-1]["time"] if frame_results else seg_start["time"],
                "gesture": GESTURE_NAMES_CN[seg_gesture],
                "gestureId": seg_gesture,
            })

        # Top-5
        top5_votes = sorted(gesture_votes.items(), key=lambda x: x[1], reverse=True)[:5]
        top5_list = [
            {"gesture": GESTURE_NAMES_CN[gid] if gid < len(GESTURE_NAMES_CN) else "未知",
             "gestureId": gid, "confidence": round(cnt / processed, 4) if processed else 0}
            for gid, cnt in top5_votes
        ]

        duration = total_frames / fps if fps > 0 else 0
        logger.info(f"视频识别: {gesture_cn} ({processed}帧, {len(segments)}个手势段, {elapsed*1000:.0f}ms)")

        return {
            "code": 200, "message": "success",
            "data": {
                "gesture": gesture_cn, "gestureId": best_gesture_id,
                "confidence": round(avg_confidence, 4),
                "timestamp": timestamp,
                "top5": top5_list,
                "inference_ms": round(elapsed * 1000, 1),
                "video_duration": round(duration, 1),
                "video_fps": round(fps, 1),
                "frames_processed": processed,
                "frames": frame_results,       # 每帧的手势
                "segments": segments,           # 连续手势段
            },
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
