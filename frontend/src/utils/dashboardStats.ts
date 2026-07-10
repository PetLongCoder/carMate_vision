import type { DashboardStats, GestureBreakdown, TodayGestureBreakdown } from '../types';

type LegacyBreakdown = GestureBreakdown & {
  policeGestureRecords?: number;
  driverGestureRecords?: number;
  policeGestureLogs?: number;
  policeGestureLogsSuccess?: number;
};

type LegacyTodayBreakdown = TodayGestureBreakdown & {
  policeGestureRecords?: number;
  driverGestureRecords?: number;
  policeGestureLogs?: number;
  policeGestureLogsSuccess?: number;
};

function normalizeBreakdown(raw?: LegacyBreakdown): GestureBreakdown {
  return {
    policeRecords: raw?.policeRecords ?? raw?.policeGestureRecords ?? 0,
    driverRecords: raw?.driverRecords ?? raw?.driverGestureRecords ?? 0,
    policeRecordsSuccess: raw?.policeRecordsSuccess ?? 0,
    driverRecordsSuccess: raw?.driverRecordsSuccess ?? 0,
    policeInferenceLogs: raw?.policeInferenceLogs ?? raw?.policeGestureLogs ?? 0,
    policeInferenceLogsSuccess: raw?.policeInferenceLogsSuccess ?? raw?.policeGestureLogsSuccess ?? 0,
  };
}

function normalizeTodayBreakdown(raw?: LegacyTodayBreakdown): TodayGestureBreakdown {
  return {
    policeRecords: raw?.policeRecords ?? raw?.policeGestureRecords ?? 0,
    driverRecords: raw?.driverRecords ?? raw?.driverGestureRecords ?? 0,
    policeRecordsSuccess: raw?.policeRecordsSuccess ?? 0,
    driverRecordsSuccess: raw?.driverRecordsSuccess ?? 0,
    policeInferenceLogs: raw?.policeInferenceLogs ?? raw?.policeGestureLogs ?? 0,
    policeInferenceLogsSuccess: raw?.policeInferenceLogsSuccess ?? 0,
  };
}

/** 兼容新旧 API 字段，避免前端显示 0 */
export function normalizeDashboardStats(raw: DashboardStats): DashboardStats {
  return {
    ...raw,
    gestureRecordTotal: raw.gestureRecordTotal ?? raw.totalGestures ?? 0,
    gestureRecordToday: raw.gestureRecordToday ?? raw.todayGestures ?? 0,
    gestureRecordSuccess: raw.gestureRecordSuccess ?? raw.successGestures ?? 0,
    gestureRecordTodaySuccess: raw.gestureRecordTodaySuccess ?? 0,
    gestureBreakdown: normalizeBreakdown(raw.gestureBreakdown as LegacyBreakdown),
    todayGestureBreakdown: normalizeTodayBreakdown(
      raw.todayGestureBreakdown as LegacyTodayBreakdown,
    ),
  };
}
