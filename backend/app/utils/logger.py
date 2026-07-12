import sys
import os
from loguru import logger

# 移除默认的控制台输出，重新配置
logger.remove()

# 默认日志级别
_default_level = os.getenv("CARMATE_LOG_LEVEL", "INFO").upper()

# 交警手势模块日志级别 (可独立控制, 未设置时沿用默认级别)
_pg_level = os.getenv("CARMATE_LOG_LEVEL_POLICE_GESTURE", _default_level).upper()

# 校验级别名称
_valid_levels = {"TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL"}
if _default_level not in _valid_levels:
    _default_level = "INFO"
if _pg_level not in _valid_levels:
    _pg_level = _default_level


def _level_to_int(level: str) -> int:
    """将级别名称转为 Loguru 内部数值 (数值越大越严重)"""
    import logging as _logging
    std_level = getattr(_logging, level, None)
    if std_level is not None:
        return std_level
    # fallback 映射
    return {
        "TRACE": 5,
        "DEBUG": 10,
        "INFO": 20,
        "SUCCESS": 25,
        "WARNING": 30,
        "ERROR": 40,
        "CRITICAL": 50,
    }.get(level, 20)


def _police_gesture_filter(record: dict) -> bool:
    """过滤交警手势相关模块的日志级别。

    由环境变量 CARMATE_LOG_LEVEL_POLICE_GESTURE 控制,
    未设置时沿用 CARMATE_LOG_LEVEL (默认 INFO)。
    """
    name = record.get("name", "")
    if "police_gesture" in name:
        record_level_no = record["level"].no
        min_level_no = _level_to_int(_pg_level)
        return record_level_no >= min_level_no
    return True


logger.add(
    sys.stdout,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan> - <level>{message}</level>",
    level=_default_level,
    filter=_police_gesture_filter,
)

# 如果调试需要，可以设置环境变量 CARMATE_LOG_LEVEL=DEBUG
# 如果仅调试交警手势模块，设置 CARMATE_LOG_LEVEL_POLICE_GESTURE=DEBUG
