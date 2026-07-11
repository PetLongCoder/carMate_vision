import cv2
import numpy as np
import mediapipe as mp
import torch
import torch.nn as nn
from typing import Tuple, List

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


class LSTMGestureTracker:
    def __init__(self, model_path: str = "app/models/gesture_model.pth"):
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

        self.buffer = []
        self.last_gesture = "unknown"
        self.stable_count = 0
        self.stable_threshold = 2

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

    def reset_state(self):
        self.buffer = []
        self.last_gesture = "unknown"
        self.stable_count = 0

    def _extract_landmarks(self, hand_landmarks) -> List[float]:
        landmarks = []
        for lm in hand_landmarks.landmark:
            landmarks.extend([lm.x, lm.y, lm.z])
        return landmarks

    def process_frame(self, image_bytes: bytes) -> Tuple[str, float, List]:
        np_arr = np.frombuffer(image_bytes, np.uint8)
        frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        if frame is None:
            return "unknown", 0.0, []

        # 镜像（与训练数据保持一致）
        frame = cv2.flip(frame, 1)

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        result = self.hands.process(rgb)

        landmarks_pixel = []
        if result.multi_hand_landmarks:
            hand_lm = result.multi_hand_landmarks[0]
            h, w, _ = frame.shape
            for lm in hand_lm.landmark:
                landmarks_pixel.append([lm.x * w, lm.y * h, lm.z * w])
            vec = self._extract_landmarks(hand_lm)
            self.buffer.append(vec)
        else:
            self.buffer.append([0.0] * 63)

        if len(self.buffer) > self.seq_length:
            self.buffer.pop(0)

        if len(self.buffer) < self.seq_length:
            return self.last_gesture, 0.0, landmarks_pixel

        input_tensor = torch.FloatTensor(np.array(self.buffer)).unsqueeze(0).to(self.device)
        with torch.no_grad():
            output = self.model(input_tensor)
            probs = torch.softmax(output, dim=1)
            confidence, pred_idx = torch.max(probs, 1)
            confidence = confidence.item()
            pred_idx = pred_idx.item()

        gesture_name = self.label_encoder.inverse_transform([pred_idx])[0]

        if gesture_name == self.last_gesture:
            self.stable_count += 1
        else:
            self.stable_count = 1
            self.last_gesture = gesture_name

        if self.stable_count >= self.stable_threshold and confidence > 0.35:
            return gesture_name, confidence, landmarks_pixel

        return self.last_gesture, confidence, landmarks_pixel