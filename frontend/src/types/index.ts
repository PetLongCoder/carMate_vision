// 车牌识别结果
export interface PlateResult {
  carId: number;
  plateNo: string;
  vehicleType: string;  // car / bus / truck / unknown
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

// 用户认证
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
export type VerifyMethod = 'password' | 'phone' | 'email';

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
