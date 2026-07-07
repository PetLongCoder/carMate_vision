import random
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from typing import Annotated

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_access_token, decode_access_token, hash_password, verify_password
from app.models.auth_schemas import (
    AuthResponse,
    EmailLoginRequest,
    LoginRequest,
    PhoneLoginRequest,
    RegisterRequest,
    SendEmailCodeRequest,
    SendSmsCodeRequest,
    UserOut,
    VerifySmsCodeRequest,
)
from app.models.db_models import User, VerificationCode
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
        phone=user.phone,
        email=user.email,
    )


def build_auth_response(user: User) -> AuthResponse:
    token = create_access_token(str(user.id), {"role": user.role, "username": user.username})
    return AuthResponse(token=token, user=user_to_out(user))


def generate_code() -> str:
    return f"{random.randint(100000, 999999)}"


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


def seed_default_users(db: Session) -> None:
    defaults = [
        {
            "username": "admin",
            "password": "123456",
            "phone": "13900139000",
            "email": "admin@example.com",
            "role": "admin",
        },
        {
            "username": "user",
            "password": "123456",
            "phone": "13800138000",
            "email": "user@example.com",
            "role": "user",
        },
    ]
    for item in defaults:
        exists = db.query(User).filter(User.username == item["username"]).first()
        if exists:
            continue
        db.add(
            User(
                username=item["username"],
                password_hash=hash_password(item["password"]),
                phone=item["phone"],
                email=item["email"],
                role=item["role"],
            )
        )
    db.commit()


@router.post("/sms/send")
def send_sms_code(body: SendSmsCodeRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.phone == body.phone).first()

    if body.scene == "login" and not user:
        return fail("该手机号未注册，请先注册", auth_error_code="NOT_REGISTERED")

    if body.scene == "register" and user:
        return fail("该手机号已注册，请前往登录", auth_error_code="ALREADY_REGISTERED")

    code = generate_code()
    save_code(db, f"phone:{body.phone}", body.scene, code)
    logger.info(f"[SMS Code] {body.phone} scene={body.scene} code={code}")
    return ok(message="验证码已发送")


@router.post("/sms/verify")
def verify_sms_code(body: VerifySmsCodeRequest, db: Session = Depends(get_db)):
    error = check_code(db, f"phone:{body.phone}", body.code)
    if error:
        return fail(error)
    return ok(message="验证码正确")


@router.post("/email/send")
def send_email_code(body: SendEmailCodeRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email).first()

    if body.scene == "login" and not user:
        return fail("该邮箱未注册，请先注册", auth_error_code="NOT_REGISTERED")

    if body.scene == "register" and user:
        return fail("该邮箱已注册，请前往登录", auth_error_code="ALREADY_REGISTERED")

    code = generate_code()
    save_code(db, f"email:{body.email}", body.scene, code)
    logger.info(f"[Email Code] {body.email} scene={body.scene} code={code}")
    return ok(message="验证码已发送")


@router.post("/register")
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    if body.username.lower() in RESERVED_USERNAMES:
        return fail("该用户名不可注册")

    code_error = verify_code(db, f"phone:{body.phone}", body.code)
    if code_error:
        return fail(code_error)

    if db.query(User).filter(User.username == body.username).first():
        return fail("该用户名已注册，请前往登录", auth_error_code="ALREADY_REGISTERED")

    if db.query(User).filter(User.phone == body.phone).first():
        return fail("该手机号已注册，请前往登录", auth_error_code="ALREADY_REGISTERED")

    if body.email and db.query(User).filter(User.email == body.email).first():
        return fail("该邮箱已注册，请前往登录", auth_error_code="ALREADY_REGISTERED")

    user = User(
        username=body.username,
        password_hash=hash_password(body.password),
        phone=body.phone,
        email=body.email,
        role="user",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    logger.info(f"新用户注册: {user.username} (id={user.id})")
    return ok(build_auth_response(user).model_dump())


@router.post("/login")
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == body.username).first()
    if not user:
        return fail("该用户名未注册，请先注册", auth_error_code="NOT_REGISTERED")
    if not verify_password(body.password, user.password_hash):
        return fail("密码错误")
    return ok(build_auth_response(user).model_dump())


@router.post("/sms/login")
def login_by_phone(body: PhoneLoginRequest, db: Session = Depends(get_db)):
    code_error = verify_code(db, f"phone:{body.phone}", body.code)
    if code_error:
        return fail(code_error)

    user = db.query(User).filter(User.phone == body.phone).first()
    if not user:
        return fail("该手机号未注册，请先注册", auth_error_code="NOT_REGISTERED")
    if user.role == "admin":
        return fail("管理员请使用账号密码登录")
    return ok(build_auth_response(user).model_dump())


@router.post("/email/login")
def login_by_email(body: EmailLoginRequest, db: Session = Depends(get_db)):
    code_error = verify_code(db, f"email:{body.email}", body.code)
    if code_error:
        return fail(code_error)

    user = db.query(User).filter(User.email == body.email).first()
    if not user:
        return fail("该邮箱未注册，请先注册", auth_error_code="NOT_REGISTERED")
    if user.role == "admin":
        return fail("管理员请使用账号密码登录")
    return ok(build_auth_response(user).model_dump())


@router.get("/me")
def get_me(user: User | None = Depends(get_current_user)):
    if not user:
        return fail("未登录或登录已过期", code=401)
    return ok(user_to_out(user).model_dump())
