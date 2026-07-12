"""
告警智能体 — LLM 摘要生成器
=========================
使用 LLM API 自动生成自然语言告警摘要。
LLM 不可用时自动降级为模板生成。
"""

import json
import time
from typing import Optional

from app.core.config import settings
from app.utils.logger import logger

from . import AlertLevel, AnomalyEvent, LEVEL_LABELS


# ── Prompt 模板 ──

SUMMARY_PROMPT = """你是一个车载视觉系统的告警分析助手。以下系统检测到异常事件，请生成结构化告警信息：

- 异常类型：{anomaly_type_label}
- 发生时间：{timestamp}
- 告警级别：{level_label}
- 来源模块：{source_label}
- 详细信息：{detail_json}

请以 JSON 格式返回（不要包含 markdown 代码块标记）：
{{
  "title": "简明告警标题（中文，20字以内）",
  "summary": "详细摘要（中文，100-200字），包含异常描述、可能原因",
  "impact_scope": "影响范围描述（中文，50字以内）",
  "suggested_actions": ["建议措施1", "建议措施2", "建议措施3"]
}}"""


def _format_timestamp(ts: float) -> str:
    """格式化时间戳为可读字符串"""
    import datetime
    return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def build_prompt(event: AnomalyEvent, level: AlertLevel) -> str:
    """构建 LLM 摘要生成提示词"""
    return SUMMARY_PROMPT.format(
        anomaly_type_label=event.anomaly_type_label,
        timestamp=_format_timestamp(event.timestamp),
        level_label=LEVEL_LABELS.get(level, level.value),
        source_label=event.source_label,
        detail_json=json.dumps(event.detail, ensure_ascii=False, indent=2),
    )


# ── 降级模板 ──

FALLBACK_TEMPLATES: dict[str, dict] = {
    "plate_recognition_failure": {
        "title": "车牌识别连续失败",
        "summary": "车牌识别模块检测到连续识别失败，可能由图像质量不佳、模型异常或光照条件变化引起。建议检查摄像头状态和模型运行情况。",
        "impact_scope": "车牌识别功能",
        "suggested_actions": ["检查摄像头画面是否正常", "确认识别模型是否正常加载", "检查环境光照条件"],
    },
    "plate_model_load_failure": {
        "title": "车牌识别模型加载失败",
        "summary": "车牌识别模型（HyperLPR3 / YOLOv8）加载失败，车牌识别功能暂时不可用。可能原因：模型文件缺失、CUDA 不可用或显存不足。",
        "impact_scope": "车牌识别功能完全不可用",
        "suggested_actions": ["检查模型文件是否完整", "确认 CUDA 环境是否正常", "尝试重启识别服务"],
    },
    "police_gesture_low_confidence": {
        "title": "交警手势识别置信度持续偏低",
        "summary": "交警手势识别模块输出置信度持续低于阈值，可能由于视频质量差、光照不足或手势动作不标准导致。",
        "impact_scope": "交警手势识别准确性下降",
        "suggested_actions": ["检查视频输入质量", "调整摄像头角度和光照", "确认手势动作是否在模型识别范围内"],
    },
    "police_gesture_model_failure": {
        "title": "交警手势模型加载失败",
        "summary": "交警手势识别模型（姿态估计 + LSTM）加载失败，手势识别功能暂时不可用。",
        "impact_scope": "交警手势识别功能完全不可用",
        "suggested_actions": ["检查模型文件是否完整", "检查 PyTorch 和 CUDA 环境", "尝试重启识别服务"],
    },
    "driver_gesture_low_confidence": {
        "title": "车主手势置信度持续偏低",
        "summary": "车主手势识别（MediaPipe + LSTM）输出置信度持续低于阈值，可能由于手部被遮挡、光照不足或手势不清晰导致。",
        "impact_scope": "车主手势控制准确性下降",
        "suggested_actions": ["确保手部在摄像头视野内且未被遮挡", "改善环境光照条件", "调整手势动作幅度"],
    },
    "driver_gesture_model_failure": {
        "title": "车主手势模型加载失败",
        "summary": "车主手势识别模型（MediaPipe Hands + LSTM）加载失败，手势控车功能暂时不可用。",
        "impact_scope": "车主手势控车功能完全不可用",
        "suggested_actions": ["检查 gesture_model.pth 文件是否完整", "确认 MediaPipe 是否正确安装", "尝试重启服务"],
    },
    "auth_unauthorized": {
        "title": "检测到未授权访问尝试",
        "summary": "系统检测到多次未授权访问尝试，可能存在恶意攻击或配置错误的客户端。",
        "impact_scope": "系统安全性",
        "suggested_actions": ["检查访问来源 IP", "确认认证配置是否正确", "考虑启用 IP 限制或增加登录验证"],
    },
    "auth_login_failure": {
        "title": "登录失败次数异常",
        "summary": "短时间内出现多次登录失败，可能是用户忘记密码或存在暴力破解尝试。",
        "impact_scope": "用户认证",
        "suggested_actions": ["检查是否为正常用户操作", "确认登录失败来源 IP", "必要时临时限制登录尝试频率"],
    },
    "llm_api_timeout": {
        "title": "LLM API 调用超时",
        "summary": "调用 LLM API 生成告警摘要时超时，系统已自动降级为模板生成。",
        "impact_scope": "告警摘要质量（已降级处理）",
        "suggested_actions": ["检查 LLM API 服务状态", "确认网络连接是否正常", "检查 API Key 是否有效"],
    },
    "llm_api_error": {
        "title": "LLM API 调用异常",
        "summary": "调用 LLM API 时发生错误，告警摘要已自动降级为模板生成。",
        "impact_scope": "告警摘要质量（已降级处理）",
        "suggested_actions": ["检查 LLM API 配置是否正确", "查看 API 服务商状态页面", "确认账户余额是否充足"],
    },
}


def generate_fallback(event: AnomalyEvent, level: AlertLevel) -> dict:
    """使用预定义模板生成告警摘要（LLM 降级方案）"""
    template = FALLBACK_TEMPLATES.get(event.anomaly_type)
    if template:
        return {
            "title": template["title"],
            "summary": template["summary"],
            "impact_scope": template["impact_scope"],
            "suggested_actions": template["suggested_actions"],
        }

    # 通用降级模板
    detail_str = json.dumps(event.detail, ensure_ascii=False)
    detail_brief = detail_str[:150] + ("..." if len(detail_str) > 150 else "")
    return {
        "title": event.title,
        "summary": f"系统检测到异常事件：{event.anomaly_type_label}。来源模块：{event.source_label}。"
                   f"详细信息：{detail_brief}",
        "impact_scope": event.source_label,
        "suggested_actions": ["查看系统日志获取详细信息", "检查相关服务运行状态"],
    }


# ── LLM API 调用 ──

async def call_llm_api(prompt: str) -> Optional[dict]:
    """调用 OpenAI 兼容 API 生成摘要（使用 httpx）"""
    if not settings.LLM_ENABLED or not settings.LLM_API_KEY:
        logger.debug("LLM 未启用或未配置 API Key，使用模板生成")
        return None

    try:
        import httpx

        url = f"{settings.LLM_API_BASE_URL.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {settings.LLM_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": settings.LLM_MODEL,
            "messages": [
                {"role": "system", "content": "你是一个专业的车载系统告警分析助手，请始终返回合法的 JSON 格式。"},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": settings.LLM_MAX_TOKENS,
            "temperature": 0.3,
        }

        async with httpx.AsyncClient(timeout=settings.LLM_TIMEOUT) as client:
            start = time.time()
            response = await client.post(url, json=payload, headers=headers)
            elapsed = time.time() - start

            if response.status_code != 200:
                logger.warning(f"LLM API 返回非 200: {response.status_code} {response.text[:200]}")
                return None

            data = response.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")

            logger.info(f"LLM API 调用成功, 耗时 {elapsed:.1f}s, 返回 {len(content)} 字符")

            # 尝试提取 JSON
            content = content.strip()
            if content.startswith("```"):
                # 去除 markdown 代码块标记
                lines = content.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                content = "\n".join(lines)

            return json.loads(content)

    except ImportError:
        logger.warning("httpx 未安装，无法调用 LLM API")
        return None
    except json.JSONDecodeError as e:
        logger.warning(f"LLM 返回内容 JSON 解析失败: {e}")
        return None
    except Exception as e:
        logger.warning(f"LLM API 调用异常: {e}")
        return None


async def generate_summary(event: AnomalyEvent, level: AlertLevel) -> dict:
    """
    生成告警摘要（LLM 优先，失败时降级）。

    返回: {"title", "summary", "impact_scope", "suggested_actions"}
    """
    if settings.LLM_ENABLED and settings.LLM_API_KEY:
        prompt = build_prompt(event, level)
        result = await call_llm_api(prompt)
        if result and all(k in result for k in ("title", "summary", "impact_scope", "suggested_actions")):
            logger.info(f"LLM 摘要生成成功: {result.get('title', '')}")
            return result
        logger.info("LLM 摘要生成失败或返回不完整，降级为模板生成")

    return generate_fallback(event, level)
