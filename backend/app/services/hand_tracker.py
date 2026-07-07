import cv2
import numpy as np
from collections import deque
from typing import Tuple, List
import mediapipe as mp

# 使用新版 mediapipe 的 tasks API
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

class HandTracker:
    def __init__(self, model_path: str = "app/models/gesture_recognizer.task"):
        """
        初始化：加载官方静态手势模型，并准备动态手势轨迹队列
        """
        # ---- 加载官方 .task 模型 ----
        try:
            base_options = python.BaseOptions(model_asset_path=model_path)
            options = vision.GestureRecognizerOptions(
                base_options=base_options,
                running_mode=vision.RunningMode.IMAGE,
                num_hands=1
            )
            self.recognizer = vision.GestureRecognizer.create_from_options(options)
            print("✅ 官方手势模型加载成功！")
        except Exception as e:
            print(f"❌ 模型加载失败: {e}")
            raise

        # 动态手势轨迹缓存（保存食指指尖坐标）
        self.trajectory = deque(maxlen=25)
        self.last_gesture = "no_hand"   # 初始化为 no_hand，避免未知继承
        self.stable_count = 0
        self.stable_threshold = 2        # 连续2帧相同才输出（防抖）

    def process_frame(self, image_bytes: bytes) -> Tuple[str, float, List]:
        """
        处理一帧图片（字节流），返回 (手势名称, 置信度, 关键点列表)
        """
        try:
            # ---- 1. 解码图像 ----
            np_arr = np.frombuffer(image_bytes, np.uint8)
            frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
            if frame is None:
                return "unknown", 0.0, []

            # ---- 2. 转换为 MediaPipe Image 对象 ----
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

            # ---- 3. 运行官方静态模型 ----
            recognition_result = self.recognizer.recognize(mp_image)

            # 提取手部关键点
            landmarks = []
            if recognition_result.hand_landmarks:
                for lm in recognition_result.hand_landmarks[0]:
                    landmarks.append([lm.x, lm.y, lm.z])

            # ---- 4. 无手检测 ----
            if not recognition_result.hand_landmarks:
                self.trajectory.clear()
                self.stable_count = 0
                self.last_gesture = "no_hand"
                return "no_hand", 0.0, []

            # ---- 5. 记录轨迹（食指指尖，像素坐标） ----
            index_tip = recognition_result.hand_landmarks[0][8]
            h, w, _ = frame.shape
            self.trajectory.append((index_tip.x * w, index_tip.y * h))

            # ---- 6. 解析官方静态结果 ----
            static_gesture = "unknown"
            static_conf = 0.0
            if recognition_result.gestures:
                top_gesture = recognition_result.gestures[0][0]
                static_gesture = top_gesture.category_name
                static_conf = top_gesture.score

            # ---- 7. 决策逻辑（修复版） ----
            gesture = "unknown"
            confidence = 0.0

            # 7.1 静态手势：若属于已知类别且置信度 > 0.25，直接采用
            if static_gesture in ["Closed_Fist", "Open_Palm", "Thumb_Up", "Thumb_Down"] and static_conf > 0.25:
                gesture = self._map_gesture_name(static_gesture)
                confidence = static_conf
            else:
                # 7.2 尝试动态手势（需轨迹长度 >= 10）
                if len(self.trajectory) >= 10:
                    gesture, confidence = self._detect_dynamic_gesture()
                    # 动态未检测到则保持上一帧（但上一帧是 unknown 时变为 no_hand）
                    if gesture == "unknown" or confidence < 0.3:
                        gesture = self.last_gesture if self.last_gesture != "unknown" else "no_hand"
                        confidence = 0.4
                else:
                    # 轨迹不足且静态不准：保持上一帧（若上一帧 unknown 则返回 no_hand）
                    gesture = self.last_gesture if self.last_gesture != "unknown" else "no_hand"
                    confidence = 0.4

            # ---- 8. 防抖 ----
            if gesture == self.last_gesture:
                self.stable_count += 1
            else:
                self.stable_count = 1
                self.last_gesture = gesture

            if self.stable_count >= self.stable_threshold:
                final_gesture = gesture
            else:
                final_gesture = self.last_gesture

            # 若最终结果为 unknown 或 no_hand，降低置信度
            if final_gesture in ["unknown", "no_hand"]:
                confidence = 0.3

            return final_gesture, min(confidence, 1.0), landmarks

        except Exception as e:
            # 单帧出错不崩溃，返回 unknown
            print(f"⚠️ 处理帧时出错: {e}")
            return "unknown", 0.0, []

    def _map_gesture_name(self, official_name: str) -> str:
        """
        将官方模型的手势名称映射到项目统一命名
        """
        mapping = {
            "Closed_Fist": "fist",
            "Open_Palm": "open_palm",
            "Thumb_Up": "thumb_up",
            "Thumb_Down": "thumb_down",
            "Pointing_Up": "pointing_up",
            "ILoveYou": "iloveyou"
        }
        return mapping.get(official_name, official_name.lower())

    def _detect_dynamic_gesture(self) -> Tuple[str, float]:
        """
        基于轨迹队列检测左右滑动和画圈
        """
        if len(self.trajectory) < 10:
            return "unknown", 0.0

        pts = np.array(self.trajectory)
        start = pts[0]
        end = pts[-1]
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        total_len = np.sum(np.linalg.norm(np.diff(pts, axis=0), axis=1))

        displacement = np.sqrt(dx**2 + dy**2)

        # 1. 滑动检测
        if displacement > 60 and total_len / displacement < 1.5:
            if abs(dx) > abs(dy):
                if dx > 0:
                    return "swipe_right", min(1.0, displacement / 150)
                else:
                    return "swipe_left", min(1.0, displacement / 150)
            else:
                return "unknown", 0.0

        # 2. 画圈检测
        min_x, min_y = np.min(pts, axis=0)
        max_x, max_y = np.max(pts, axis=0)
        bbox_area = (max_x - min_x) * (max_y - min_y)

        if 3000 < bbox_area < 40000 and total_len > 150:
            dist_ends = np.linalg.norm(pts[0] - pts[-1])
            if dist_ends < 80:
                return "circle", 0.85

        return "unknown", 0.0
