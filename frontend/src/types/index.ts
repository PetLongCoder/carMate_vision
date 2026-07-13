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
  landmarks?: number[][];  // 手部关键点
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
  sourceLabel?: string;
  anomalyType?: string;
  anomalyTypeLabel?: string;
  impactScope?: string;
  suggestedActions?: string[];
  notifiedChannels?: string[];
  rawEvent?: Record<string, unknown>;
  createdAt: string;
  acknowledged: boolean;
  acknowledgedBy?: string | null;
  acknowledgedAt?: string | null;
}

export type AlertLevel = 'info' | 'warning' | 'critical';

// ── 告警统计 ──

export interface AlertStats {
  total: number;
  unacknowledged: number;
  todayCount: number;
  totalByLevel: Record<string, number>;
  byAnomalyType: Record<string, number>;
  dailyTrend: AlertDailyTrend[];
  avgResponseMinutes: number;
}

export interface AlertDailyTrend {
  date: string;
  info: number;
  warning: number;
  critical: number;
}

export interface AlertAnalysis {
  topAnomalyTypes: Array<{ type: string; label: string; count: number }>;
  sourceDistribution: Array<{ source: string; label: string; count: number }>;
  peakHours: Array<{ hour: number; count: number }>;
  ackRate: number;
  total: number;
  acknowledged: number;
}

export interface AnomalyTypeOption {
  value: string;
  label: string;
}

// ============================================================
// 历史记录
// ============================================================

export interface HistoryRecord {
  id: number;
  type: 'plate' | 'police_gesture' | 'driver_gesture';
  module?: string;
  module_label?: string;
  source_type?: string;
  source_label?: string;
  file_name?: string | null;
  success?: boolean;
  summary?: string | null;
  image: string;
  result: Record<string, unknown>;
  createdAt: string;
}

export interface HistoryListResponse {
  list: HistoryRecord[];
  total: number;
}

export interface HistoryTypeOption {
  value: string;
  label: string;
}

export interface AdminRecognitionRecord extends HistoryRecord {
  user_id?: number | null;
  username?: string | null;
}

export interface AdminRecognitionListResponse {
  list: AdminRecognitionRecord[];
  total: number;
  page: number;
  pageSize: number;
}

// ============================================================
// 统计数据
// ============================================================

export interface GestureBreakdown {
  policeRecords: number;
  driverRecords: number;
  policeRecordsSuccess: number;
  driverRecordsSuccess: number;
  policeInferenceLogs: number;
  policeInferenceLogsSuccess: number;
}

export interface TodayGestureBreakdown {
  policeRecords: number;
  driverRecords: number;
  policeRecordsSuccess: number;
  driverRecordsSuccess: number;
  policeInferenceLogs: number;
  policeInferenceLogsSuccess: number;
}

export interface DashboardStats {
  /** 手势识别记录累计（含未成功，含摄像头逐帧记录） */
  gestureRecordTotal: number;
  /** 今日新增手势识别记录 */
  gestureRecordToday: number;
  /** 累计识别成功次数 */
  gestureRecordSuccess: number;
  /** 今日识别成功次数 */
  gestureRecordTodaySuccess: number;
  totalPlates: number;
  /** @deprecated 与 gestureRecordTotal 相同，兼容旧代码 */
  totalGestures: number;
  /** @deprecated 与 gestureRecordToday 相同 */
  todayGestures: number;
  /** @deprecated 与 gestureRecordSuccess 相同 */
  successGestures: number;
  totalAlerts: number;
  unreadAlerts: number;
  gestureBreakdown: GestureBreakdown;
  todayGestureBreakdown: TodayGestureBreakdown;
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
  nickname?: string;
  avatar_url?: string;
  has_wechat?: boolean;
  login_methods?: string[];
}

export interface LoginRequest {
  username: string;
  password: string;
  portal?: UserRole;
}

export interface PhoneLoginRequest {
  phone: string;
  code: string;
}

export interface EmailLoginRequest {
  email: string;
  code: string;
}

export type CodeScene = 'login' | 'register' | 'bind' | 'rebind_new';
export type SecureCodeScene = 'unbind' | 'rebind_old' | 'delete' | 'change_password';
export type VerifyMethod = 'password' | 'phone' | 'email' | 'wechat';

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
  email_code?: string;
}

export interface AuthResponse {
  token: string;
  user: User;
}

export interface UpdateProfileRequest {
  nickname?: string;
}

export interface BindPhoneRequest {
  phone: string;
  code: string;
}

export interface BindEmailRequest {
  email: string;
  code: string;
}

export interface UnbindCodeRequest {
  code: string;
}

export interface RebindPhoneRequest {
  old_code: string;
  new_phone: string;
  new_code: string;
}

export interface RebindEmailRequest {
  old_code: string;
  new_email: string;
  new_code: string;
}

export interface DeleteAccountRequest {
  verify_method: VerifyMethod;
  password?: string;
  code?: string;
}

export interface ChangePasswordRequest {
  verify_method: VerifyMethod;
  old_password?: string;
  code?: string;
  new_password: string;
}

export interface WechatQrcodeResponse {
  state: string;
  confirm_url: string;
  qrcode_base64: string;
  expires_in: number;
  lan_ip: string;
  network_hint: string;
  step?: number;
}

export type WechatPollStatus = 'waiting' | 'confirmed' | 'expired' | 'step1_done';

export interface WechatPollResponse {
  status: WechatPollStatus;
  auth?: AuthResponse;
}

export interface WechatBindPollResponse {
  status: WechatPollStatus;
  user?: User;
  step?: number;
}

export interface OperationLogActionOption {
  value: string;
  label: string;
}

export interface UserOperationLog {
  id: number;
  user_id: number | null;
  username: string | null;
  role: string | null;
  action: string;
  action_label: string;
  success: boolean;
  message: string | null;
  detail: Record<string, unknown> | null;
  ip_address: string | null;
  user_agent: string | null;
  created_at: string;
}

export interface OperationLogListResponse {
  list: UserOperationLog[];
  total: number;
  page: number;
  pageSize: number;
}
