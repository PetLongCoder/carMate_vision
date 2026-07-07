"""
实时车牌追踪服务
================

基于 IoU 匹配实现帧间车牌 ID 稳定追踪, 用于视频流和上传视频的实时处理。

核心组件:
- TrackedPlate: 单个追踪车牌的状态 + 历史轨迹
- PlateTracker: 帧间 IoU 贪心匹配追踪器, 稳定分配 trackId
- VideoStreamProcessor: 视频流处理, 帧检测 + 追踪 + 标注绘制

配合 WebSocket 实现识别结果的实时前端展示。
"""
import base64
import cv2
import numpy as np
from typing import Optional

from app.services.plate_recognition import recognize_plates
from app.utils.logger import logger


# ─── 车牌颜色 → BGR 颜色映射 (用于绘制标注框) ────────────
PLATE_BGR_MAP: dict[str, tuple[int, int, int]] = {
    "blue":   (255, 100,   0),   # 蓝牌
    "green":  ( 0,  200,   0),   # 绿牌
    "yellow": ( 0,  200, 200),   # 黄牌
    "white":  (255, 255, 255),   # 白牌
    "black":  ( 0,    0,   0),   # 黑牌
}
DEFAULT_BGR = (0, 100, 255)  # 橙色


# ═══════════════════════════════════════════════════════════
#  IoU 工具
# ═══════════════════════════════════════════════════════════

def compute_iou(box_a: dict, box_b: dict) -> float:
    """
    计算两个 bbox 的交并比 (IoU)

    box 格式: {"x": int, "y": int, "width": int, "height": int}
    """
    x1 = max(box_a["x"], box_b["x"])
    y1 = max(box_a["y"], box_b["y"])
    x2 = min(box_a["x"] + box_a["width"], box_b["x"] + box_b["width"])
    y2 = min(box_a["y"] + box_a["height"], box_b["y"] + box_b["height"])

    inter = max(0, x2 - x1) * max(0, y2 - y1)
    area_a = box_a["width"] * box_a["height"]
    area_b = box_b["width"] * box_b["height"]
    union = area_a + area_b - inter

    return inter / union if union > 0 else 0.0


# ═══════════════════════════════════════════════════════════
#  TrackedPlate — 单个车牌追踪状态
# ═══════════════════════════════════════════════════════════

class TrackedPlate:
    """跨帧追踪的一个车牌, 包含完整的历史轨迹"""

    def __init__(self, track_id: int, detection: dict,
                 frame_number: int, timestamp: float):
        self.track_id = track_id
        self.plate_no = detection["plateNo"]
        self.color = detection["color"]
        self.vehicle_type = detection.get("vehicleType", "unknown")
        self.confidence = detection["confidence"]
        self.bbox = detection["bbox"].copy()

        self.first_seen = timestamp
        self.last_seen = timestamp
        self.first_frame = frame_number
        self.last_frame = frame_number
        self.appearances = 1
        self.confidence_sum = self.confidence

        self.history: list[dict] = [{
            "frame": frame_number,
            "timestamp": timestamp,
            "bbox": self.bbox.copy(),
            "confidence": self.confidence,
            "plateNo": self.plate_no,
        }]

    def update(self, detection: dict, frame_number: int, timestamp: float):
        """用新的检测帧更新追踪状态"""
        self.last_seen = timestamp
        self.last_frame = frame_number
        self.appearances += 1
        self.confidence_sum += detection["confidence"]
        self.confidence = round(self.confidence_sum / self.appearances, 4)
        self.bbox = detection["bbox"].copy()

        # 若新检测置信度高于历史最佳, 更新车牌号 (防抖动)
        if detection["confidence"] > self.confidence:
            self.plate_no = detection["plateNo"]

        self.history.append({
            "frame": frame_number,
            "timestamp": timestamp,
            "bbox": detection["bbox"].copy(),
            "confidence": detection["confidence"],
            "plateNo": detection["plateNo"],
        })

    def to_dict(self, current_only: bool = False) -> dict:
        """序列化为可 JSON 序列化的字典"""
        d = {
            "trackId": self.track_id,
            "plateNo": self.plate_no,
            "color": self.color,
            "vehicleType": self.vehicle_type,
            "confidence": self.confidence,
            "bbox": self.bbox,
            "appearances": self.appearances,
            "firstSeen": round(self.first_seen, 2),
        }
        if not current_only:
            d["lastSeen"] = round(self.last_seen, 2)
            d["history"] = self.history
        return d


# ═══════════════════════════════════════════════════════════
#  PlateTracker — 帧间贪心 IoU 追踪器
# ═══════════════════════════════════════════════════════════

class PlateTracker:
    """
    车牌帧间追踪器

    使用贪心 IoU 匹配策略, 将当前帧的检测结果关联到已有追踪上。
    匹配不上的检测创建新追踪; 连续 N 帧未匹配的追踪标记为丢失。

    参数:
        iou_threshold:  IoU 匹配阈值 (默认 0.3)
        max_lost_frames: 丢失帧数上限, 超过则移除追踪 (默认 30)
        min_appearances: 视为稳定追踪的最小出现次数 (默认 3, 过滤单帧误检)
    """

    def __init__(self, iou_threshold: float = 0.3,
                 max_lost_frames: int = 30,
                 min_appearances: int = 3):
        self.iou_threshold = iou_threshold
        self.max_lost_frames = max_lost_frames
        self.min_appearances = min_appearances
        self._next_id = 1
        self._active: dict[int, TrackedPlate] = {}
        self._lost: dict[int, TrackedPlate] = {}
        self._all: dict[int, TrackedPlate] = {}
        self._total_processed = 0

    # ── 属性 ────────────────────────────────────────

    @property
    def active_tracks(self) -> list[TrackedPlate]:
        return list(self._active.values())

    @property
    def all_tracks(self) -> list[TrackedPlate]:
        return list(self._all.values())

    @property
    def total_processed(self) -> int:
        return self._total_processed

    # ── 生命周期 ────────────────────────────────────

    def reset(self):
        """重置追踪器全部状态"""
        self._next_id = 1
        self._active.clear()
        self._lost.clear()
        self._all.clear()
        self._total_processed = 0

    # ── 核心更新 ────────────────────────────────────

    def update(self, plates: list[dict], frame_number: int,
               timestamp: float) -> list[dict]:
        """
        更新追踪状态, 返回当前帧的有效追踪列表

        Args:
            plates:   recognize_plates() 的单帧输出
            frame_number:  帧序号
            timestamp:     时间戳 (秒)

        Returns:
            本帧追踪结果列表, 每项含 trackId / plateNo / color / bbox / ...
        """
        self._total_processed += 1

        if not plates:
            self._clean_lost(frame_number)
            return []

        # 1) 贪心匹配: 检测 → 活跃追踪
        matched, unmatched_indices = self._greedy_match(plates)

        # 2) 更新已匹配的追踪
        for det_idx, track_id in matched.items():
            self._active[track_id].update(plates[det_idx], frame_number, timestamp)

        # 3) 未匹配检测 → 创建新追踪
        for det_idx in unmatched_indices:
            det = plates[det_idx]
            tp = TrackedPlate(self._next_id, det, frame_number, timestamp)
            self._active[self._next_id] = tp
            self._all[self._next_id] = tp
            self._next_id += 1

        # 4) 清理超时未出现的追踪
        self._clean_lost(frame_number)

        # 5) 组装本帧结果
        return [
            tp.to_dict(current_only=True)
            for tp in self._active.values()
            if tp.last_frame == frame_number
        ]

    def _greedy_match(self, detections: list[dict]) -> tuple[dict[int, int], list[int]]:
        """贪心 IoU 匹配: 每个检测匹配 IoU 最高的活跃追踪"""
        matched: dict[int, int] = {}
        used_tracks: set[int] = set()

        for det_idx, det in enumerate(detections):
            best_iou = self.iou_threshold
            best_tid: Optional[int] = None
            dbox = det["bbox"]

            for tid, track in self._active.items():
                if tid in used_tracks:
                    continue
                iou_val = compute_iou(dbox, track.bbox)
                if iou_val > best_iou:
                    best_iou = iou_val
                    best_tid = tid

            if best_tid is not None:
                matched[det_idx] = best_tid
                used_tracks.add(best_tid)

        unmatched = [i for i in range(len(detections)) if i not in matched]
        return matched, unmatched

    def _clean_lost(self, current_frame: int):
        """将超时未出现的活跃追踪移入丢失列表"""
        to_remove = []
        for tid, track in self._active.items():
            if current_frame - track.last_frame > self.max_lost_frames:
                to_remove.append(tid)
        for tid in to_remove:
            self._lost[tid] = self._active.pop(tid)

    # ── 汇总 ────────────────────────────────────────

    def get_summary(self, min_appearances: Optional[int] = None) -> list[dict]:
        """返回所有稳定追踪的汇总 (用于前端摘要表格)"""
        threshold = min_appearances if min_appearances is not None else self.min_appearances
        return [
            tp.to_dict()
            for tp in self._all.values()
            if tp.appearances >= threshold
        ]


# ═══════════════════════════════════════════════════════════
#  VideoStreamProcessor — 视频流处理器
# ═══════════════════════════════════════════════════════════

class VideoStreamProcessor:
    """
    视频帧处理器

    封装单帧的检测 + 追踪 + 标注绘制流程。
    支持本地视频文件和 RTSP/RTMP 流。

    参数:
        tracker:                PlateTracker 实例 (默认新建)
        process_every_n_frames: 每 N 帧处理一次 (默认 3, 即跳过中间帧)
    """

    def __init__(self, tracker: Optional[PlateTracker] = None,
                 process_every_n_frames: int = 3):
        self.tracker = tracker or PlateTracker()
        self.process_every_n_frames = max(1, process_every_n_frames)
        self._frame_count = 0
        self._fps = 30.0

    # ── 单帧处理 ────────────────────────────────────

    def process_frame(self, frame: np.ndarray, fps: float = 30.0) -> tuple[list[dict], np.ndarray]:
        """
        处理一帧: 检测 → 追踪 → 标注

        Args:
            frame:  BGR 图像 (OpenCV 格式)
            fps:    视频帧率, 用于计算时间戳

        Returns:
            (tracking_results, annotated_frame)
        """
        self._fps = fps if fps > 0 else self._fps
        frame_number = self._frame_count
        self._frame_count += 1

        # 跳帧: 非处理帧只做追踪清理
        if frame_number % self.process_every_n_frames != 0:
            # 仍按帧推进追踪器的丢失计数
            self.tracker.update([], frame_number, frame_number / self._fps)
            return [], np.ndarray([])

        # 1) 车牌检测 (复用已有 pipeline)
        try:
            plates = recognize_plates(frame)
        except Exception as exc:
            logger.warning(f"帧 {frame_number} 检测异常: {exc}")
            plates = []

        # 2) 追踪
        timestamp = frame_number / self._fps
        tracking_results = self.tracker.update(plates, frame_number, timestamp)

        # 3) 标注帧
        annotated = self.draw_annotations(frame, tracking_results)

        return tracking_results, annotated

    def reset(self):
        """重置处理器和追踪器状态"""
        self._frame_count = 0
        self.tracker.reset()

    # ── 标注绘制 ────────────────────────────────────

    @staticmethod
    def draw_annotations(frame: np.ndarray, results: list[dict]) -> np.ndarray:
        """在帧上绘制检测框 + 车牌文字 + 追踪 ID"""
        annotated = frame.copy()
        h, w = annotated.shape[:2]

        for r in results:
            bbox = r["bbox"]
            x1 = max(0, int(bbox["x"]))
            y1 = max(0, int(bbox["y"]))
            x2 = min(w, int(bbox["x"] + bbox["width"]))
            y2 = min(h, int(bbox["y"] + bbox["height"]))

            box_color = PLATE_BGR_MAP.get(r["color"], DEFAULT_BGR)

            # ── 绘制矩形框 ──
            cv2.rectangle(annotated, (x1, y1), (x2, y2), box_color, 2)

            # ── 车牌号码标签 (框上方, 若空间不够则放框内) ──
            plate_text = f"{r['plateNo']}"
            color_text = r["color"]

            (tw, th), _ = cv2.getTextSize(plate_text, cv2.FONT_HERSHEY_SIMPLEX, 0.65, 2)
            label_bg_top = y1 - th - 8 if y1 > th + 8 else y1
            label_bg_bottom = label_bg_top + th + 6

            # 背景
            cv2.rectangle(annotated, (x1, label_bg_top),
                          (x1 + tw + 8, label_bg_bottom), box_color, -1)
            # 文字
            cv2.putText(annotated, plate_text, (x1 + 4, label_bg_bottom - 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)

            # ── 第二行: 颜色 + 置信度 (框下方) ──
            info_text = f"#{r['trackId']} {color_text} {r.get('confidence', 0):.0%}"
            cv2.putText(annotated, info_text, (x1, y2 + 18),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, box_color, 1)

            # ── 左上角帧信息 ──
            cv2.putText(annotated, f"Frame {r.get('_frame', '')}", (8, 22),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

        # 若没有任何检测, 在左上角提示
        if not results:
            cv2.putText(annotated, "No plate detected", (8, 22),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 100, 100), 1)

        return annotated

    @staticmethod
    def frame_to_jpeg_base64(frame: np.ndarray, quality: int = 80) -> str:
        """将 OpenCV 帧编码为 JPEG base64 字符串"""
        _, buffer = cv2.imencode(".jpg", frame,
                                 [cv2.IMWRITE_JPEG_QUALITY, quality])
        return base64.b64encode(buffer).decode("utf-8")
