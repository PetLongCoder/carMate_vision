import request from './request';
import type {
  ApiResponse,
  AdminRecognitionListResponse,
  HistoryTypeOption,
} from '../types';

export interface AdminRecognitionQuery {
  page?: number;
  pageSize?: number;
  type?: string;
  sourceType?: string;
  success?: boolean;
  keyword?: string;
  username?: string;
  startDate?: string;
  endDate?: string;
}

export async function getAdminRecognitionTypes(): Promise<HistoryTypeOption[]> {
  const res = await request.get<ApiResponse<HistoryTypeOption[]>>('/admin/recognition-records/types');
  return res.data.data;
}

export async function getAdminRecognitionRecords(
  params: AdminRecognitionQuery,
): Promise<AdminRecognitionListResponse> {
  const res = await request.get<ApiResponse<AdminRecognitionListResponse>>(
    '/admin/recognition-records',
    { params },
  );
  return res.data.data;
}
