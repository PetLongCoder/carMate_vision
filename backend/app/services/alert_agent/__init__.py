"""
告警智能体 — 核心类型定义
=======================
AlertAgent 系统使用的枚举和数据类。
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class AlertLevel(str, Enum):
    """告警级别"""
    INFO = "info"          # 提示 — 偶发异常，不影响系统运行
    WARNING = "warning"    # 警告 — 持续异常，需要关注
    CRITICAL = "critical"  # 严重 — 系统功能受损，需要立即处置


# 异常类型中文标签
ANOMALY_TYPE_LABELS: dict[str, str] = {
    "plate_recognition_failure": "车牌识别失败",
    "plate_model_load_failure": "车牌模型加载失败",
    "plate_frame_decode_failure": "车牌帧解码失败",
    "police_gesture_low_confidence": "交警手势置信度偏低",
    "police_gesture_model_failure": "交警手势模型加载失败",
    "police_gesture_inference_error": "交警手势推理错误",
    "driver_gesture_low_confidence": "车主手势置信度偏低",
    "driver_gesture_model_failure": "车主手势模型加载失败",
    "auth_unauthorized": "未授权访问",
    "auth_login_failure": "登录失败",
    "llm_api_timeout": "LLM API 超时",
    "llm_api_error": "LLM API 调用失败",
    "llm_token_excess": "LLM Token 超额",
    "system_error": "系统错误",
}


# 来源模块中文标签
SOURCE_LABELS: dict[str, str] = {
    "plate_recognition": "车牌识别",
    "police_gesture": "交警手势",
    "driver_gesture": "车主手势",
    "auth": "用户认证",
    "llm_api": "LLM API",
    "system": "系统",
}


@dataclass
class AnomalyEvent:
    """标准化异常事件"""
    source: str                                    # 来源模块
    anomaly_type: str                              # 异常类型
    title: str                                     # 简短标题
    detail: dict = field(default_factory=dict)     # 详细信息
    timestamp: float = field(default_factory=time.time)
    severity_hint: Optional[AlertLevel] = None     # 建议告警级别
    user_id: Optional[int] = None                  # 关联用户 ID（系统级告警为 None）

    @property
    def source_label(self) -> str:
        return SOURCE_LABELS.get(self.source, self.source)

    @property
    def anomaly_type_label(self) -> str:
        return ANOMALY_TYPE_LABELS.get(self.anomaly_type, self.anomaly_type)


@dataclass
class AlertDecision:
    """告警决策结果"""
    level: AlertLevel
    should_alert: bool = True
    reason: str = ""


# 告警级别对应的飞书卡片颜色
FEISHU_LEVEL_COLORS: dict[AlertLevel, str] = {
    AlertLevel.INFO: "blue",
    AlertLevel.WARNING: "orange",
    AlertLevel.CRITICAL: "red",
}

# 告警级别对应的中文标签
LEVEL_LABELS: dict[AlertLevel, str] = {
    AlertLevel.INFO: "提示",
    AlertLevel.WARNING: "警告",
    AlertLevel.CRITICAL: "严重",
}
