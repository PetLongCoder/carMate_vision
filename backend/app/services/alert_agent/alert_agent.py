"""
告警智能体 — 核心服务
===================
AlertAgent 是系统的自主告警决策引擎，负责：
1. 接收异常事件
2. 决策告警级别（提示/警告/严重）
3. 通过 LLM API 自动生成自然语言告警摘要
4. 写入告警记录到数据库
5. 触发多渠道通知分发
"""

from __future__ import annotations

import json
import time
from collections import deque
from datetime import datetime, timezone, date
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.db_models import AlertRecord
from app.utils.logger import logger

from . import AlertLevel, AlertDecision, AnomalyEvent, LEVEL_LABELS
from .llm_summary import generate_summary
from .notification_dispatcher import dispatch_notifications


class AlertAgent:
    """
    告警智能体核心（单例模式）。

    用法：
        agent = AlertAgent()
        await agent.process_event(anomaly_event)
    """

    def __init__(self):
        # 防抖：记录最近告警 (anomaly_type, timestamp)
        self._recent_alerts: deque[tuple[str, float]] = deque(maxlen=200)
        # 滑动窗口计数器：{anomaly_type: [timestamps]}
        self._failure_counters: dict[str, list[float]] = {}
        # 冷却窗口（秒）
        self._cooldown_seconds: int = 60

    def set_cooldown(self, seconds: int) -> None:
        """设置同类告警最小间隔（秒）"""
        self._cooldown_seconds = seconds

    async def process_event(self, event: AnomalyEvent) -> Optional[int]:
        """
        主入口：处理异常事件。

        Returns:
            新创建的 AlertRecord.id，如果被防抖过滤则返回 None
        """
        # 1. 决策告警级别
        decision = self._decide_level(event)
        if not decision.should_alert:
            logger.debug(f"事件不触发告警: [{event.anomaly_type}] {decision.reason}")
            return None

        # 2. 检查防抖
        if self._check_cooldown(event):
            logger.debug(f"同类告警在冷却期内，跳过: {event.anomaly_type}")
            return None

        # 3. LLM 摘要生成
        try:
            summary_data = await generate_summary(event, decision.level)
        except Exception as e:
            logger.warning(f"摘要生成异常，使用降级模板: {e}")
            from .llm_summary import generate_fallback
            summary_data = generate_fallback(event, decision.level)

        # 4. 写入数据库
        alert_id = self._persist_alert(event, decision, summary_data)
        if alert_id is None:
            return None

        # 5. 记录防抖
        self._record_cooldown(event)

        # 6. 通知分发（不阻塞，fire-and-forget）
        try:
            alert_dict = self._build_alert_dict(alert_id, event, decision, summary_data)
            import asyncio
            asyncio.create_task(dispatch_notifications(alert_dict))
        except Exception as e:
            logger.error(f"通知分发失败: {e}")

        return alert_id

    def _decide_level(self, event: AnomalyEvent) -> AlertDecision:
        """
        基于规则决策告警级别。

        决策规则：
        - model_load_failure → CRITICAL（系统功能不可用）
        - 连续失败 → 从 INFO 升级到 WARNING 再到 CRITICAL
        - 单次一般错误 → INFO
        - 未授权访问 → WARNING
        """
        anomaly_type = event.anomaly_type

        # 严重级别：模型加载失败
        if "model_load_failure" in anomaly_type or "model_failure" in anomaly_type:
            return AlertDecision(level=AlertLevel.CRITICAL, reason="模型加载失败，功能不可用")

        # 严重级别：连续失败计数超过阈值
        counter = self._failure_counters.get(anomaly_type, [])
        now = time.time()
        recent = [t for t in counter if now - t < 300]  # 5 分钟窗口
        recent_count = len(recent)

        if "unauthorized" in anomaly_type:
            if recent_count >= 10:
                return AlertDecision(level=AlertLevel.CRITICAL, reason=f"短时间内 {recent_count} 次未授权访问")
            if recent_count >= 3:
                return AlertDecision(level=AlertLevel.WARNING, reason=f"5 分钟内 {recent_count} 次未授权访问")
            return AlertDecision(level=AlertLevel.INFO, reason="单次未授权访问记录")

        if "login_failure" in anomaly_type:
            if recent_count >= 10:
                return AlertDecision(level=AlertLevel.CRITICAL, reason=f"短时间内 {recent_count} 次登录失败")
            if recent_count >= 3:
                return AlertDecision(level=AlertLevel.WARNING, reason=f"5 分钟内 {recent_count} 次登录失败")
            return AlertDecision(level=AlertLevel.INFO, reason="单次登录失败")

        if "low_confidence" in anomaly_type:
            if recent_count >= 10:
                return AlertDecision(level=AlertLevel.WARNING, reason="置信度持续偏低，需关注")
            if recent_count >= 3:
                return AlertDecision(level=AlertLevel.INFO, reason="置信度偏低，记录观察")
            return AlertDecision(level=AlertLevel.INFO, reason="单次低置信度，记录观察")
            # should_alert 由 _check_cooldown 控制频率

        if "recognition_failure" in anomaly_type or "inference_error" in anomaly_type:
            if recent_count >= 10:
                return AlertDecision(level=AlertLevel.CRITICAL, reason=f"连续 {recent_count} 次识别失败")
            if recent_count >= 3:
                return AlertDecision(level=AlertLevel.WARNING, reason=f"连续 {recent_count} 次识别失败")
            return AlertDecision(level=AlertLevel.INFO, reason="单次识别失败")

        if "llm_api" in anomaly_type:
            if recent_count >= 3:
                return AlertDecision(level=AlertLevel.WARNING, reason=f"连续 {recent_count} 次 LLM API 异常")
            return AlertDecision(level=AlertLevel.INFO, reason="LLM API 调用异常")

        # 默认：使用事件的建议级别或 WARNING
        level = event.severity_hint or AlertLevel.WARNING
        return AlertDecision(level=level, reason="默认告警规则")

    def _check_cooldown(self, event: AnomalyEvent) -> bool:
        """检查同类事件是否在冷却期内"""
        anomaly_type = event.anomaly_type
        now = time.time()
        for a_type, ts in self._recent_alerts:
            if a_type == anomaly_type and (now - ts) < self._cooldown_seconds:
                return True
        return False

    def _record_cooldown(self, event: AnomalyEvent) -> None:
        """记录告警用于防抖和计数"""
        now = time.time()
        self._recent_alerts.append((event.anomaly_type, now))

        # 更新滑动窗口计数器
        if event.anomaly_type not in self._failure_counters:
            self._failure_counters[event.anomaly_type] = []
        self._failure_counters[event.anomaly_type].append(now)

        # 清理 5 分钟前的记录
        cutoff = now - 300
        self._failure_counters[event.anomaly_type] = [
            t for t in self._failure_counters[event.anomaly_type] if t > cutoff
        ]

    def _persist_alert(
        self, event: AnomalyEvent, decision: AlertDecision, summary_data: dict
    ) -> Optional[int]:
        """写入告警记录到数据库"""
        db: Session = SessionLocal()
        try:
            suggested_actions = summary_data.get("suggested_actions", [])
            if isinstance(suggested_actions, list):
                suggested_actions_json = json.dumps(suggested_actions, ensure_ascii=False)
            else:
                suggested_actions_json = str(suggested_actions)

            record = AlertRecord(
                level=decision.level.value,
                title=summary_data.get("title", event.title),
                summary=summary_data.get("summary", ""),
                source=event.source,
                anomaly_type=event.anomaly_type,
                impact_scope=summary_data.get("impact_scope", event.source_label),
                suggested_actions=suggested_actions_json,
                raw_event=json.dumps(event.detail, ensure_ascii=False),
                notified_channels=None,  # 将在通知分发后更新
                acknowledged=False,
            )
            db.add(record)
            db.commit()
            db.refresh(record)

            alert_id = record.id
            logger.info(f"告警记录已创建: id={alert_id}, level={decision.level.value}, "
                        f"type={event.anomaly_type}, title={record.title}")
            return alert_id

        except Exception as e:
            db.rollback()
            logger.error(f"告警记录写入失败: {e}")
            return None
        finally:
            db.close()

    def _build_alert_dict(
        self, alert_id: int, event: AnomalyEvent, decision: AlertDecision, summary_data: dict
    ) -> dict:
        """构建告警字典（用于通知推送）"""
        now = datetime.now(timezone.utc)
        suggested_actions = summary_data.get("suggested_actions", [])

        return {
            "id": alert_id,
            "level": decision.level.value,
            "level_label": LEVEL_LABELS.get(decision.level, decision.level.value),
            "title": summary_data.get("title", event.title),
            "summary": summary_data.get("summary", ""),
            "source": event.source,
            "source_label": event.source_label,
            "anomaly_type": event.anomaly_type,
            "anomaly_type_label": event.anomaly_type_label,
            "impact_scope": summary_data.get("impact_scope", ""),
            "suggested_actions": suggested_actions,
            "acknowledged": False,
            "created_at": now.strftime("%Y-%m-%d %H:%M:%S"),
            "createdAt": now.isoformat(),
        }

    def update_notified_channels(self, alert_id: int, channels: list[str]) -> None:
        """更新告警记录的通知渠道信息"""
        db: Session = SessionLocal()
        try:
            record = db.query(AlertRecord).filter(AlertRecord.id == alert_id).first()
            if record:
                record.notified_channels = ",".join(channels)
                db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"更新通知渠道失败: {e}")
        finally:
            db.close()

    # ── 统计查询 ──

    def get_stats(self, db: Session, days: int = 7) -> dict:
        """获取告警统计数据"""
        cutoff = datetime.now(timezone.utc)
        start_date = cutoff - __import__("datetime").timedelta(days=days)

        # 按级别统计
        total_by_level = {}
        for level in ("info", "warning", "critical"):
            total_by_level[level] = (
                db.query(func.count(AlertRecord.id))
                .filter(AlertRecord.level == level)
                .scalar() or 0
            )

        # 按异常类型统计
        type_rows = (
            db.query(AlertRecord.anomaly_type, func.count(AlertRecord.id))
            .filter(AlertRecord.anomaly_type.isnot(None))
            .group_by(AlertRecord.anomaly_type)
            .all()
        )
        by_type = {row[0]: row[1] for row in type_rows}

        # 每日趋势
        daily = (
            db.query(
                func.date(AlertRecord.created_at).label("day"),
                AlertRecord.level,
                func.count(AlertRecord.id),
            )
            .filter(AlertRecord.created_at >= start_date)
            .group_by("day", AlertRecord.level)
            .order_by("day")
            .all()
        )
        daily_trend: list[dict] = []
        day_map: dict[str, dict] = {}
        for day, level, count in daily:
            day_str = str(day)
            if day_str not in day_map:
                day_map[day_str] = {"date": day_str, "info": 0, "warning": 0, "critical": 0}
            day_map[day_str][level] = count
        daily_trend = sorted(day_map.values(), key=lambda x: x["date"])

        # 总数 / 未确认 / 今日
        total = sum(total_by_level.values())
        unack = (
            db.query(func.count(AlertRecord.id))
            .filter(AlertRecord.acknowledged.is_(False))
            .scalar() or 0
        )
        today_count = (
            db.query(func.count(AlertRecord.id))
            .filter(func.date(AlertRecord.created_at) == date.today())
            .scalar() or 0
        )

        # 平均确认时间（分钟）
        avg_ack = db.query(
            func.avg(
                func.timestampdiff(
                    __import__("sqlalchemy").text("MINUTE"),
                    AlertRecord.created_at,
                    AlertRecord.acknowledged_at,
                )
            )
        ).filter(
            AlertRecord.acknowledged.is_(True),
            AlertRecord.acknowledged_at.isnot(None),
        ).scalar()
        avg_response = round(float(avg_ack), 1) if avg_ack else 0

        return {
            "total": total,
            "unacknowledged": unack,
            "todayCount": today_count,
            "totalByLevel": total_by_level,
            "byAnomalyType": by_type,
            "dailyTrend": daily_trend,
            "avgResponseMinutes": avg_response,
        }


# 全局单例
alert_agent = AlertAgent()
