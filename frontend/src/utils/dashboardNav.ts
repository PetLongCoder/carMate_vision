import dayjs from 'dayjs';

export interface RecognitionRecordQuery {
  type?: string;
  success?: boolean;
  startDate?: string;
  endDate?: string;
}

export function buildRecognitionRecordsPath(query: RecognitionRecordQuery = {}): string {
  const params = new URLSearchParams();
  if (query.type) params.set('type', query.type);
  if (query.success !== undefined) params.set('success', String(query.success));
  if (query.startDate) params.set('startDate', query.startDate);
  if (query.endDate) params.set('endDate', query.endDate);
  const qs = params.toString();
  return qs ? `/admin/recognition-records?${qs}` : '/admin/recognition-records';
}

export function todayRange(): { startDate: string; endDate: string } {
  return {
    startDate: dayjs().startOf('day').toISOString(),
    endDate: dayjs().endOf('day').toISOString(),
  };
}

export function buildAlertsPath(options?: { acknowledged?: boolean; level?: string }): string {
  const params = new URLSearchParams();
  if (options?.acknowledged === false) params.set('acknowledged', 'false');
  if (options?.level) params.set('level', options.level);
  const qs = params.toString();
  return qs ? `/alerts?${qs}` : '/alerts';
}

export type GestureStatsMode = 'total' | 'today' | 'success';
export type GestureStatsTab = 'police' | 'driver' | 'logs';

export function buildGestureStatsPath(
  mode: GestureStatsMode = 'total',
  tab?: GestureStatsTab,
): string {
  const params = new URLSearchParams({ mode });
  if (tab) params.set('tab', tab);
  return `/dashboard/gestures?${params.toString()}`;
}
