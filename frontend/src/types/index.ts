// 车牌识别结果
export interface PlateResult {
  carId: number;
  plateNo: string;
  color: string;
  confidence: number;
  bbox: BBox;
}

export interface BBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

// 交警手势识别结果
export interface PoliceGestureResult {
  gesture: string;
  gestureId: number;
  confidence: number;
  timestamp: number;
}

// 车主手势识别结果
export interface DriverGestureResult {
  gesture: string;
  gestureId: number;
  confidence: number;
  controlAction?: ControlAction;
}

export interface ControlAction {
  type: 'volume_up' | 'volume_down' | 'temperature_up' | 'temperature_down' | 'next_track' | 'prev_track' | 'play_pause';
  label: string;
}

// 告警
export interface Alert {
  id: number;
  level: AlertLevel;
  title: string;
  summary: string;
  source: string;
  createdAt: string;
  acknowledged: boolean;
}

export type AlertLevel = 'info' | 'warning' | 'critical';

// 历史记录
export interface HistoryRecord {
  id: number;
  type: 'plate' | 'police_gesture' | 'driver_gesture';
  image: string;
  result: Record<string, unknown>;
  createdAt: string;
}

// 统计数据
export interface DashboardStats {
  totalPlates: number;
  totalGestures: number;
  totalAlerts: number;
  unreadAlerts: number;
}

// API 通用响应
export interface ApiResponse<T> {
  code: number;
  message: string;
  data: T;
}
