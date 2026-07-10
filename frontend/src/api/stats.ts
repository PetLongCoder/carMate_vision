import request from './request';
import type { ApiResponse, DashboardStats } from '../types';

export async function getDashboardStats(): Promise<DashboardStats> {
  const res = await request.get<ApiResponse<DashboardStats>>('/stats/dashboard');
  return res.data.data;
}
