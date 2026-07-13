import random
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.account_security import ensure_can_remove_method, list_login_methods, can_delete_account
from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_access_token, decode_access_token, hash_password, verify_password
from app.models.auth_schemas import (
    AuthResponse,
    BindEmailRequest,
    BindPhoneRequest,
    ChangePasswordRequest,
    DeleteAccountRequest,
    EmailLoginRequest,
    LoginRequest,
    PhoneLoginRequest,
    RebindEmailRequest,
    RebindPhoneRequest,
    RegisterRequest,
    SecureEmailCodeRequest,
    SecureSmsCodeRequest,
    SendEmailCodeRequest,
    SendSmsCodeRequest,
    UnbindCodeRequest,
    UpdateProfileRequest,
    UserOut,
    VerifySmsCodeRequest,
)
from app.models.db_models import User, VerificationCode
from app.services.operation_log_service import log_operation
from app.services.email_service import EmailSendError, send_verification_email
from app.services.sms_service import send_verification_sms
from app.services.alert_agent.event_collector import event_collector
from app.services.alert_agent import AnomalyEvent, AlertLevel
from app.services.user_privacy_service import (
    assign_email,
    assign_phone,
    find_user_by_email,
    find_user_by_phone,
    get_email_plain,
    get_phone_plain,
    masked_email,
    masked_phone,
)
from app.utils.logger import logger

router = APIRouter(prefix="/auth", tags=["用户认证"])

RESERVED_USERNAMES = {"admin"}
EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


def ok(data: Any = None, message: str = "success") -> dict:
    return {"code": 0, "message": message, "data": data}


def fail(message: str, code: int = 400, auth_error_code: str | None = None) -> dict:
    body: dict[str, Any] = {"code": code, "message": message, "data": None}
    if auth_error_code:
        body["authErrorCode"] = auth_error_code
    return body


def user_to_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        username=user.username,
        role=user.role,
        phone=masked_phone(user),
        email=masked_email(user),
        nickname=user.nickname,
        avatar_url=user.avatar_url,
        has_wechat=bool(user.wechat_openid),
        login_methods=list_login_methods(user),
    )


def build_auth_response(user: User) -> AuthResponse:
    token = create_access_token(str(user.id), {"role": user.role, "username": user.username})
    return AuthResponse(token=token, user=user_to_out(user))


def generate_code() -> str:
    return f"{random.randint(100000, 999999)}"


def dispatch_sms_code(db: Session, phone: str, scene: str) -> None:
    """生成、入库并在终端输出短信验证码（mock）。"""
    code = generate_code()
    save_code(db, f"phone:{phone}", scene, code)
    send_verification_sms(phone, code, scene)


def dispatch_email_code(db: Session, email: str, scene: str) -> tuple[str | None, dict | None]:
    """生成、入库并发送邮箱验证码。成功返回 (message, None)，失败返回 (None, fail_response)。"""
    code = generate_code()
    save_code(db, f"email:{email}", scene, code)
    try:
        message = send_verification_email(email, code, scene)
    except EmailSendError as exc:
        return None, fail(str(exc))
    return message, None


def save_code(db: Session, target: str, scene: str, code: str) -> None:
    db.query(VerificationCode).filter(VerificationCode.target == target).delete()
    db.add(
        VerificationCode(
            target=target,
            code=code,
            scene=scene,
            expires_at=datetime.now(timezone.utc).replace(tzinfo=None)
            + timedelta(seconds=settings.CODE_TTL_SECONDS),
        )
    )
    db.commit()


def check_code(db: Session, target: str, code: str) -> str | None:
    record = (
        db.query(VerificationCode)
        .filter(VerificationCode.target == target)
        .order_by(VerificationCode.id.desc())
        .first()
    )
    if not record:
        return "请先获取验证码"
    if record.expires_at < datetime.now(timezone.utc).replace(tzinfo=None):
        return "验证码已过期，请重新获取"
    if record.code != code.strip():
        return "验证码错误"
    return None


def verify_code(db: Session, target: str, code: str) -> str | None:
    record = (
        db.query(VerificationCode)
        .filter(VerificationCode.target == target)
        .order_by(VerificationCode.id.desc())
        .first()
    )
    error = check_code(db, target, code)
    if error:
        return error
    if record:
        db.delete(record)
        db.commit()
    return None


def get_current_user(
    authorization: Annotated[str | None, Header()] = None,
    db: Session = Depends(get_db),
) -> User | None:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization.removeprefix("Bearer ").strip()
    payload = decode_access_token(token)
    if not payload:
        return None
    user_id = payload.get("sub")
    if not user_id:
        return None
    return db.query(User).filter(User.id == int(user_id)).first()


def require_current_user(user: User | None = Depends(get_current_user)) -> User:
    if not user:
        raise HTTPException(status_code=401, detail="未登录或登录已过期")
    return user


def require_admin(user: User = Depends(require_current_user)) -> User:
    if user.role != "admin":
        event_collector.collect(AnomalyEvent(
            source="auth",
            anomaly_type="auth_unauthorized",
            title="未授权访问：非管理员尝试访问管理功能",
            detail={"username": user.username, "role": user.role},
            severity_hint=AlertLevel.WARNING,
        ))
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


def seed_default_users(db: Session) -> None:
    defaults = [
        {
            "username": "admin",
            "password": "123456",
            "phone": "13900139000",
            "role": "admin",
        },
        {
            "username": "user",
            "password": "123456",
            "phone": "13800138000",
            "role": "user",
        },
    ]
    for item in defaults:
        exists = db.query(User).filter(User.username == item["username"]).first()
        if exists:
            continue
        user = User(
            username=item["username"],
            password_hash=hash_password(item["password"]),
            role=item["role"],
        )
        assign_phone(user, item["phone"])
        db.add(user)
    db.commit()


@router.post("/sms/send")
def send_sms_code(body: SendSmsCodeRequest, db: Session = Depends(get_db)):
    user = find_user_by_phone(db, body.phone)

    if body.scene == "login" and not user:
        return fail("该手机号未注册，请先注册", auth_error_code="NOT_REGISTERED")

    if body.scene == "register" and user:
        return fail("该手机号已注册，请前往登录", auth_error_code="ALREADY_REGISTERED")

    if body.scene == "bind" and user:
        return fail("该手机号已被其他账号绑定", auth_error_code="ALREADY_REGISTERED")

    if body.scene == "rebind_new" and user:
        return fail("该手机号已被其他账号绑定", auth_error_code="ALREADY_REGISTERED")

    dispatch_sms_code(db, body.phone, body.scene)
    return ok(message="验证码已发送")


@router.post("/sms/verify")
def verify_sms_code(body: VerifySmsCodeRequest, db: Session = Depends(get_db)):
    error = check_code(db, f"phone:{body.phone}", body.code)
    if error:
        return fail(error)
    return ok(message="验证码正确")


@router.post("/email/send")
def send_email_code(body: SendEmailCodeRequest, db: Session = Depends(get_db)):
    user = find_user_by_email(db, body.email)

    if body.scene == "login" and not user:
        return fail("该邮箱未注册，请先注册", auth_error_code="NOT_REGISTERED")

    if body.scene == "register" and user:
        return fail("该邮箱已注册，请前往登录", auth_error_code="ALREADY_REGISTERED")

    if body.scene == "bind" and user:
        return fail("该邮箱已被其他账号绑定", auth_error_code="ALREADY_REGISTERED")

    if body.scene == "rebind_new" and user:
        return fail("该邮箱已被其他账号绑定", auth_error_code="ALREADY_REGISTERED")

    message, error = dispatch_email_code(db, body.email, body.scene)
    if error:
        return error
    return ok(message=message or "验证码已发送")


@router.post("/register")
def register(body: RegisterRequest, request: Request, db: Session = Depends(get_db)):
    if body.username.lower() in RESERVED_USERNAMES:
        return fail("该用户名不可注册")

    code_error = verify_code(db, f"phone:{body.phone}", body.code)
    if code_error:
        return fail(code_error)

    if db.query(User).filter(User.username == body.username).first():
        return fail("该用户名已注册，请前往登录", auth_error_code="ALREADY_REGISTERED")

    if find_user_by_phone(db, body.phone):
        return fail("该手机号已注册，请前往登录", auth_error_code="ALREADY_REGISTERED")

    if body.email and find_user_by_email(db, body.email):
        return fail("该邮箱已注册，请前往登录", auth_error_code="ALREADY_REGISTERED")

    if body.email:
        email_code_error = verify_code(db, f"email:{body.email}", body.email_code or "")
        if email_code_error:
            return fail(email_code_error)

    user = User(
        username=body.username,
        password_hash=hash_password(body.password),
        role="user",
    )
    assign_phone(user, body.phone)
    if body.email:
        assign_email(user, body.email)
    db.add(user)
    db.commit()
    db.refresh(user)
    logger.info(f"新用户注册: {user.username} (id={user.id})")
    log_operation(
        db,
        action="register",
        user=user,
        success=True,
        request=request,
        detail={"phone": body.phone, "email": body.email},
    )
    return ok(build_auth_response(user).model_dump())


@router.post("/login")
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == body.username).first()
    if not user:
        log_operation(
            db,
            action="login_failed",
            username=body.username,
            success=False,
            message="用户名未注册",
            request=request,
            detail={"method": "password"},
        )
        return fail("该用户名未注册，请先注册", auth_error_code="NOT_REGISTERED")
    if not verify_password(body.password, user.password_hash):
        log_operation(
            db,
            action="login_failed",
            user=user,
            success=False,
            message="密码错误",
            request=request,
            detail={"method": "password"},
        )
        event_collector.collect(AnomalyEvent(
            source="auth",
            anomaly_type="auth_login_failure",
            title="登录失败：密码错误",
            detail={"username": body.username, "method": "password"},
        ))
        return fail("密码错误")
    if body.portal == "user" and user.role == "admin":
        log_operation(
            db,
            action="login_failed",
            user=user,
            success=False,
            message="请使用管理员登录入口",
            request=request,
            detail={"method": "password", "portal": body.portal},
        )
        return fail("请使用管理员登录入口")
    if body.portal == "admin" and user.role != "admin":
        log_operation(
            db,
            action="login_failed",
            user=user,
            success=False,
            message="该账号不是管理员",
            request=request,
            detail={"method": "password", "portal": body.portal},
        )
        return fail("该账号不是管理员")
    log_operation(
        db,
        action="login",
        user=user,
        success=True,
        request=request,
        detail={"method": "password", "portal": body.portal},
    )
    return ok(build_auth_response(user).model_dump())


@router.post("/sms/login")
def login_by_phone(body: PhoneLoginRequest, request: Request, db: Session = Depends(get_db)):
    code_error = verify_code(db, f"phone:{body.phone}", body.code)
    if code_error:
        return fail(code_error)

    user = find_user_by_phone(db, body.phone)
    if not user:
        return fail("该手机号未注册，请先注册", auth_error_code="NOT_REGISTERED")
    if user.role == "admin":
        return fail("管理员请使用账号密码登录")
    log_operation(
        db,
        action="login_phone",
        user=user,
        success=True,
        request=request,
        detail={"phone": body.phone},
    )
    return ok(build_auth_response(user).model_dump())


@router.post("/email/login")
def login_by_email(body: EmailLoginRequest, request: Request, db: Session = Depends(get_db)):
    code_error = verify_code(db, f"email:{body.email}", body.code)
    if code_error:
        return fail(code_error)

    user = find_user_by_email(db, body.email)
    if not user:
        return fail("该邮箱未注册，请先注册", auth_error_code="NOT_REGISTERED")
    if user.role == "admin":
        return fail("管理员请使用账号密码登录")
    log_operation(
        db,
        action="login_email",
        user=user,
        success=True,
        request=request,
        detail={"email": body.email},
    )
    return ok(build_auth_response(user).model_dump())


@router.get("/me")
def get_me(user: User | None = Depends(get_current_user)):
    if not user:
        return fail("未登录或登录已过期", code=401)
    return ok(user_to_out(user).model_dump())


@router.put("/profile")
def update_profile(
    body: UpdateProfileRequest,
    request: Request,
    user: User = Depends(require_current_user),
    db: Session = Depends(get_db),
):
    old_nickname = user.nickname
    if body.nickname is not None:
        user.nickname = body.nickname
    db.commit()
    db.refresh(user)
    log_operation(
        db,
        action="profile_update",
        user=user,
        success=True,
        request=request,
        detail={"old_nickname": old_nickname, "new_nickname": user.nickname},
    )
    return ok(user_to_out(user).model_dump())


@router.post("/bind/phone")
def bind_phone(
    body: BindPhoneRequest,
    request: Request,
    user: User = Depends(require_current_user),
    db: Session = Depends(get_db),
):
    if user.phone:
        return fail("您已绑定手机号")

    code_error = verify_code(db, f"phone:{body.phone}", body.code)
    if code_error:
        return fail(code_error)

    owner = find_user_by_phone(db, body.phone)
    if owner and owner.id != user.id:
        return fail("该手机号已被其他账号绑定", auth_error_code="ALREADY_REGISTERED")

    assign_phone(user, body.phone)
    db.commit()
    db.refresh(user)
    logger.info(f"用户 {user.username} 绑定手机号: {body.phone}")
    log_operation(db, action="bind_phone", user=user, success=True, request=request, detail={"phone": body.phone})
    return ok(user_to_out(user).model_dump())


@router.post("/bind/email")
def bind_email(
    body: BindEmailRequest,
    request: Request,
    user: User = Depends(require_current_user),
    db: Session = Depends(get_db),
):
    if user.email:
        return fail("您已绑定邮箱")

    code_error = verify_code(db, f"email:{body.email}", body.code)
    if code_error:
        return fail(code_error)

    owner = find_user_by_email(db, body.email)
    if owner and owner.id != user.id:
        return fail("该邮箱已被其他账号绑定", auth_error_code="ALREADY_REGISTERED")

    assign_email(user, body.email)
    db.commit()
    db.refresh(user)
    logger.info(f"用户 {user.username} 绑定邮箱: {body.email}")
    log_operation(db, action="bind_email", user=user, success=True, request=request, detail={"email": body.email})
    return ok(user_to_out(user).model_dump())


@router.post("/account/sms/send")
def send_secure_sms_code(
    body: SecureSmsCodeRequest,
    user: User = Depends(require_current_user),
    db: Session = Depends(get_db),
):
    phone = get_phone_plain(user)
    if not phone:
        return fail("您尚未绑定手机号")

    if body.scene == "unbind":
        guard = ensure_can_remove_method(user, "phone")
        if guard:
            return fail(guard)

    dispatch_sms_code(db, phone, body.scene)
    return ok(message="验证码已发送")


@router.post("/account/email/send")
def send_secure_email_code(
    body: SecureEmailCodeRequest,
    user: User = Depends(require_current_user),
    db: Session = Depends(get_db),
):
    email = get_email_plain(user)
    if not email:
        return fail("您尚未绑定邮箱")

    if body.scene == "unbind":
        guard = ensure_can_remove_method(user, "email")
        if guard:
            return fail(guard)

    message, error = dispatch_email_code(db, email, body.scene)
    if error:
        return error
    return ok(message=message or "验证码已发送")


@router.post("/unbind/phone")
def unbind_phone(
    body: UnbindCodeRequest,
    request: Request,
    user: User = Depends(require_current_user),
    db: Session = Depends(get_db),
):
    guard = ensure_can_remove_method(user, "phone")
    if guard:
        return fail(guard)

    phone = get_phone_plain(user)
    if not phone:
        return fail("您尚未绑定手机号")

    code_error = verify_code(db, f"phone:{phone}", body.code)
    if code_error:
        return fail(code_error)

    assign_phone(user, None)
    db.commit()
    db.refresh(user)
    logger.info(f"用户 {user.username} 解绑手机号")
    log_operation(db, action="unbind_phone", user=user, success=True, request=request)
    return ok(user_to_out(user).model_dump())


@router.post("/unbind/email")
def unbind_email(
    body: UnbindCodeRequest,
    request: Request,
    user: User = Depends(require_current_user),
    db: Session = Depends(get_db),
):
    guard = ensure_can_remove_method(user, "email")
    if guard:
        return fail(guard)

    email = get_email_plain(user)
    if not email:
        return fail("您尚未绑定邮箱")

    code_error = verify_code(db, f"email:{email}", body.code)
    if code_error:
        return fail(code_error)

    assign_email(user, None)
    db.commit()
    db.refresh(user)
    logger.info(f"用户 {user.username} 解绑邮箱")
    log_operation(db, action="unbind_email", user=user, success=True, request=request)
    return ok(user_to_out(user).model_dump())


@router.post("/rebind/phone")
def rebind_phone(
    body: RebindPhoneRequest,
    request: Request,
    user: User = Depends(require_current_user),
    db: Session = Depends(get_db),
):
    phone = get_phone_plain(user)
    if not phone:
        return fail("您尚未绑定手机号，请使用绑定功能")

    code_error = verify_code(db, f"phone:{phone}", body.old_code)
    if code_error:
        return fail(f"原手机号验证失败：{code_error}")

    new_code_error = verify_code(db, f"phone:{body.new_phone}", body.new_code)
    if new_code_error:
        return fail(f"新手机号验证失败：{new_code_error}")

    owner = find_user_by_phone(db, body.new_phone)
    if owner and owner.id != user.id:
        return fail("该手机号已被其他账号绑定", auth_error_code="ALREADY_REGISTERED")

    assign_phone(user, body.new_phone)
    db.commit()
    db.refresh(user)
    logger.info(f"用户 {user.username} 换绑手机号: {body.new_phone}")
    log_operation(
        db,
        action="rebind_phone",
        user=user,
        success=True,
        request=request,
        detail={"new_phone": body.new_phone},
    )
    return ok(user_to_out(user).model_dump())


@router.post("/rebind/email")
def rebind_email(
    body: RebindEmailRequest,
    request: Request,
    user: User = Depends(require_current_user),
    db: Session = Depends(get_db),
):
    email = get_email_plain(user)
    if not email:
        return fail("您尚未绑定邮箱，请使用绑定功能")

    code_error = verify_code(db, f"email:{email}", body.old_code)
    if code_error:
        return fail(f"原邮箱验证失败：{code_error}")

    new_code_error = verify_code(db, f"email:{body.new_email}", body.new_code)
    if new_code_error:
        return fail(f"新邮箱验证失败：{new_code_error}")

    owner = find_user_by_email(db, body.new_email)
    if owner and owner.id != user.id:
        return fail("该邮箱已被其他账号绑定", auth_error_code="ALREADY_REGISTERED")

    assign_email(user, body.new_email)
    db.commit()
    db.refresh(user)
    logger.info(f"用户 {user.username} 换绑邮箱: {body.new_email}")
    log_operation(
        db,
        action="rebind_email",
        user=user,
        success=True,
        request=request,
        detail={"new_email": body.new_email},
    )
    return ok(user_to_out(user).model_dump())


@router.post("/account/change-password")
def change_password(
    body: ChangePasswordRequest,
    request: Request,
    user: User = Depends(require_current_user),
    db: Session = Depends(get_db),
):
    methods = list_login_methods(user)

    if body.verify_method == "password":
        if "password" not in methods:
            return fail("当前账号不支持密码验证")
        if not body.old_password or not verify_password(body.old_password, user.password_hash):
            return fail("原密码错误")
    elif body.verify_method == "phone":
        phone = get_phone_plain(user)
        if not phone:
            return fail("您尚未绑定手机号")
        if not body.code:
            return fail("请输入验证码")
        code_error = verify_code(db, f"phone:{phone}", body.code)
        if code_error:
            return fail(code_error)
    elif body.verify_method == "email":
        email = get_email_plain(user)
        if not email:
            return fail("您尚未绑定邮箱")
        if not body.code:
            return fail("请输入验证码")
        code_error = verify_code(db, f"email:{email}", body.code)
        if code_error:
            return fail(code_error)
    else:
        return fail("不支持的验证方式")

    user.password_hash = hash_password(body.new_password)
    db.commit()
    db.refresh(user)
    logger.info(f"用户 {user.username} 修改密码")
    log_operation(
        db,
        action="change_password",
        user=user,
        success=True,
        request=request,
        detail={"verify_method": body.verify_method},
    )
    return ok(user_to_out(user).model_dump())


@router.post("/account/delete")
def delete_account(
    body: DeleteAccountRequest,
    request: Request,
    user: User = Depends(require_current_user),
    db: Session = Depends(get_db),
):
    guard = can_delete_account(user)
    if guard:
        return fail(guard)

    methods = list_login_methods(user)

    if body.verify_method == "password":
        if "password" not in methods:
            return fail("当前账号不支持密码验证")
        if not body.password or not verify_password(body.password, user.password_hash):
            return fail("密码验证失败")
    elif body.verify_method == "phone":
        phone = get_phone_plain(user)
        if not phone:
            return fail("您尚未绑定手机号")
        if not body.code:
            return fail("请输入验证码")
        code_error = verify_code(db, f"phone:{phone}", body.code)
        if code_error:
            return fail(code_error)
    elif body.verify_method == "email":
        email = get_email_plain(user)
        if not email:
            return fail("您尚未绑定邮箱")
        if not body.code:
            return fail("请输入验证码")
        code_error = verify_code(db, f"email:{email}", body.code)
        if code_error:
            return fail(code_error)
    else:
        return fail("不支持的验证方式")

    username = user.username
    user_id = user.id
    user_role = user.role
    log_operation(
        db,
        action="delete_account",
        user_id=user_id,
        username=username,
        role=user_role,
        success=True,
        request=request,
        detail={"verify_method": body.verify_method},
    )
    db.delete(user)
    db.commit()
    logger.info(f"用户注销账号: {username}")
    return ok(message="账号已注销")
