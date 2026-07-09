"""用户操作日志服务。"""

import json
from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from app.models.db_models import User, UserOperationLog

ACTION_LABELS: dict[str, str] = {
    "login": "账号密码登录",
    "login_phone": "手机验证码登录",
    "login_email": "邮箱验证码登录",
    "login_wechat": "微信扫码登录",
    "login_failed": "登录失败",
    "register": "用户注册",
    "profile_update": "更新资料",
    "bind_phone": "绑定手机号",
    "unbind_phone": "解绑手机号",
    "rebind_phone": "换绑手机号",
    "bind_email": "绑定邮箱",
    "unbind_email": "解绑邮箱",
    "rebind_email": "换绑邮箱",
    "bind_wechat": "绑定微信",
    "unbind_wechat": "解绑微信",
    "rebind_wechat": "换绑微信",
    "change_password": "修改密码",
    "delete_account": "注销账号",
    "view_operation_logs": "查看操作日志",
}


def get_client_ip(request: Request | None) -> str | None:
    if not request:
        return None
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


def get_user_agent(request: Request | None) -> str | None:
    if not request:
        return None
    ua = request.headers.get("user-agent")
    if not ua:
        return None
    return ua[:255]


def log_operation(
    db: Session,
    *,
    action: str,
    success: bool = True,
    user: User | None = None,
    username: str | None = None,
    user_id: int | None = None,
    role: str | None = None,
    message: str | None = None,
    detail: dict[str, Any] | None = None,
    request: Request | None = None,
) -> None:
    resolved_username = username or (user.username if user else None)
    resolved_user_id = user_id if user_id is not None else (user.id if user else None)
    resolved_role = role or (user.role if user else None)

    record = UserOperationLog(
        user_id=resolved_user_id,
        username=resolved_username,
        role=resolved_role,
        action=action,
        success=success,
        message=message,
        detail=json.dumps(detail, ensure_ascii=False) if detail else None,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
    )
    db.add(record)
    db.commit()


def operation_log_to_dict(record: UserOperationLog) -> dict[str, Any]:
    detail: dict[str, Any] | None = None
    if record.detail:
        try:
            detail = json.loads(record.detail)
        except json.JSONDecodeError:
            detail = {"raw": record.detail}

    return {
        "id": record.id,
        "user_id": record.user_id,
        "username": record.username,
        "role": record.role,
        "action": record.action,
        "action_label": ACTION_LABELS.get(record.action, record.action),
        "success": record.success,
        "message": record.message,
        "detail": detail,
        "ip_address": record.ip_address,
        "user_agent": record.user_agent,
        "created_at": record.created_at.isoformat() if record.created_at else None,
    }
