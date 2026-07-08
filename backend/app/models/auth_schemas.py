from typing import Literal, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator

SmsScene = Literal[
    "login",
    "register",
    "bind",
    "unbind",
    "rebind_old",
    "rebind_new",
    "delete",
]
EmailScene = Literal[
    "login",
    "register",
    "bind",
    "unbind",
    "rebind_old",
    "rebind_new",
    "delete",
]
VerifyMethod = Literal["password", "phone", "email"]
ChangePasswordVerifyMethod = Literal["password", "phone", "email"]


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str = Field(min_length=2, max_length=50)
    password: str = Field(min_length=6, max_length=128)
    phone: str = Field(pattern=r"^1[3-9]\d{9}$")
    code: str = Field(min_length=6, max_length=6)
    email: Optional[EmailStr] = None

    @field_validator("email", mode="before")
    @classmethod
    def empty_email_to_none(cls, value: object) -> object:
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        return value

class PhoneLoginRequest(BaseModel):
    phone: str = Field(pattern=r"^1[3-9]\d{9}$")
    code: str = Field(min_length=6, max_length=6)


class EmailLoginRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6)


class SendSmsCodeRequest(BaseModel):
    phone: str = Field(pattern=r"^1[3-9]\d{9}$")
    scene: SmsScene


class SendEmailCodeRequest(BaseModel):
    email: EmailStr
    scene: EmailScene


class SecureSmsCodeRequest(BaseModel):
    scene: Literal["unbind", "rebind_old", "delete", "change_password"]


class SecureEmailCodeRequest(BaseModel):
    scene: Literal["unbind", "rebind_old", "delete", "change_password"]


class VerifySmsCodeRequest(BaseModel):
    phone: str = Field(pattern=r"^1[3-9]\d{9}$")
    code: str = Field(min_length=6, max_length=6)


class BindPhoneRequest(BaseModel):
    phone: str = Field(pattern=r"^1[3-9]\d{9}$")
    code: str = Field(min_length=6, max_length=6)


class BindEmailRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6)


class UnbindCodeRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6)


class RebindPhoneRequest(BaseModel):
    old_code: str = Field(min_length=6, max_length=6)
    new_phone: str = Field(pattern=r"^1[3-9]\d{9}$")
    new_code: str = Field(min_length=6, max_length=6)


class RebindEmailRequest(BaseModel):
    old_code: str = Field(min_length=6, max_length=6)
    new_email: EmailStr
    new_code: str = Field(min_length=6, max_length=6)


class DeleteAccountRequest(BaseModel):
    verify_method: VerifyMethod
    password: Optional[str] = None
    code: Optional[str] = Field(default=None, min_length=6, max_length=6)


class ChangePasswordRequest(BaseModel):
    verify_method: ChangePasswordVerifyMethod
    old_password: Optional[str] = None
    code: Optional[str] = Field(default=None, min_length=6, max_length=6)
    new_password: str = Field(min_length=6, max_length=128)


class UpdateProfileRequest(BaseModel):
    nickname: Optional[str] = Field(default=None, max_length=64)

    @field_validator("nickname", mode="before")
    @classmethod
    def empty_nickname_to_none(cls, value: object) -> object:
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        return value.strip() if isinstance(value, str) else value


class UserOut(BaseModel):
    id: int
    username: str
    role: str
    phone: Optional[str] = None
    email: Optional[str] = None
    nickname: Optional[str] = None
    avatar_url: Optional[str] = None
    has_wechat: bool = False
    login_methods: list[str] = []

    model_config = {"from_attributes": True}


class AuthResponse(BaseModel):
    token: str
    user: UserOut


class WechatQrcodeResponse(BaseModel):
    state: str
    confirm_url: str
    qrcode_base64: str
    expires_in: int
    lan_ip: str
    network_hint: str


class WechatPollResponse(BaseModel):
    status: Literal["waiting", "confirmed", "expired"]
    auth: Optional[AuthResponse] = None


class WechatConfirmRequest(BaseModel):
    state: str
    mock_openid: Optional[str] = None
    nickname: Optional[str] = None
