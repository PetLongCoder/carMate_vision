from pydantic import BaseModel
from typing import Optional, List


# ===== 车主手势识别（负责的模块）=====
class ControlAction(BaseModel):
    type: str   # volume_up, volume_down, temperature_up, temperature_down, next_track, prev_track, play_pause
    label: str  # 中文描述


class DriverGestureResult(BaseModel):
    gesture: str                 # 中文手势名称
    gestureId: int               # 0~6 编号
    confidence: float            # 0~1
    controlAction: Optional[ControlAction] = None


# ===== 车牌识别（供队友参考）=====
class BBox(BaseModel):
    x: float
    y: float
    width: float
    height: float


class PlateResult(BaseModel):
    carId: int
    plateNo: str
    vehicleType: str   # car / bus / truck / unknown
    color: str   # blue / green / yellow
    confidence: float
    bbox: BBox


# ===== 交警手势（供队友参考）=====
class PoliceGestureResult(BaseModel):
    gesture: str
    gestureId: int   # 0~7
    confidence: float
    timestamp: int


# ===== 告警（供队友参考）=====
class Alert(BaseModel):
    id: int
    level: str   # info / warning / critical
    title: str
    summary: str
    source: str
    createdAt: str
    acknowledged: bool


# ===== 历史记录（供队友参考）=====
class HistoryRecord(BaseModel):
    id: int
    type: str   # plate / police_gesture / driver_gesture
    image: str
    result: dict
    createdAt: str


# ===== 仪表盘统计（供队友参考）=====
class DashboardStats(BaseModel):
    totalPlates: int
    totalGestures: int
    totalAlerts: int
    unreadAlerts: int