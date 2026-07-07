"""
手部追踪服务（兼容 MediaPipe 新版 API）
基于 landmarks 的手势分类逻辑保持不变
"""
import cv2
import numpy as np
from collections import deque
from typing import Tuple, List

# ─── MediaPipe 兼容导入 ──────────────────────
# 新版 (0.10.30+): mp.tasks.vision.HandLandmarker
# 旧版 (≤0.10.14): mp.solutions.hands
try:
    import mediapipe as mp

    # 尝试新版 API
    if hasattr(mp, 'tasks'):
        from mediapipe.tasks import python as mp_tasks
        from mediapipe.tasks.python import vision
        _USE_NEW_API = True
    else:
        _USE_NEW_API = False
except ImportError:
    mp = None
    _USE_NEW_API = False


class HandTracker:
    def __init__(self):
        if _USE_NEW_API:
            self._init_new_api()
        else:
            self._init_old_api()
        self.trajectory = deque(maxlen=20)

    def _init_new_api(self):
        """新版 MediaPipe API 初始化"""
        model_path = "hand_landmarker.task"
        try:
            base_options = mp_tasks.BaseOptions(model_asset_path=model_path)
            options = vision.HandLandmarkerOptions(
                base_options=base_options,
                num_hands=1,
                min_hand_detection_confidence=0.5,
                min_tracking_confidence=0.5,
            )
            self.detector = vision.HandLandmarker.create_from_options(options)
        except Exception:
            # 如果模型不存在，自动下载
            import urllib.request
            import os
            url = ("https://storage.googleapis.com/mediapipe-models/"
                   "hand_landmarker/hand_landmarker/float16/"
                   "latest/hand_landmarker.task")
            print(f"正在下载 MediaPipe 模型: {model_path}")
            urllib.request.urlretrieve(url, model_path)
            base_options = mp_tasks.BaseOptions(model_asset_path=model_path)
            options = vision.HandLandmarkerOptions(
                base_options=base_options,
                num_hands=1,
                min_hand_detection_confidence=0.5,
                min_tracking_confidence=0.5,
            )
            self.detector = vision.HandLandmarker.create_from_options(options)

    def _init_old_api(self):
        """旧版 MediaPipe API 初始化"""
        self.mp_hands = mp.solutions.hands
        self.hands = self.mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=1,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        self.mp_draw = mp.solutions.drawing_utils

    def _get_landmarks(self, frame: np.ndarray):
        """获取手部关键点，兼容新旧 API"""
        if _USE_NEW_API:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            det_result = self.detector.detect(mp_image)
            if not det_result.hand_landmarks:
                return None, None, None
            h, w, _ = frame.shape
            landmarks = det_result.hand_landmarks[0]
            landmark_list = [[lm.x * w, lm.y * h, lm.z * w] for lm in landmarks]
            return landmarks, landmark_list, None
        else:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            result = self.hands.process(rgb)
            if not result.multi_hand_landmarks:
                return None, None, None
            hand_landmarks = result.multi_hand_landmarks[0]
            h, w, _ = frame.shape
            landmark_list = []
            for lm in hand_landmarks.landmark:
                landmark_list.append([lm.x * w, lm.y * h, lm.z * w])
            return hand_landmarks.landmark, landmark_list, None

    def process_frame(self, image_bytes: bytes) -> Tuple[str, float, List]:
        """
        输入: 图片二进制数据
        返回: (手势键, 置信度, 关键点列表)
        """
        np_arr = np.frombuffer(image_bytes, np.uint8)
        frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        if frame is None:
            return "unknown", 0.0, []

        landmarks, landmark_list, _ = self._get_landmarks(frame)
        if landmarks is None:
            self.trajectory.clear()
            return "no_hand", 0.0, []

        # 记录食指指尖轨迹（用于动态手势）
        index_tip = landmarks[8] if _USE_NEW_API else landmarks[8]
        if _USE_NEW_API:
            self.trajectory.append((index_tip.x * frame.shape[1], index_tip.y * frame.shape[0]))
        else:
            w, h = frame.shape[1], frame.shape[0]
            self.trajectory.append((index_tip.x * w, index_tip.y * h))

        # 静态手势判断
        gesture, conf = self._classify_static_gesture(landmarks)
        if gesture != "unknown":
            return gesture, conf, landmark_list

        # 动态手势判断
        gesture, conf = self._classify_dynamic_gesture()
        return gesture, conf, landmark_list

    def _classify_static_gesture(self, landmarks) -> Tuple[str, float]:
        """静态手势分类：握拳、手掌张开、拇指向上、拇指向下"""
        wrist = landmarks[0]
        thumb_tip = landmarks[4]
        thumb_ip = landmarks[3]
        tips = [landmarks[4], landmarks[8], landmarks[12], landmarks[16], landmarks[20]]

        distances = []
        for tip in tips:
            dx = tip.x - wrist.x
            dy = tip.y - wrist.y
            dz = tip.z - wrist.z
            distances.append((dx**2 + dy**2 + dz**2) ** 0.5)
        avg_dist = sum(distances) / len(distances)

        thumb_is_up = thumb_tip.y < thumb_ip.y

        if avg_dist > 0.25:
            if thumb_is_up:
                return "thumb_up", min(avg_dist / 0.4, 1.0)
            else:
                return "thumb_down", min(avg_dist / 0.4, 1.0)
        else:
            return "fist", max(1.0 - avg_dist / 0.25, 0.5)

        return "unknown", 0.0

    def _classify_dynamic_gesture(self) -> Tuple[str, float]:
        """动态手势分类：左右滑动、画圈"""
        if len(self.trajectory) < 10:
            return "unknown", 0.0

        xs = [p[0] for p in self.trajectory]
        ys = [p[1] for p in self.trajectory]

        dx = max(xs) - min(xs)
        dy = max(ys) - min(ys)

        if dx > 100 and dx > 2 * dy:
            direction = "swipe_right" if xs[-1] > xs[0] else "swipe_left"
            confidence = min(dx / 250, 1.0)
            return direction, confidence

        area = dx * dy
        if 5000 < area < 30000 and dx > 50 and dy > 50:
            return "circle", 0.8

        return "unknown", 0.0
