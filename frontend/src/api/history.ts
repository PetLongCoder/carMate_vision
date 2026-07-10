import request from './request';
import type { ApiResponse, HistoryListResponse, HistoryTypeOption } from '../types';

export interface HistoryQuery {
  page?: number;
  pageSize?: number;
  type?: string;
  sourceType?: string;
  success?: boolean;
  keyword?: string;
  plateNo?: string;
  startDate?: string;
  endDate?: string;
}

export async function getHistoryTypes(): Promise<HistoryTypeOption[]> {
  const res = await request.get<ApiResponse<HistoryTypeOption[]>>('/history/types');
  return res.data.data;
}

export async function getUserHistory(params?: HistoryQuery): Promise<HistoryListResponse> {
  const res = await request.get<ApiResponse<HistoryListResponse>>('/history', { params });
  return res.data.data;
}
