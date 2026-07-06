import { useEffect, useRef, useCallback } from 'react';
import { useAppStore } from '../store';
import type { Alert } from '../types';

export function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null);
  const addAlert = useAppStore((s) => s.addAlert);

  const connect = useCallback(() => {
    const wsUrl = import.meta.env.VITE_WS_URL || 'ws://localhost:8000/ws';
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
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

    ws.onerror = (err) => {
      console.error('[WebSocket] 连接错误:', err);
    };

    ws.onclose = () => {
      console.log('[WebSocket] 连接关闭, 3秒后重连');
      setTimeout(() => {
        connect();
      }, 3000);
    };

    wsRef.current = ws;
  }, [addAlert]);

  const disconnect = useCallback(() => {
    wsRef.current?.close();
    wsRef.current = null;
  }, []);

  useEffect(() => {
    connect();
    return () => disconnect();
  }, [connect, disconnect]);

  return { reconnect: connect, disconnect };
}
