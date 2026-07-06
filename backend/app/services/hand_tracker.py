import cv2
import mediapipe as mp
import numpy as np
from collections import deque
from typing import Tuple, List


class HandTracker:
    def __init__(self):
        self.mp_hands = mp.solutions.hands
        self.hands = self.mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=1,          # 先只识别一只手
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )
        self.mp_draw = mp.solutions.drawing_utils
        # 保存最近20帧的食指指尖坐标（用于动态手势分析）
        self.trajectory = deque(maxlen=20)

    def process_frame(self, image_bytes: bytes) -> Tuple[str, float, List]:
        """
        输入: 图片二进制数据
        返回: (手势键, 置信度, 关键点列表)
              手势键: fist, open_palm, thumb_up, thumb_down,
                     swipe_left, swipe_right, circle,
                     no_hand, unknown
        """
        # 1. 解码图像
        np_arr = np.frombuffer(image_bytes, np.uint8)
        frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        if frame is None:
            return "unknown", 0.0, []

        # 2. MediaPipe 手部检测
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        result = self.hands.process(rgb)

        if not result.multi_hand_landmarks:
            self.trajectory.clear()
            return "no_hand", 0.0, []

        # 3. 取第一只手
        hand_landmarks = result.multi_hand_landmarks[0]
        h, w, _ = frame.shape

        # 提取21个关键点坐标（像素值）
        landmark_list = []
        for lm in hand_landmarks.landmark:
            landmark_list.append([lm.x * w, lm.y * h, lm.z * w])

        # 4. 记录食指指尖轨迹（用于动态手势）
        index_tip = hand_landmarks.landmark[8]
        self.trajectory.append((index_tip.x * w, index_tip.y * h))

        # 5. 先判断静态手势（握拳、张开、拇指上下）
        gesture, conf = self._classify_static_gesture(hand_landmarks.landmark)
        if gesture != "unknown":
            return gesture, conf, landmark_list

        # 6. 若静态无法判断，尝试动态手势（滑动、画圈）
        gesture, conf = self._classify_dynamic_gesture()
        return gesture, conf, landmark_list

    def _classify_static_gesture(self, landmarks) -> Tuple[str, float]:
        """
        静态手势分类：握拳、手掌张开、拇指向上、拇指向下
        基于指尖到手腕的距离 + 拇指方向
        """
        wrist = landmarks[0]
        thumb_tip = landmarks[4]
        thumb_ip = landmarks[3]
        tips = [landmarks[4], landmarks[8], landmarks[12], landmarks[16], landmarks[20]]

        # 计算所有指尖到手腕的平均距离
        distances = []
        for tip in tips:
            dx = tip.x - wrist.x
            dy = tip.y - wrist.y
            dz = tip.z - wrist.z
            distances.append((dx**2 + dy**2 + dz**2) ** 0.5)
        avg_dist = sum(distances) / len(distances)

        # 拇指方向（图像坐标系 y 向下，y 小表示上）
        thumb_is_up = thumb_tip.y < thumb_ip.y

        # 判断阈值（可根据实际摄像头距离微调）
        if avg_dist > 0.25:
            # 手掌张开
            if thumb_is_up:
                return "thumb_up", min(avg_dist / 0.4, 1.0)
            else:
                return "thumb_down", min(avg_dist / 0.4, 1.0)
        else:
            # 握拳
            return "fist", max(1.0 - avg_dist / 0.25, 0.5)

        # 如果都不满足，返回 unknown
        return "unknown", 0.0

    def _classify_dynamic_gesture(self) -> Tuple[str, float]:
        """
        动态手势分类：左右滑动、画圈
        基于食指指尖的轨迹分析
        """
        if len(self.trajectory) < 10:
            return "unknown", 0.0

        xs = [p[0] for p in self.trajectory]
        ys = [p[1] for p in self.trajectory]

        dx = max(xs) - min(xs)
        dy = max(ys) - min(ys)

        # 左右滑动：水平位移大且远大于垂直位移
        if dx > 100 and dx > 2 * dy:
            direction = "swipe_right" if xs[-1] > xs[0] else "swipe_left"
            confidence = min(dx / 250, 1.0)
            return direction, confidence

        # 画圈：轨迹包围面积适中
        area = dx * dy
        if 5000 < area < 30000 and dx > 50 and dy > 50:
            return "circle", 0.8

        return "unknown", 0.0