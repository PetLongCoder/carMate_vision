import { useEffect, useRef, useCallback } from 'react';
import { useAppStore } from '../store';
import type { Alert } from '../types';

const WS_ENABLED = import.meta.env.VITE_ENABLE_WS === 'true';
const MAX_RETRIES = 3;
const RETRY_DELAY_MS = 5000;

export function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null);
  const retryCountRef = useRef(0);
  const retryTimerRef = useRef<number | undefined>(undefined);
  const addAlert = useAppStore((s) => s.addAlert);

  const clearRetryTimer = () => {
    if (retryTimerRef.current) {
      window.clearTimeout(retryTimerRef.current);
      retryTimerRef.current = undefined;
    }
  };

  const disconnect = useCallback(() => {
    clearRetryTimer();
    if (wsRef.current) {
      wsRef.current.onclose = null;
      wsRef.current.close();
      wsRef.current = null;
    }
  }, []);

  const connect = useCallback(() => {
    if (!WS_ENABLED) return;

    clearRetryTimer();
    disconnect();

    const wsUrl = import.meta.env.VITE_WS_URL || 'ws://localhost:8000';
    const ws = new WebSocket(wsUrl.replace(/\/+$/, '') + '/ws');

    ws.onopen = () => {
      retryCountRef.current = 0;
      console.log('[WebSocket] 已连接');
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'alert') {
          addAlert(data.payload as Alert);
        }
      } catch {
        console.warn('[WebSocket] 消息解析失败:', event.data);
      }
    };

    ws.onerror = () => {
      if (retryCountRef.current === 0) {
        console.warn('[WebSocket] 连接失败，后端 WebSocket 可能未启动');
      }
    };

    ws.onclose = () => {
      wsRef.current = null;

      if (retryCountRef.current >= MAX_RETRIES) {
        console.warn('[WebSocket] 已达最大重连次数，停止重连');
        return;
      }

      retryCountRef.current += 1;
      retryTimerRef.current = window.setTimeout(() => {
        connect();
      }, RETRY_DELAY_MS);
    };

    wsRef.current = ws;
  }, [addAlert, disconnect]);

  useEffect(() => {
    if (!WS_ENABLED) return;

    connect();
    return () => disconnect();
  }, [connect, disconnect]);

  return { reconnect: connect, disconnect };
}
