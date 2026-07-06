import sys
from loguru import logger

# 移除默认的控制台输出，重新配置
logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan> - <level>{message}</level>",
    level="INFO"
)

# 如果调试需要，可以改为 level="DEBUG"