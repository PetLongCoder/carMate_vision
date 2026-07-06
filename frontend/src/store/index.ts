import { create } from 'zustand';
import type { Alert, DashboardStats } from '../types';

interface AppState {
  // 侧边栏
  sidebarCollapsed: boolean;
  toggleSidebar: () => void;

  // 告警
  alerts: Alert[];
  unreadCount: number;
  setAlerts: (alerts: Alert[]) => void;
  addAlert: (alert: Alert) => void;
  markAlertRead: (id: number) => void;
  clearAlerts: () => void;

  // 统计
  stats: DashboardStats | null;
  setStats: (stats: DashboardStats) => void;

  // 中控面板
  volume: number;
  temperature: number;
  setVolume: (v: number) => void;
  setTemperature: (t: number) => void;
}

export const useAppStore = create<AppState>((set) => ({
  sidebarCollapsed: false,
  toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),

  alerts: [],
  unreadCount: 0,
  setAlerts: (alerts) =>
    set({ alerts, unreadCount: alerts.filter((a) => !a.acknowledged).length }),
  addAlert: (alert) =>
    set((s) => ({
      alerts: [alert, ...s.alerts].slice(0, 100),
      unreadCount: s.unreadCount + (alert.acknowledged ? 0 : 1),
    })),
  markAlertRead: (id) =>
    set((s) => {
      const alerts = s.alerts.map((a) => (a.id === id ? { ...a, acknowledged: true } : a));
      return { alerts, unreadCount: alerts.filter((a) => !a.acknowledged).length };
    }),
  clearAlerts: () => set({ alerts: [], unreadCount: 0 }),

  stats: null,
  setStats: (stats) => set({ stats }),

  volume: 50,
  temperature: 24,
  setVolume: (volume) => set({ volume: Math.max(0, Math.min(100, volume)) }),
  setTemperature: (temperature) => set({ temperature: Math.max(16, Math.min(32, temperature)) }),
}));
