"""
车辆检测 + 车牌识别服务
核心方案：HyperLPR3 全图车牌检测与识别（主），YOLOv8 车辆检测（辅）

模型说明：
- HyperLPR3 内置的检测/识别模型基于 CCPD 数据集训练，专为中国车牌优化
- YOLOv8 使用 COCO 预训练权重，用于检测车辆（car/truck/bus）

CCPD 数据集：https://github.com/zexi-liu7/CCPD
"""
import cv2
import numpy as np
import hyperlpr3 as lpr3
from ultralytics import YOLO
from typing import Optional
from difflib import SequenceMatcher
from app.utils.logger import logger

# ─── HyperLPR3 plate_type → 车牌颜色 ──────────────────────────
PLATE_COLOR_MAP = {
    0: "blue",     # 蓝牌（普通燃油车）
    1: "yellow",   # 黄牌（单层）
    2: "white",    # 白牌（警车/公车）
    3: "green",    # 绿牌（新能源）
    4: "black",    # 黑牌（港澳）
    5: "yellow",   # 香港单层
    6: "yellow",   # 香港双层
    7: "yellow",   # 澳门单层
    8: "yellow",   # 澳门双层
    9: "yellow",   # 黄牌（双层）
}

# ─── COCO 车辆类别 ─────────────────────────────
VEHICLE_CLASSES = [2, 5, 7]  # car, bus, truck
COCO_CLASS_NAMES = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}


def enhance_image(image: np.ndarray) -> np.ndarray:
    """
    图像预增强：提升低光照/对比度条件下的车牌识别率
    使用 CLAHE（对比度受限自适应直方图均衡化）
    """
    # 转换为 LAB 色彩空间，对 L 通道做 CLAHE
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    l = clahe.apply(l)
    enhanced = cv2.merge([l, a, b])
    enhanced = cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)
    return enhanced


class PlateRecognizer:
    """
    HyperLPR3 车牌识别器
    在全图上直接检测+识别车牌（内置 CCPD 训练的模型）
    """

    def __init__(self, detect_level: int = None):
        logger.info("正在加载 HyperLPR3 模型（基于 CCPD 数据集训练）")
        if detect_level is None:
            detect_level = lpr3.DETECT_LEVEL_HIGH
        self.catcher = lpr3.LicensePlateCatcher(detect_level=detect_level)
        logger.info("HyperLPR3 模型加载完成")

    def detect_on_full_image(self, image: np.ndarray) -> list[dict]:
        """
        在全图上检测并识别车牌
        先做 CLAHE 增强提高低光照场景下的识别率
        """
        # 图像增强
        enhanced = enhance_image(image)

        # 同时用原图和增强图检测，提高召回率
        all_results = []
        for img in [image, enhanced]:
            try:
                raw_results = self.catcher(img)
                all_results.extend(raw_results)
            except Exception as e:
                logger.warning(f"HyperLPR3 检测异常: {e}")

        # 去重：同一车牌号只取置信度最高的
        seen = {}
        for code, confidence, type_idx, box in all_results:
            if code not in seen or confidence > seen[code][0]:
                seen[code] = (confidence, type_idx, box)

        results = []
        for code, (confidence, type_idx, box) in seen.items():
            conf = round(float(confidence), 4)
            if conf < 0.5:  # 低置信度丢弃，避免错误识别
                continue
            x1, y1, x2, y2 = map(int, box)
            color = PLATE_COLOR_MAP.get(type_idx, "blue")
            results.append({
                "plate_no": code,
                "color": color,
                "confidence": conf,
                "bbox": {
                    "x": x1,
                    "y": y1,
                    "width": x2 - x1,
                    "height": y2 - y1,
                },
            })

        logger.info(f"HyperLPR3 识别到 {len(results)} 个车牌")
        return results


class VehicleDetector:
    """YOLOv8 车辆检测器（辅助功能）"""

    def __init__(self, model_path: str = "yolov8n.pt", conf: float = 0.5):
        logger.info(f"正在加载 YOLOv8 模型: {model_path}")
        self.model = YOLO(model_path)
        self.conf = conf
        logger.info("YOLOv8 模型加载完成")

    def detect(self, image: np.ndarray) -> list[dict]:
        """检测车辆，返回 bbox + 类型（car/bus/truck）"""
        results = self.model(image, classes=VEHICLE_CLASSES,
                             conf=self.conf, verbose=False)
        vehicles = []
        if results[0].boxes is not None:
            boxes = results[0].boxes.xyxy.cpu().numpy()
            confs = results[0].boxes.conf.cpu().numpy()
            cls_ids = results[0].boxes.cls.cpu().numpy()
            for box, conf, cls_id in zip(boxes, confs, cls_ids):
                x1, y1, x2, y2 = map(int, box.tolist())
                cls_int = int(cls_id)
                vehicles.append({
                    "bbox": {"x": x1, "y": y1,
                             "width": x2 - x1, "height": y2 - y1},
                    "confidence": float(conf),
                    "class_id": cls_int,
                    "class_name": COCO_CLASS_NAMES.get(cls_int, "unknown"),
                })
        return vehicles


def _match_plate_to_vehicle(plate_bbox: dict, vehicle_bboxes: list[dict]) -> Optional[dict]:
    """判断车牌中心点在哪个车辆框内，返回匹配的车辆信息（含类型）"""
    px = plate_bbox["x"] + plate_bbox["width"] // 2
    py = plate_bbox["y"] + plate_bbox["height"] // 2
    for v in vehicle_bboxes:
        vb = v["bbox"]
        if vb["x"] <= px <= vb["x"] + vb["width"] and \
           vb["y"] <= py <= vb["y"] + vb["height"]:
            return v
    return None


# ─── 模块级单例 ───────────────────────────
_recognizer: Optional[PlateRecognizer] = None
_detector: Optional[VehicleDetector] = None


def get_recognizer() -> PlateRecognizer:
    global _recognizer
    if _recognizer is None:
        _recognizer = PlateRecognizer()
    return _recognizer


def get_detector() -> VehicleDetector:
    global _detector
    if _detector is None:
        _detector = VehicleDetector()
    return _detector


def recognize_plates(image: np.ndarray) -> list[dict]:
    """
    车牌识别完整 pipeline

    策略：
    1. HyperLPR3 全图检测+识别车牌（核心，模型基于 CCPD 训练）
    2. YOLOv8 车辆检测（辅助，用于车牌→车辆归属）

    返回 PlateResult[] 格式（符合前端接口文档）
    """
    recognizer = get_recognizer()

    # 1. HyperLPR3 全图车牌检测
    plates = recognizer.detect_on_full_image(image)

    if not plates:
        logger.info("未识别到车牌")
        return []

    # 2. YOLOv8 车辆检测（辅助匹配 carId）
    detector = get_detector()
    vehicles = detector.detect(image)

    # 3. 组装结果（含车辆类型）
    results = []
    seen_plates = set()
    for i, plate in enumerate(plates):
        if plate["plate_no"] in seen_plates:
            continue
        seen_plates.add(plate["plate_no"])

        # 匹配车牌所属车辆
        matched_vehicle = _match_plate_to_vehicle(plate["bbox"], vehicles)
        vehicle_type = matched_vehicle["class_name"] if matched_vehicle else "unknown"

        results.append({
            "carId": i + 1,
            "plateNo": plate["plate_no"],
            "vehicleType": vehicle_type,
            "color": plate["color"],
            "confidence": plate["confidence"],
            "bbox": plate["bbox"],
        })

    logger.info(f"最终返回 {len(results)} 个车牌识别结果")
    return results


# ─── 视频识别 ──────────────────────────────
VIDEO_EXTRACT_INTERVAL = 30  # 每隔 30 帧取一帧


def _plate_core(plate_no: str) -> str:
    """提取车牌号中的核心字母数字部分（去掉中文前缀，便于模糊匹配）"""
    core = ""
    for ch in plate_no:
        if ch.isascii() and (ch.isalnum() or ch in "-·"):
            core += ch
    return core.upper()


def _plates_are_same(a: str, b: str, threshold: float = 0.55) -> bool:
    """判断两个车牌号是否指向同一物理车牌（模糊匹配）"""
    if a == b:
        return True
    # 提取核心字母数字部分
    core_a = _plate_core(a)
    core_b = _plate_core(b)
    if not core_a or not core_b:
        return False
    # 核心里有相同的字母数字段（后 5 位稳定部分匹配）
    suffix_a = core_a[-5:]
    suffix_b = core_b[-5:]
    if suffix_a == suffix_b:
        return True
    # 编辑距离相似度
    from difflib import SequenceMatcher
    ratio = SequenceMatcher(None, core_a, core_b).ratio()
    return ratio >= threshold


def recognize_plates_from_video(video_bytes: bytes) -> list[dict]:
    """
    视频车牌识别 pipeline

    策略：
    1. 写入临时文件，用 OpenCV VideoCapture 逐帧读取
    2. 约每秒取一帧进行识别
    3. 模糊去重合并所有帧的车牌结果
    """
    import tempfile, os

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        tmp.write(video_bytes)
        tmp_path = tmp.name

    try:
        cap = cv2.VideoCapture(tmp_path)
        if not cap.isOpened():
            logger.error("无法打开视频文件")
            return []

        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps <= 0:
            fps = 30
        frame_interval = max(1, round(fps))  # ～1 帧/秒

        # 收集所有帧的原始结果
        raw_results: list[dict] = []
        frame_idx = 0

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            if frame_idx % frame_interval == 0:
                timestamp = round(frame_idx / fps, 2)
                plates = recognize_plates(frame)
                for p in plates:
                    p["timestamp"] = timestamp
                    raw_results.append(p)

            frame_idx += 1

        cap.release()

        # ── 模糊去重 ──
        # 按置信度降序排列，高置信度优先保留
        raw_results.sort(key=lambda x: x["confidence"], reverse=True)

        merged = []
        for p in raw_results:
            found = False
            for m in merged:
                if _plates_are_same(p["plateNo"], m["plateNo"]):
                    found = True
                    # 保留最高置信度的车牌号
                    if p["confidence"] > m["confidence"]:
                        m["plateNo"] = p["plateNo"]
                        m["confidence"] = p["confidence"]
                    # 用更宽泛的 bbox（安全第一）
                    m["bbox"]["x"] = min(m["bbox"]["x"], p["bbox"]["x"])
                    m["bbox"]["y"] = min(m["bbox"]["y"], p["bbox"]["y"])
                    m["bbox"]["width"] = max(
                        m["bbox"]["x"] + m["bbox"]["width"],
                        p["bbox"]["x"] + p["bbox"]["width"],
                    ) - m["bbox"]["x"]
                    m["bbox"]["height"] = max(
                        m["bbox"]["y"] + m["bbox"]["height"],
                        p["bbox"]["y"] + p["bbox"]["height"],
                    ) - m["bbox"]["y"]
                    # 更新 timestamp 范围
                    if "timestampStart" not in m:
                        m["timestampStart"] = m["timestamp"]
                    m["timestampStart"] = min(m["timestampStart"], p["timestamp"])
                    m["timestamp"] = max(m["timestamp"], p["timestamp"])
                    break
            if not found:
                merged.append(p)

        # 重新编号 carId
        for i, m in enumerate(merged):
            m["carId"] = i + 1
            # 如果有时间范围，标记
            if "timestampStart" in m and m["timestampStart"] != m["timestamp"]:
                m["timestampRange"] = f'{m["timestampStart"]}s-{m["timestamp"]}s'
            m.pop("timestampStart", None)

        logger.info(
            f"视频识别完成: 共处理 {frame_idx} 帧, "
            f"原始检测 {len(raw_results)} 条, "
            f"合并去重后 {len(merged)} 个车牌"
        )
        return merged

    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


# ─── CCPD 数据集批量验证工具 ───────────────
def evaluate_on_ccpd(ccpd_dir: str, max_samples: int = 100):
    """
    在 CCPD 数据集上评估车牌识别效果

    用法:
        from app.services.plate_recognition import evaluate_on_ccpd
        evaluate_on_ccpd("path/to/ccpd/images", max_samples=200)

    CCPD 数据集下载: https://github.com/zexi-liu7/CCPD
    图片命名格式: <area>-<angle>&<bbox>&<vertices>-<plate_code>-...
    """
    import os, glob
    recognizer = get_recognizer()

    image_paths = glob.glob(os.path.join(ccpd_dir, "*.jpg"))[:max_samples]
    if not image_paths:
        logger.error(f"未在 {ccpd_dir} 中找到 CCPD 图片")
        return

    total = len(image_paths)
    detected = 0
    correct = 0

    for path in image_paths:
        img = cv2.imread(path)
        if img is None:
            continue

        # 从文件名解析真实车牌号（CCPD 格式）
        basename = os.path.basename(path)
        parts = basename.split("-")
        if len(parts) >= 5:
            # 第5部分是车牌号编码
            plate_code_encoded = parts[4].split("_")
            # 解码略（CCPD 有特定映射表）
            pass

        # 识别
        results = recognizer.detect_on_full_image(img)
        if results:
            detected += 1
            # 这里可以加车牌号比对逻辑

        logger.info(f"[{detected}/{total}] 检测到车牌: {len(results)} 个")

    logger.info(f"CCPD 评估完成: 共 {total} 张, 检测到车牌 {detected} 张")
