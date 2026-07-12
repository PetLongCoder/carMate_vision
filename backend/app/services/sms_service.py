"""短信验证码 Mock 发送（开发阶段在后端终端查看验证码）。"""

from app.utils.logger import logger


def send_verification_sms(phone: str, code: str, scene: str) -> None:
    logger.info(f"[SMS Code] {phone} scene={scene} code={code}")
