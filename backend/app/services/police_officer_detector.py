"""YOLO-World based traffic-police detector for police-only gesture mode."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np

from app.utils.logger import logger


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


def _env_list(name: str, default: str) -> list[str]:
    raw = os.getenv(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


def _env_classes() -> tuple[list[str], set[str], set[str]]:
    positives = _env_list(
        "CARMATE_POLICE_ONLY_CLASSES",
        "traffic police officer,traffic policeman,traffic controller,traffic officer directing traffic",
    )
    negatives = _env_list(
        "CARMATE_POLICE_ONLY_NEGATIVE_CLASSES",
        "person,pedestrian,ordinary person,civilian,bystander,man,woman,driver,cyclist,worker,tourist,adult,child",
    )
    classes = positives + negatives
    if os.getenv("CARMATE_POLICE_ONLY_ADD_BACKGROUND", "1").lower() in {"1", "true", "yes"}:
        classes.append("")
    return classes, set(positives), set(negatives)


POLICE_ONLY_MODEL = os.getenv("CARMATE_POLICE_ONLY_DETECT_MODEL", "yolov8s-worldv2.pt")
POLICE_ONLY_CONF = _env_float("CARMATE_POLICE_ONLY_DETECT_CONF", 0.60)
POLICE_ONLY_CANDIDATE_CONF = _env_float("CARMATE_POLICE_ONLY_CANDIDATE_CONF", 0.05)
POLICE_ONLY_POSITIVE_MARGIN = _env_float("CARMATE_POLICE_ONLY_POSITIVE_MARGIN", 0.20)
POLICE_ONLY_IMGSZ = _env_int("CARMATE_POLICE_ONLY_DETECT_IMGSZ", 640)


@dataclass
class PoliceOfficerDetection:
    detected: bool
    confidence: float = 0.0
    class_name: str = ""
    box: Optional[list[float]] = None
    candidate_confidence: float = 0.0
    candidate_class_name: str = ""
    negative_confidence: float = 0.0
    negative_class_name: str = ""
    reject_reason: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "policeDetected": self.detected,
            "policeConfidence": round(float(self.confidence), 4),
            "policeClass": self.class_name,
            "policeBox": self.box,
            "policeCandidateConfidence": round(float(self.candidate_confidence), 4),
            "policeCandidateClass": self.candidate_class_name,
            "policeNegativeConfidence": round(float(self.negative_confidence), 4),
            "policeNegativeClass": self.negative_class_name,
            "policeRejectReason": self.reject_reason,
            "policeDetectionError": self.error,
        }


class PoliceOfficerDetector:
    def __init__(self) -> None:
        try:
            from ultralytics import YOLO
        except Exception as exc:
            raise RuntimeError("ultralytics is required for YOLO-World police-only mode") from exc

        self.classes, self.positive_classes, self.negative_classes = _env_classes()
        self.model = YOLO(POLICE_ONLY_MODEL)
        if hasattr(self.model, "set_classes"):
            self.model.set_classes(self.classes)
        else:
            raise RuntimeError("current ultralytics version does not support YOLO-World set_classes")
        logger.info(
            "YOLO-World traffic-police detector loaded: model=%s, accept_conf=%.2f, margin=%.2f, positive=%s, negative=%s",
            POLICE_ONLY_MODEL,
            POLICE_ONLY_CONF,
            POLICE_ONLY_POSITIVE_MARGIN,
            sorted(self.positive_classes),
            sorted(self.negative_classes),
        )

    def detect(self, img_bgr: np.ndarray) -> PoliceOfficerDetection:
        if img_bgr is None or img_bgr.size == 0:
            return PoliceOfficerDetection(False, error="empty image")

        img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        results = self.model.predict(img_rgb, conf=POLICE_ONLY_CANDIDATE_CONF, imgsz=POLICE_ONLY_IMGSZ, verbose=False)
        if not results:
            return PoliceOfficerDetection(False)

        result = results[0]
        boxes = getattr(result, "boxes", None)
        if boxes is None or len(boxes) == 0:
            return PoliceOfficerDetection(False)

        names = getattr(result, "names", {}) or {}
        confs = boxes.conf.detach().cpu().numpy()
        cls_ids = boxes.cls.detach().cpu().numpy().astype(int) if boxes.cls is not None else np.full(len(confs), -1)
        positives: list[tuple[float, int, str]] = []
        negatives: list[tuple[float, int, str]] = []
        for i, cls_id in enumerate(cls_ids):
            class_name = names.get(int(cls_id), self.classes[int(cls_id)] if 0 <= int(cls_id) < len(self.classes) else "")
            class_name = str(class_name).strip()
            if class_name in self.positive_classes:
                positives.append((float(confs[i]), i, class_name))
            elif class_name in self.negative_classes:
                negatives.append((float(confs[i]), i, class_name))
        if not positives:
            negative = max(negatives, key=lambda item: item[0]) if negatives else (0.0, -1, "")
            return PoliceOfficerDetection(
                False,
                negative_confidence=negative[0],
                negative_class_name=negative[2],
                reject_reason="no traffic-police candidate",
            )

        confidence, idx, class_name = max(positives, key=lambda item: item[0])
        negative_confidence, _neg_idx, negative_class_name = max(negatives, key=lambda item: item[0]) if negatives else (0.0, -1, "")
        if confidence < POLICE_ONLY_CONF:
            return PoliceOfficerDetection(
                False,
                candidate_confidence=confidence,
                candidate_class_name=class_name,
                negative_confidence=negative_confidence,
                negative_class_name=negative_class_name,
                reject_reason=f"traffic-police confidence below {POLICE_ONLY_CONF:.2f}",
            )
        if negative_confidence and confidence < negative_confidence + POLICE_ONLY_POSITIVE_MARGIN:
            return PoliceOfficerDetection(
                False,
                candidate_confidence=confidence,
                candidate_class_name=class_name,
                negative_confidence=negative_confidence,
                negative_class_name=negative_class_name,
                reject_reason="ordinary-person candidate is too close or stronger",
            )

        xyxy = boxes.xyxy[idx].detach().cpu().numpy().astype(float).tolist()
        return PoliceOfficerDetection(
            detected=True,
            confidence=confidence,
            class_name=class_name,
            box=[round(v, 2) for v in xyxy],
            candidate_confidence=confidence,
            candidate_class_name=class_name,
            negative_confidence=negative_confidence,
            negative_class_name=negative_class_name,
        )


_detector: PoliceOfficerDetector | None = None


def get_police_officer_detector() -> PoliceOfficerDetector:
    global _detector
    if _detector is None:
        _detector = PoliceOfficerDetector()
    return _detector


def detect_police_officer(img_bgr: np.ndarray) -> PoliceOfficerDetection:
    try:
        return get_police_officer_detector().detect(img_bgr)
    except Exception as exc:
        logger.exception("YOLO-World traffic-police detection failed: %s", exc)
        return PoliceOfficerDetection(False, error=str(exc))
