"""
通知分发器
=========
多渠道通知分发：WebSocket 推送 + 飞书 Webhook。
"""

import json
import time
from typing import Optional

from app.core.config import settings
from app.utils.logger import logger

from . import AlertLevel, LEVEL_LABELS, FEISHU_LEVEL_COLORS
from .ws_alert_manager import ws_alert_manager


# ── 飞书消息卡片模板 ──

FEISHU_CARD_TEMPLATE = {
    "msg_type": "interactive",
    "card": {
        "header": {
            "title": {"tag": "plain_text", "content": ""},
            "template": "blue",
        },
        "elements": [],
    },
}


def _build_feishu_card(alert_dict: dict) -> dict:
    """根据告警数据构建飞书消息卡片"""
    level = alert_dict.get("level", "info")
    level_label = LEVEL_LABELS.get(AlertLevel(level), level)
    title = alert_dict.get("title", "未知告警")
    anomaly_type = alert_dict.get("anomaly_type_label", alert_dict.get("anomaly_type", ""))
    source = alert_dict.get("source_label", alert_dict.get("source", ""))
    created_at = alert_dict.get("created_at", "")
    summary = alert_dict.get("summary", "")
    impact_scope = alert_dict.get("impact_scope", "")
    suggested_actions = alert_dict.get("suggested_actions", [])

    color = FEISHU_LEVEL_COLORS.get(AlertLevel(level), "blue")

    # 构建卡片
    card = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": f"🚨 [{level_label}] {title}"},
                "template": color,
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": (
                            f"**异常类型**：{anomaly_type}\n"
                            f"**来源模块**：{source}\n"
                            f"**时间**：{created_at}\n"
                            f"**影响范围**：{impact_scope}"
                        ),
                    },
                },
                {"tag": "hr"},
                {
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": f"**摘要**：\n{summary}"},
                },
            ],
        },
    }

    # 添加建议操作
    if suggested_actions:
        action_text = "\n".join(f"- {action}" for action in suggested_actions)
        card["card"]["elements"].extend([
            {"tag": "hr"},
            {
                "tag": "div",
                "text": {"tag": "lark_md", "content": f"**建议处置**：\n{action_text}"},
            },
        ])

    return card


async def _send_feishu(alert_dict: dict) -> bool:
    """发送告警到飞书机器人"""
    if not settings.ALERT_FEISHU_ENABLED:
        logger.debug("飞书通知未启用")
        return False

    webhook_url = settings.ALERT_FEISHU_WEBHOOK_URL
    if not webhook_url:
        logger.warning("飞书 Webhook URL 未配置")
        return False

    try:
        import httpx

        card = _build_feishu_card(alert_dict)

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(webhook_url, json=card)
            if response.status_code == 200:
                logger.info(f"飞书通知发送成功: {alert_dict.get('title', '')}")
                return True
            else:
                logger.warning(f"飞书通知发送失败: HTTP {response.status_code} {response.text[:200]}")
                return False

    except ImportError:
        logger.warning("httpx 未安装，无法发送飞书通知")
        return False
    except Exception as e:
        logger.error(f"飞书通知发送异常: {e}")
        return False


# ── 通知分发器 ──

async def dispatch_notifications(alert_dict: dict, channels: Optional[list[str]] = None) -> list[str]:
    """
    向指定渠道分发告警通知。

    Args:
        alert_dict: 告警数据字典
        channels: 通知渠道列表，None 表示所有启用的渠道

    Returns:
        成功通知的渠道列表
    """
    if not settings.ALERT_NOTIFICATION_ENABLED:
        logger.debug("通知功能未启用")
        return []

    if channels is None:
        channels = []
        if settings.ALERT_WEBSOCKET_ENABLED:
            channels.append("websocket")
        if settings.ALERT_FEISHU_ENABLED:
            channels.append("feishu")

    notified = []

    # WebSocket 推送
    if "websocket" in channels:
        try:
            await ws_alert_manager.broadcast_alert(alert_dict)
            notified.append("websocket")
            logger.debug("WebSocket 告警推送完成")
        except Exception as e:
            logger.error(f"WebSocket 告警推送失败: {e}")

    # 飞书通知
    if "feishu" in channels:
        try:
            success = await _send_feishu(alert_dict)
            if success:
                notified.append("feishu")
        except Exception as e:
            logger.error(f"飞书通知异常: {e}")

    return notified
