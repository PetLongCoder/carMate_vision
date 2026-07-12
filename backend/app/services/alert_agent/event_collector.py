"""
全局事件采集器
============
非侵入式异常事件采集器，在现有模块的失败点旁边添加事件采集调用。
提供单例 event_collector 供各模块使用。
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from app.utils.logger import logger

from . import AnomalyEvent, AlertLevel

if TYPE_CHECKING:
    from .alert_agent import AlertAgent


class EventCollector:
    """
    全局异常事件采集器（单例模式）。

    用法：
        from app.services.alert_agent.event_collector import event_collector

        # 在识别失败处添加一行调用
        event_collector.collect(AnomalyEvent(
            source="plate_recognition",
            anomaly_type="plate_recognition_failure",
            title="车牌识别连续失败",
            detail={"error": str(e), "frame": frame_num},
        ))
    """

    _instance: "EventCollector | None" = None

    def __init__(self):
        self._alert_agent: "AlertAgent | None" = None
        self._loop: asyncio.AbstractEventLoop | None = None

    def set_alert_agent(self, agent: "AlertAgent") -> None:
        """注入 AlertAgent 实例（在应用启动时调用）"""
        self._alert_agent = agent
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            self._loop = None

    def collect(self, event: AnomalyEvent) -> None:
        """
        采集异常事件并异步转交 AlertAgent 处理。
        不阻塞主流程 — 使用 asyncio.create_task 或 call_soon_threadsafe。
        """
        if self._alert_agent is None:
            logger.debug(f"AlertAgent 未初始化，跳过事件: {event.anomaly_type}")
            return

        logger.info(f"EventCollector 采集到事件: [{event.source}] {event.anomaly_type_label}")

        try:
            loop = self._loop or asyncio.get_running_loop()
            loop.create_task(self._alert_agent.process_event(event))
        except RuntimeError:
            # 没有运行中的事件循环，同步产生一个
            try:
                loop = asyncio.new_event_loop()
                loop.run_until_complete(self._alert_agent.process_event(event))
            except Exception as e:
                logger.error(f"事件处理失败: {e}")


# 全局单例
event_collector = EventCollector()
