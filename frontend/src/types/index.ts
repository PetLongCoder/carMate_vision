// ============================================================
// 车牌识别结果
// ============================================================

export interface BBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface PlateResult {
  carId: number;
  plateNo: string;
  vehicleType: string;  // car / bus / truck / unknown
  color: string;
  confidence: number;
  bbox: BBox;
}

// ============================================================
// 实时追踪类型
// ============================================================

/** 帧检测结果 (WebSocket detection 消息) */
export interface FrameDetection {
  type: 'detection';
  sessionId: string;
  frameNumber: number;
  timestamp: number;
  fps: number;
  detections: TrackedPlateResult[];
  processingMs: number;
}

/** 单个追踪车牌 (帧检测结果中的一项) */
export interface TrackedPlateResult {
  trackId: number;
  plateNo: string;
  color: string;
  vehicleType: string;
  confidence: number;
  bbox: BBox;
  appearances: number;
  firstSeen: number;
}

/** 会话状态 (WebSocket status 消息) */
export interface SessionStatusMsg {
  type: 'status';
  sessionId: string;
  status: 'pending' | 'processing' | 'completed' | 'error' | 'stopped';
  progress: number;
  framesProcessed: number;
  totalFrames: number;
}

/** 追踪汇总 (WebSocket summary 消息) */
export interface TrackingSummary {
  type: 'summary';
  sessionId: string;
  totalFrames: number;
  processedFrames: number;
  duration: number;
  plates: TrackedPlateSummary[];
}

/** 稳定追踪车牌汇总 */
export interface TrackedPlateSummary {
  trackId: number;
  plateNo: string;
  color: string;
  vehicleType: string;
  confidence: number;
  firstSeen: number;
  lastSeen: number;
  appearances: number;
  bbox: BBox;
}

/** WebSocket 错误消息 */
export interface WsErrorMessage {
  type: 'error';
  sessionId?: string;
  message: string;
}

/** 联合类型: 所有可能的 WebSocket 消息 */
export type WsPlateMessage =
  | FrameDetection
  | SessionStatusMsg
  | TrackingSummary
  | WsErrorMessage;

/** 追踪会话信息 (REST API) */
export interface TrackingSessionInfo {
  sessionId: string;
  type: 'video' | 'stream';
  status: string;
  source: string;
  totalFrames: number;
  processedFrames: number;
  fps: number;
  wsConnections: number;
  createdAt: string;
  updatedAt: string;
  errorMessage: string | null;
}

/** 创建追踪会话响应 */
export interface TrackSessionResponse {
  sessionId: string;
  fileName: string;
  fileSize: number;
  totalFrames: number;
  status: string;
  wsEndpoint: string;
}

/** 启动流追踪响应 */
export interface StreamStartResponse {
  sessionId: string;
  name: string;
  url: string;
  status: string;
  wsEndpoint: string;
}

// ============================================================
// 交警手势识别结果
// ============================================================

export interface PoliceGestureResult {
  gesture: string;
  gestureId: number;
  confidence: number;
  timestamp: number;
}

// ============================================================
// 车主手势识别结果
// ============================================================

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

// ============================================================
// 告警
// ============================================================

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

// ============================================================
// 历史记录
// ============================================================

export interface HistoryRecord {
  id: number;
  type: 'plate' | 'police_gesture' | 'driver_gesture';
  image: string;
  result: Record<string, unknown>;
  createdAt: string;
}

// ============================================================
// 统计数据
// ============================================================

export interface DashboardStats {
  totalPlates: number;
  totalGestures: number;
  totalAlerts: number;
  unreadAlerts: number;
}

// ============================================================
// API 通用响应
// ============================================================

export interface ApiResponse<T> {
  code: number;
  message: string;
  data: T;
}

// ============================================================
// 用户认证
// ============================================================

export type UserRole = 'user' | 'admin';

export interface User {
  id: number;
  username: string;
  email?: string;
  phone?: string;
  role: UserRole;
}

export interface LoginRequest {
  username: string;
  password: string;
}

export interface PhoneLoginRequest {
  phone: string;
  code: string;
}

export interface EmailLoginRequest {
  email: string;
  code: string;
}

export type CodeScene = 'login' | 'register';

export interface SendSmsCodeRequest {
  phone: string;
  scene: CodeScene;
}

export interface SendEmailCodeRequest {
  email: string;
  scene: CodeScene;
}

export interface VerifySmsCodeRequest {
  phone: string;
  code: string;
}

export interface RegisterRequest {
  username: string;
  password: string;
  phone: string;
  code: string;
  email?: string;
}

export interface AuthResponse {
  token: string;
  user: User;
}
