"""
WebSocket 告警连接管理器
======================
管理所有订阅告警推送的 WebSocket 连接，
支持向所有连接的客户端广播告警消息。
"""

import asyncio
from typing import Any

from fastapi import WebSocket

from app.utils.logger import logger


class WebSocketAlertManager:
    """管理告警推送的 WebSocket 连接池"""

    def __init__(self):
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        """注册新的 WebSocket 连接"""
        async with self._lock:
            self._connections.add(ws)
            logger.info(f"WebSocket 告警客户端已连接, 当前连接数: {len(self._connections)}")

    async def disconnect(self, ws: WebSocket) -> None:
        """移除 WebSocket 连接"""
        async with self._lock:
            self._connections.discard(ws)
            logger.info(f"WebSocket 告警客户端断开, 当前连接数: {len(self._connections)}")

    async def broadcast_alert(self, alert_data: dict) -> None:
        """
        向所有连接的客户端广播告警消息。

        Args:
            alert_data: 告警数据字典（会包装为 {"type": "alert", "payload": ...}）
        """
        message = {"type": "alert", "payload": alert_data}
        disconnected: list[WebSocket] = []

        async with self._lock:
            connections = list(self._connections)

        for ws in connections:
            try:
                await ws.send_json(message)
            except Exception:
                disconnected.append(ws)

        if disconnected:
            async with self._lock:
                for ws in disconnected:
                    self._connections.discard(ws)
            logger.debug(f"清理 {len(disconnected)} 个断开的 WebSocket 连接")

    @property
    def active_count(self) -> int:
        """活跃连接数"""
        return len(self._connections)

    async def broadcast_json(self, data: dict[str, Any]) -> None:
        """向所有连接广播任意 JSON 数据"""
        disconnected: list[WebSocket] = []

        async with self._lock:
            connections = list(self._connections)

        for ws in connections:
            try:
                await ws.send_json(data)
            except Exception:
                disconnected.append(ws)

        if disconnected:
            async with self._lock:
                for ws in disconnected:
                    self._connections.discard(ws)


# 全局单例
ws_alert_manager = WebSocketAlertManager()
