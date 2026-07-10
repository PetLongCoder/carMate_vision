import request from './request';
import type { ApiResponse } from '../types';

export interface PoliceGestureLogItem {
  id: number;
  recognitionType: string;
  gesture: string;
  confidence?: number;
  success: boolean;
  filename?: string | null;
  createdAt?: string | null;
}

export interface PoliceGestureLogListResponse {
  list: PoliceGestureLogItem[];
  total: number;
  page: number;
  pageSize: number;
}

export async function getPoliceGestureLogs(params?: {
  page?: number;
  pageSize?: number;
}): Promise<PoliceGestureLogListResponse> {
  const res = await request.get<ApiResponse<PoliceGestureLogListResponse>>('/police-gesture/logs', {
    params,
  });
  return res.data.data;
}
