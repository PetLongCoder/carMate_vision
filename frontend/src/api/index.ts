import request from './request';
import type {
  ApiResponse,
  PlateResult,
  PoliceGestureResult,
  DriverGestureResult,
  Alert,
  HistoryRecord,
  DashboardStats,
  TrackSessionResponse,
  StreamStartResponse,
  TrackingSessionInfo,
} from '../types';

// ═══════════════════════════════════════════════════════════
//  车牌识别
// ═══════════════════════════════════════════════════════════

export function uploadPlateImage(file: File) {
  const formData = new FormData();
  formData.append('file', file);
  return request.post<ApiResponse<PlateResult[]>>('/plate/recognize', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
}

// ═══════════════════════════════════════════════════════════
//  实时追踪
// ═══════════════════════════════════════════════════════════

/** 上传视频并创建追踪会话 */
export function uploadTrackVideo(file: File) {
  const formData = new FormData();
  formData.append('file', file);
  return request.post<ApiResponse<TrackSessionResponse>>('/plate/track', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 30000,
  });
}

/** 启动流媒体追踪会话 */
export function startStreamTracking(url: string, name?: string) {
  const formData = new FormData();
  formData.append('url', url);
  if (name) formData.append('name', name);
  return request.post<ApiResponse<StreamStartResponse>>('/plate/stream/start', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 20000, // 20s — RTSP 连接可能需要时间
  });
}

/** 停止追踪会话 */
export function stopStreamTracking(sessionId: string) {
  return request.post<ApiResponse<null>>(`/plate/stream/stop/${sessionId}`);
}

/** 列出所有追踪会话 */
export function listTrackingSessions() {
  return request.get<ApiResponse<TrackingSessionInfo[]>>('/plate/stream/sessions');
}

/** 查询会话详情 */
export function getTrackingSession(sessionId: string) {
  return request.get<ApiResponse<TrackingSessionInfo>>(`/plate/stream/sessions/${sessionId}`);
}

// ═══════════════════════════════════════════════════════════
//  交警手势识别
// ═══════════════════════════════════════════════════════════

export function uploadPoliceGestureVideo(file: File) {
  const formData = new FormData();
  formData.append('file', file);
  return request.post<ApiResponse<PoliceGestureResult>>('/police-gesture/recognize', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 600000,
  });
}

// ═══════════════════════════════════════════════════════════
//  交警手势识别 - SSE 流式识别
// ═══════════════════════════════════════════════════════════

export type PoliceGestureStreamEvent =
  | { event: 'meta'; data: Record<string, unknown> }
  | { event: 'frame'; data: Record<string, unknown> }
  | { event: 'done'; data: Record<string, unknown> }
  | { event: 'error'; data: { message?: string } };

export async function streamPoliceGestureVideo(
  file: File,
  onEvent: (event: PoliceGestureStreamEvent) => void,
  signal?: AbortSignal,
) {
  const formData = new FormData();
  formData.append('file', file);

  const baseURL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api';
  const response = await fetch(`${baseURL}/police-gesture/recognize/stream`, {
    method: 'POST',
    body: formData,
    signal,
  });

  if (!response.ok || !response.body) {
    throw new Error(`流式识别请求失败: ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';

  const dispatchChunk = (chunk: string) => {
    const eventName = chunk.match(/^event:\s*(.+)$/m)?.[1]?.trim();
    const dataText = chunk.match(/^data:\s*(.+)$/m)?.[1]?.trim();
    if (!eventName || !dataText) return;

    onEvent({
      event: eventName as PoliceGestureStreamEvent['event'],
      data: JSON.parse(dataText),
    } as PoliceGestureStreamEvent);
  };

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split('\n\n');
    buffer = chunks.pop() || '';
    chunks.forEach(dispatchChunk);
  }

  if (buffer.trim()) {
    dispatchChunk(buffer);
  }
}

export async function createPoliceGesturePreview(file: File, signal?: AbortSignal) {
  const formData = new FormData();
  formData.append('file', file);

  const baseURL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api';
  const response = await fetch(`${baseURL}/police-gesture/preview`, {
    method: 'POST',
    body: formData,
    signal,
  });

  if (!response.ok) {
    const text = await response.text().catch(() => '');
    throw new Error(text || `预览视频生成失败: ${response.status}`);
  }

  return response.blob();
}

export function resetPoliceGestureStream(streamId = 'default') {
  const formData = new FormData();
  formData.append('stream_id', streamId);
  return request.post<ApiResponse<{ streamId: string }>>('/police-gesture/stream/reset', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
}

export function recognizePoliceGestureFrame(file: Blob, streamId = 'default') {
  const formData = new FormData();
  formData.append('file', file, 'frame.jpg');
  formData.append('stream_id', streamId);
  return request.post<ApiResponse<PoliceGestureResult>>('/police-gesture/stream/frame', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120000,
  });
}

// ═══════════════════════════════════════════════════════════
//  车主手势识别
// ═══════════════════════════════════════════════════════════
export function uploadDriverGestureImage(file: File) {
  const formData = new FormData();
  formData.append('file', file);
  return request.post<ApiResponse<DriverGestureResult>>('/driver-gesture/recognize', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
}

// ═══════════════════════════════════════════════════════════
//  告警
// ═══════════════════════════════════════════════════════════

export function getAlerts(params?: {
  page?: number;
  pageSize?: number;
  level?: string;
  acknowledged?: boolean;
}) {
  return request.get<ApiResponse<{ list: Alert[]; total: number }>>('/alerts', { params });
}

export function acknowledgeAlert(id: number) {
  return request.put<ApiResponse<null>>(`/alerts/${id}/acknowledge`);
}

export function batchAcknowledgeAlerts(ids: number[]) {
  const params = new URLSearchParams();
  ids.forEach((id) => params.append('ids', String(id)));
  return request.put<ApiResponse<{ updated: number }>>(`/alerts/batch-acknowledge?${params.toString()}`);
}

export function getAlertStats(params?: { days?: number }) {
  return request.get<ApiResponse<import('../types').AlertStats>>('/alerts/stats', { params });
}

export function getAlertTimeline(params?: {
  page?: number;
  pageSize?: number;
  startDate?: string;
  endDate?: string;
  level?: string;
  anomalyType?: string;
}) {
  return request.get<ApiResponse<{ list: Alert[]; total: number }>>('/alerts/timeline', { params });
}

export function getAlertDetail(alertId: number) {
  return request.get<ApiResponse<Alert & { rawEvent?: object; relatedAlerts?: Alert[] }>>(`/alerts/${alertId}/detail`);
}

export function getAlertAnalysis(params?: { days?: number }) {
  return request.get<ApiResponse<import('../types').AlertAnalysis>>('/alerts/analysis', { params });
}

export function getAnomalyTypes() {
  return request.get<ApiResponse<import('../types').AnomalyTypeOption[]>>('/alerts/anomaly-types');
}

export function triggerTestAlert(anomalyType?: string, level?: string) {
  return request.post<ApiResponse<{ alertId: number | null; message: string }>>('/alerts/test', null, {
    params: { type: anomalyType, level },
  });
}

// ═══════════════════════════════════════════════════════════
//  历史记录
// ═══════════════════════════════════════════════════════════

export function getHistory(params?: { page?: number; pageSize?: number; type?: string }) {
  return request.get<ApiResponse<{ list: HistoryRecord[]; total: number }>>('/history', { params });
}

// ═══════════════════════════════════════════════════════════
//  统计数据
// ═══════════════════════════════════════════════════════════

export { getDashboardStats } from './stats';
