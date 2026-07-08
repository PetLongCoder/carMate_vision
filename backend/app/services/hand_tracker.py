import cv2
import numpy as np
from collections import deque
from typing import Tuple, List
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

class HandTracker:
    def __init__(self, model_path: str = "app/models/gesture_recognizer.task"):
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

        # 双轨迹缓存
        self.trajectory_hand = deque(maxlen=25)    # 手掌中心 → 用于滑动
        self.trajectory_finger = deque(maxlen=25)  # 食指尖 → 用于画圈
        
        self.last_output = "no_hand"
        self.stable_count = 0
        self.idle_count = 0

        self.dynamic_lock = False
        self.lock_frames = 0
        self.dynamic_cooldown = 8
        self.static_threshold = 2

    def reset_state(self):
        self.trajectory_hand.clear()
        self.trajectory_finger.clear()
        self.last_output = "no_hand"
        self.stable_count = 0
        self.idle_count = 0
        self.dynamic_lock = False
        self.lock_frames = 0

    def _get_hand_center(self, landmarks):
        wrist = landmarks[0]
        middle_base = landmarks[9]
        return (wrist.x + middle_base.x) / 2, (wrist.y + middle_base.y) / 2

    def _get_finger_tip(self, landmarks, idx=8):
        """获取指尖坐标，默认食指"""
        tip = landmarks[idx]
        return tip.x, tip.y

    def process_frame(self, image_bytes: bytes) -> Tuple[str, float, List]:
        try:
            np_arr = np.frombuffer(image_bytes, np.uint8)
            frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
            if frame is None:
                return "unknown", 0.0, []

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

            recognition_result = self.recognizer.recognize(mp_image)

            landmarks = []
            if recognition_result.hand_landmarks:
                for lm in recognition_result.hand_landmarks[0]:
                    landmarks.append([lm.x, lm.y, lm.z])

            if not recognition_result.hand_landmarks:
                self.trajectory_hand.clear()
                self.trajectory_finger.clear()
                self.stable_count = 0
                self.idle_count += 1
                if self.idle_count > 10:
                    self.last_output = "no_hand"
                    self.dynamic_lock = False
                return "no_hand", 0.0, []

            self.idle_count = 0

            h, w, _ = frame.shape
            hand_lm = recognition_result.hand_landmarks[0]
            
            # 获取两个轨迹点
            cx, cy = self._get_hand_center(hand_lm)
            fx, fy = self._get_finger_tip(hand_lm, idx=8)  # 食指尖
            
            self.trajectory_hand.append((cx * w, cy * h))
            self.trajectory_finger.append((fx * w, fy * h))

            # ---- 静态模型结果 ----
            static_gesture = "unknown"
            static_conf = 0.0
            if recognition_result.gestures:
                top = recognition_result.gestures[0][0]
                static_gesture = top.category_name
                static_conf = top.score
            mapped_gesture = self._map_gesture_name(static_gesture)

            # ---- 动态锁定冷却 ----
            if self.dynamic_lock:
                self.lock_frames -= 1
                if self.lock_frames <= 0:
                    self.dynamic_lock = False
                    self.trajectory_hand.clear()
                    self.trajectory_finger.clear()

            # ==========================================
            # 核心决策
            # ==========================================
            output = "unknown"
            confidence = 0.0

            if self.dynamic_lock:
                return self.last_output, 0.8, landmarks

            # ---- 动态检测 ----
            if len(self.trajectory_hand) >= 8 or len(self.trajectory_finger) >= 8:
                print(f"🔄 尝试动态检测, 手轨迹: {len(self.trajectory_hand)}, 指轨迹: {len(self.trajectory_finger)}")
                
                # 滑动检测：使用手掌中心
                swipe_result, swipe_conf = self._detect_swipe()
                if swipe_result != "unknown" and swipe_conf > 0.3:
                    output = swipe_result
                    confidence = swipe_conf
                    self.last_output = output
                    self.dynamic_lock = True
                    self.lock_frames = self.dynamic_cooldown
                    print(f"✅ 滑动触发: {output}")
                    return output, confidence, landmarks
                
                # 画圈检测：使用食指尖
                circle_result, circle_conf = self._detect_circle()
                if circle_result != "unknown" and circle_conf > 0.3:
                    output = circle_result
                    confidence = circle_conf
                    self.last_output = output
                    self.dynamic_lock = True
                    self.lock_frames = self.dynamic_cooldown
                    print(f"✅ 画圈触发: {output}")
                    return output, confidence, landmarks

            # ---- 静态手势 ----
            if mapped_gesture in ["fist", "open_palm", "thumb_up", "thumb_down"] and static_conf > 0.25:
                if mapped_gesture == self.last_output:
                    self.stable_count += 1
                else:
                    self.stable_count = 1
                    self.last_output = mapped_gesture

                if self.stable_count >= self.static_threshold:
                    output = mapped_gesture
                    confidence = static_conf
                else:
                    output = self.last_output
                    confidence = static_conf * 0.8
                
                # 不清理轨迹，让轨迹继续累积
                return output, min(confidence, 1.0), landmarks

            output = self.last_output
            confidence = 0.3
            return output, confidence, landmarks

        except Exception as e:
            print(f"⚠️ 处理帧时出错: {e}")
            return "unknown", 0.0, []

    def _detect_swipe(self) -> Tuple[str, float]:
        """使用手掌中心轨迹检测滑动（增强版：放宽阈值 + 方向镜像 + 方向持续检测）"""
        if len(self.trajectory_hand) < 8:
            return "unknown", 0.0
        
        pts = np.array(self.trajectory_hand)
        start = pts[0]
        end = pts[-1]
        displacement = np.linalg.norm(end - start)
        total_len = np.sum(np.linalg.norm(np.diff(pts, axis=0), axis=1))
        
        # ===== 方法1：基于总路径的检测（放宽条件） =====
        if total_len > 20:  # 原 30 → 20
            # 方向角
            angles = []
            for i in range(1, len(pts)):
                dx = pts[i][0] - pts[i-1][0]
                dy = pts[i][1] - pts[i-1][1]
                angles.append(np.arctan2(dy, dx))
            angles = np.array(angles)
            
            # 方向一致性
            cos_sum = np.sum(np.cos(angles))
            sin_sum = np.sum(np.sin(angles))
            resultant = np.sqrt(cos_sum**2 + sin_sum**2) / len(angles)
            
            # 放宽阈值
            if resultant > 0.25:  # 原 0.3 → 0.25
                straightness = total_len / (displacement + 0.1)
                if straightness < 4.0:  # 原 3.5 → 4.0
                    if abs(end[0] - start[0]) > abs(end[1] - start[1]):
                        # ===== 镜像补偿 =====
                        if end[0] > start[0]:
                            return "swipe_left", min(1.0, total_len / 120)
                        else:
                            return "swipe_right", min(1.0, total_len / 120)
        
        # ===== 方法2：方向持续检测（解决慢速滑动） =====
        if len(self.trajectory_hand) >= 6:
            # 取最近6帧
            recent = list(self.trajectory_hand)[-6:]
            if len(recent) >= 6:
                # 计算每帧之间的方向
                dirs = []
                for i in range(1, len(recent)):
                    dx = recent[i][0] - recent[i-1][0]
                    dy = recent[i][1] - recent[i-1][1]
                    # 忽略静止帧（位移很小）
                    if abs(dx) < 2 and abs(dy) < 2:
                        continue
                    # 归一化方向（只保留水平/垂直倾向）
                    if abs(dx) > abs(dy):
                        dirs.append(1 if dx > 0 else -1)  # 1=右，-1=左
                    else:
                        dirs.append(0)  # 垂直忽略
                
                # 如果至少有4个有效方向且水平方向一致
                if len(dirs) >= 4:
                    right_count = dirs.count(1)
                    left_count = dirs.count(-1)
                    if right_count >= 3 or left_count >= 3:
                        # 镜像补偿
                        if right_count >= 3:
                            return "swipe_left", 0.7
                        else:
                            return "swipe_right", 0.7
        
        return "unknown", 0.0

    def _detect_circle(self) -> Tuple[str, float]:
        """使用食指尖轨迹检测画圈（增强版：放宽条件，适应不同速度）"""
        if len(self.trajectory_finger) < 10:
            return "unknown", 0.0
        
        pts = np.array(self.trajectory_finger)
        start = pts[0]
        end = pts[-1]
        displacement = np.linalg.norm(end - start)
        total_len = np.sum(np.linalg.norm(np.diff(pts, axis=0), axis=1))
        
        # 降低路径门槛
        if total_len < 35:  # 原 50 → 35
            return "unknown", 0.0
        
        # 方向角
        angles = []
        for i in range(1, len(pts)):
            dx = pts[i][0] - pts[i-1][0]
            dy = pts[i][1] - pts[i-1][1]
            angles.append(np.arctan2(dy, dx))
        angles = np.array(angles)
        
        # 方向一致性（画圈时应该低）
        cos_sum = np.sum(np.cos(angles))
        sin_sum = np.sum(np.sin(angles))
        resultant = np.sqrt(cos_sum**2 + sin_sum**2) / len(angles)
        
        # 角度累积变化
        angle_diffs = []
        for i in range(1, len(angles)):
            diff = angles[i] - angles[i-1]
            diff = np.arctan2(np.sin(diff), np.cos(diff))
            angle_diffs.append(diff)
        total_angular = np.sum(angle_diffs)
        
        # 检测条件：放宽角度累积和闭合性
        if resultant < 0.6 and abs(total_angular) > 1.8:  # 2.0 → 1.8
            dist_ends = np.linalg.norm(pts[0] - pts[-1])
            # 相对闭合：终点距离 < 总路径的 60%（原固定200，现自适应）
            if dist_ends < total_len * 0.6:
                min_x, min_y = np.min(pts, axis=0)
                max_x, max_y = np.max(pts, axis=0)
                area = (max_x - min_x) * (max_y - min_y)
                # 放宽面积范围
                if 300 < area < 90000:  # 原 500~80000 → 300~90000
                    print(f"   circle: area={area:.0f}, dist_ends={dist_ends:.1f}, angular={abs(total_angular):.2f}")
                    return "circle", min(0.85, abs(total_angular) / 6)
        return "unknown", 0.0

    def _map_gesture_name(self, official_name: str) -> str:
        mapping = {
            "Closed_Fist": "fist",
            "Open_Palm": "open_palm",
            "Thumb_Up": "thumb_up",
            "Thumb_Down": "thumb_down",
            "Pointing_Up": "pointing_up",
            "ILoveYou": "iloveyou"
        }
        return mapping.get(official_name, official_name.lower())