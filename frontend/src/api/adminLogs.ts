import request from './request';
import type { ApiResponse, OperationLogActionOption, OperationLogListResponse } from '../types';

export interface OperationLogQuery {
  page?: number;
  pageSize?: number;
  username?: string;
  action?: string;
  success?: boolean;
  startDate?: string;
  endDate?: string;
}

export async function getOperationLogActions(): Promise<OperationLogActionOption[]> {
  const res = await request.get<ApiResponse<OperationLogActionOption[]>>('/admin/operation-logs/actions');
  return res.data.data;
}

export async function getOperationLogs(params: OperationLogQuery): Promise<OperationLogListResponse> {
  const res = await request.get<ApiResponse<OperationLogListResponse>>('/admin/operation-logs', { params });
  return res.data.data;
}
