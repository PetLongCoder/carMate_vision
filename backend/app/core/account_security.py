"""账号登录方式与安全校验。"""

from app.models.db_models import User

RESERVED_USERNAMES = {"admin"}


def list_login_methods(user: User) -> list[str]:
    methods: list[str] = []
    if _has_password_login(user):
        methods.append("password")
    if user.phone:
        methods.append("phone")
    if user.email:
        methods.append("email")
    if user.wechat_openid:
        methods.append("wechat")
    return methods


def _has_password_login(user: User) -> bool:
    # 纯微信自动注册、且未绑定手机/邮箱时，不视为可用密码登录
    if user.wechat_openid and not user.phone and not user.email and user.username.startswith("wx_"):
        return False
    return True


def ensure_can_remove_method(user: User, method: str) -> str | None:
    methods = list_login_methods(user)
    if method not in methods:
        return "当前账号未绑定该登录方式"
    if len(methods) <= 1:
        return "至少保留一种登录方式，无法解绑"
    return None


def can_delete_account(user: User) -> str | None:
    if user.username in RESERVED_USERNAMES:
        return "系统预置账号不可注销"
    if not list_login_methods(user):
        return "账号无可用的登录方式"
    return None
