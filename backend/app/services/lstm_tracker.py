import cv2
import numpy as np
import mediapipe as mp
import torch
import torch.nn as nn
from typing import Tuple, List

# ============================================================
# 1. 定义与训练时相同的 LSTM 模型结构
# ============================================================
class GestureLSTM(nn.Module):
    def __init__(self, input_size=63, hidden_size=128, num_layers=2, num_classes=None):
        super().__init__()
        self.lstm = nn.LSTM(input_size, hidden_size, num_layers, batch_first=True, dropout=0.3)
        self.fc = nn.Linear(hidden_size, num_classes)
        self.dropout = nn.Dropout(0.3)

    def forward(self, x):
        out, _ = self.lstm(x)
        out = self.dropout(out[:, -1, :])
        return self.fc(out)


# ============================================================
# 2. LSTM 推理跟踪器
# ============================================================
class LSTMGestureTracker:
    def __init__(
        self,
        model_path: str = "app/models/gesture_model.pth",
        lstm_threshold: float = 0.75,
        stable_threshold: int = 2,
    ):
        self.lstm_threshold = lstm_threshold
        self.stable_threshold = stable_threshold

        # 加载 LSTM 模型
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        checkpoint = torch.load(model_path, map_location=device, weights_only=False)
        self.label_encoder = checkpoint['label_encoder']
        self.num_classes = checkpoint['num_classes']
        self.seq_length = checkpoint['seq_length']
        self.hidden_size = checkpoint.get('hidden_size', 128)
        self.num_layers = checkpoint.get('num_layers', 2)

        self.model = GestureLSTM(
            input_size=63,
            hidden_size=self.hidden_size,
            num_layers=self.num_layers,
            num_classes=self.num_classes
        )
        self.model.load_state_dict(checkpoint['model_state_dict'])
        self.model.to(device)
        self.model.eval()
        self.device = device

        # 缓冲区：存储最近 seq_length 帧的63维关键点
        self.buffer = []
        self.last_gesture = "unknown"
        self.stable_count = 0

        # 无手计数器：用于检测手是否移出画面
        self.no_hand_count = 0

        # MediaPipe
        self.mp_hands = mp.solutions.hands
        self.hands = self.mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=1,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )

        print("✅ LSTM 模型加载成功！")
        print(f"   手势类别: {list(self.label_encoder.classes_)}")
        print(f"   序列长度: {self.seq_length}")
        print(f"   运行设备: {self.device}")
        print(f"   LSTM 置信度阈值: {self.lstm_threshold}")

    def reset_state(self):
        self.buffer = []
        self.last_gesture = "unknown"
        self.stable_count = 0
        self.no_hand_count = 0

    def _extract_landmarks(self, hand_landmarks) -> List[float]:
        landmarks = []
        for lm in hand_landmarks.landmark:
            landmarks.extend([lm.x, lm.y, lm.z])
        return landmarks  # 63维

    def process_frame(self, image_bytes: bytes) -> Tuple[str, float, List]:
        # 1. 解码图像
        np_arr = np.frombuffer(image_bytes, np.uint8)
        frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        if frame is None:
            return "unknown", 0.0, []

        # 2. 镜像（与训练数据保持一致）
        frame = cv2.flip(frame, 1)

        # 3. MediaPipe 手部检测
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        result = self.hands.process(rgb)

        landmarks_pixel = []  # 默认空，无手时保持空
        if result.multi_hand_landmarks:
            hand_lm = result.multi_hand_landmarks[0]
            h, w, _ = frame.shape
            for lm in hand_lm.landmark:
                landmarks_pixel.append([lm.x * w, lm.y * h, lm.z * w])
            vec = self._extract_landmarks(hand_lm)
            self.buffer.append(vec)
            self.no_hand_count = 0
        else:
            # 无手：填充全零，累加无手计数，且立即清空 landmarks_pixel
            self.buffer.append([0.0] * 63)
            self.no_hand_count += 1
            # 关键修复：无手时 landmarks_pixel 保持为空列表，前端将清空画布
            landmarks_pixel = []

        # 4. 如果连续 5 帧以上无手，直接返回 no_hand（不等缓冲区满）
        if self.no_hand_count > 5:
            self.last_gesture = "no_hand"
            return "no_hand", 0.0, landmarks_pixel

        # 保持缓冲区长度不超过 seq_length
        if len(self.buffer) > self.seq_length:
            self.buffer.pop(0)

        # 如果缓冲区未满，返回上一帧结果（但 landmarks_pixel 已空，前端骨骼消失）
        if len(self.buffer) < self.seq_length:
            return self.last_gesture, 0.0, landmarks_pixel

        # 5. LSTM 预测（滑动窗口）
        input_tensor = torch.FloatTensor(np.array(self.buffer)).unsqueeze(0).to(self.device)
        with torch.no_grad():
            output = self.model(input_tensor)
            probs = torch.softmax(output, dim=1)
            confidence, pred_idx = torch.max(probs, 1)
            confidence = confidence.item()
            pred_idx = pred_idx.item()

        gesture_name = self.label_encoder.inverse_transform([pred_idx])[0]

        # 针对特定手势提高阈值
        if gesture_name == "rotate_ccw":
            effective_threshold = 0.92
        elif gesture_name == "rotate_cw":
            effective_threshold = 0.85
            
        else:
            effective_threshold = self.lstm_threshold

        # 6. 防抖：连续相同手势才更新输出
        if gesture_name == self.last_gesture:
            self.stable_count += 1
        print(f"🔍 手势: {gesture_name}, 置信度: {confidence:.4f}")

        # 针对特定手势调整阈值
        if gesture_name == "rotate_ccw":
            effective_threshold = 0.99
        elif gesture_name == "rotate_cw":
            effective_threshold = 0.82
        elif gesture_name in ["swipe_left", ]:
            effective_threshold = 0.35
        elif gesture_name == "swipe_right":
            effective_threshold = 0.4
        else:
            effective_threshold = self.lstm_threshold

        # 7. 只有连续稳定且置信度足够才输出
        if self.stable_count >= self.stable_threshold and confidence > effective_threshold:
            return gesture_name, confidence, landmarks_pixel
        else:
        # ==========================================
        # 关键修复：先检查置信度是否达标
        # ==========================================
            is_confident = confidence > effective_threshold

        # 只有置信度达标时，才更新防抖状态
        if is_confident:
            if gesture_name == self.last_gesture:
                self.stable_count += 1
            else:
                self.stable_count = 1
                self.last_gesture = gesture_name
        else:
            # 低置信度：重置稳定计数（防止低置信度累积导致误输出）
            self.stable_count = 0
            # 不更新 last_gesture，保持上一个有效手势

        # 6. 输出判断
        if is_confident and self.stable_count >= self.stable_threshold:
            return gesture_name, confidence, landmarks_pixel
        else:
            # 低置信度或未稳定：返回上一个有效手势（但置信度用当前帧的，作为参考）
            # 如果上一个有效手势是 unknown，则返回 unknown
            return self.last_gesture, confidence, landmarks_pixel