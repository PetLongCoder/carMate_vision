import request from './request';
import type {
  ApiResponse,
  PlateResult,
  PoliceGestureResult,
  DriverGestureResult,
  Alert,
  HistoryRecord,
  DashboardStats,
} from '../types';

// ---- 车牌识别 ----
export function uploadPlateImage(file: File) {
  const formData = new FormData();
  formData.append('file', file);
  return request.post<ApiResponse<PlateResult[]>>('/plate/recognize', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
}

// ---- 交警手势识别 ----
export function uploadPoliceGestureVideo(file: File) {
  const formData = new FormData();
  formData.append('file', file);
  return request.post<ApiResponse<PoliceGestureResult>>('/police-gesture/recognize', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 600000,
  });
}

// ---- 车主手势识别 ----
export function uploadDriverGestureImage(file: File) {
  const formData = new FormData();
  formData.append('file', file);
  return request.post<ApiResponse<DriverGestureResult>>('/driver-gesture/recognize', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
}

// ---- 告警 ----
export function getAlerts(params?: { page?: number; pageSize?: number; level?: string }) {
  return request.get<ApiResponse<{ list: Alert[]; total: number }>>('/alerts', { params });
}

export function acknowledgeAlert(id: number) {
  return request.put<ApiResponse<null>>(`/alerts/${id}/acknowledge`);
}

// ---- 历史记录 ----
export function getHistory(params?: { page?: number; pageSize?: number; type?: string }) {
  return request.get<ApiResponse<{ list: HistoryRecord[]; total: number }>>('/history', { params });
}

// ---- 统计数据 ----
export function getDashboardStats() {
  return request.get<ApiResponse<DashboardStats>>('/stats/dashboard');
}
