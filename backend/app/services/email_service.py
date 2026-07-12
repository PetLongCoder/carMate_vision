"""邮箱验证码发送：mock（终端日志）/ smtp（真实邮件）。"""

from __future__ import annotations

import smtplib
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formataddr, parseaddr

from app.core.config import settings
from app.utils.logger import logger


class EmailSendError(Exception):
    """邮件发送失败。"""


_SCENE_LABELS = {
    "register": "注册",
    "login": "登录",
    "bind": "绑定邮箱",
    "rebind_new": "换绑邮箱",
    "unbind": "解绑邮箱",
    "rebind_old": "换绑验证",
    "delete": "注销账号",
    "change_password": "修改密码",
}


def _scene_label(scene: str) -> str:
    return _SCENE_LABELS.get(scene, "验证")


def _mask_email(email: str) -> str:
    local, sep, domain = email.partition("@")
    if not sep or len(local) <= 2:
        return email
    return f"{local[0]}***{local[-1]}@{domain}"


def send_verification_email(to_email: str, code: str, scene: str) -> str:
    """发送验证码邮件，返回给用户看的提示文案。"""
    provider = settings.EMAIL_PROVIDER.lower()
    if provider == "smtp":
        _send_via_smtp(to_email, code, scene)
        logger.info(f"[Email Sent] {_mask_email(to_email)} scene={scene} provider=smtp")
        return "验证码已发送，请查收邮箱（含垃圾箱）"

    logger.info(f"[Email Code] {to_email} scene={scene} code={code} (mock)")
    return "验证码已发送（请在后端终端查看）"


def _smtp_from_address() -> str:
    """SMTP 发件邮箱；SMTP_FROM 可填纯邮箱或 `Name <email>`。"""
    raw = settings.SMTP_FROM or settings.SMTP_USER
    _, addr = parseaddr(raw)
    return addr or settings.SMTP_USER


def _send_via_smtp(to_email: str, code: str, scene: str) -> None:
    missing = [
        name
        for name, val in [
            ("SMTP_HOST", settings.SMTP_HOST),
            ("SMTP_USER", settings.SMTP_USER),
            ("SMTP_PASSWORD", settings.SMTP_PASSWORD),
        ]
        if not val
    ]
    if missing:
        raise EmailSendError(f"SMTP 未配置完整，缺少: {', '.join(missing)}")

    minutes = max(settings.CODE_TTL_SECONDS // 60, 1)
    scene_text = _scene_label(scene)
    subject = f"CarMate 验证码 - {scene_text}"
    body = (
        f"您正在进行 CarMate {scene_text}操作。\n\n"
        f"验证码：{code}\n"
        f"有效期：{minutes} 分钟\n\n"
        f"如非本人操作，请忽略此邮件。"
    )

    from_addr = _smtp_from_address()
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = formataddr(("CarMate", from_addr))
    msg["To"] = to_email

    try:
        if settings.SMTP_USE_SSL:
            with smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as server:
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                server.sendmail(from_addr, [to_email], msg.as_string())
        else:
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as server:
                server.starttls()
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                server.sendmail(from_addr, [to_email], msg.as_string())
    except smtplib.SMTPException as exc:
        raise EmailSendError(f"邮件发送失败: {exc}") from exc
