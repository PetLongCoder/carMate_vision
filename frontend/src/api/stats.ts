import request from './request';
import type { ApiResponse, DashboardStats } from '../types';
import { normalizeDashboardStats } from '../utils/dashboardStats';

export async function getDashboardStats(): Promise<DashboardStats> {
  const res = await request.get<ApiResponse<DashboardStats>>('/stats/dashboard');
  return normalizeDashboardStats(res.data.data);
}