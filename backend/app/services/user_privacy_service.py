"""用户隐私字段加解密与查库辅助。"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.crypto import (
    decrypt_field,
    encrypt_field,
    is_encrypted,
    looks_like_plain_email,
    looks_like_plain_phone,
    mask_email,
    mask_phone,
)
from app.models.db_models import User


def encrypt_phone(phone: str | None) -> str | None:
    if not phone:
        return None
    return encrypt_field("phone", phone)


def encrypt_email(email: str | None) -> str | None:
    if not email:
        return None
    return encrypt_field("email", email)


def encrypt_wechat_openid(openid: str | None) -> str | None:
    if not openid:
        return None
    return encrypt_field("wechat_openid", openid)


def encrypt_wechat_unionid(unionid: str | None) -> str | None:
    if not unionid:
        return None
    return encrypt_field("wechat_unionid", unionid)


def get_phone_plain(user: User) -> str | None:
    if not user.phone:
        return None
    return decrypt_field("phone", user.phone)


def get_email_plain(user: User) -> str | None:
    if not user.email:
        return None
    return decrypt_field("email", user.email)


def get_wechat_openid_plain(user: User) -> str | None:
    if not user.wechat_openid:
        return None
    return decrypt_field("wechat_openid", user.wechat_openid)


def masked_phone(user: User) -> str | None:
    return mask_phone(get_phone_plain(user))


def masked_email(user: User) -> str | None:
    return mask_email(get_email_plain(user))


def find_user_by_phone(db: Session, phone: str) -> User | None:
    token = encrypt_phone(phone)
    return db.query(User).filter(User.phone == token).first()


def find_user_by_email(db: Session, email: str) -> User | None:
    token = encrypt_email(email)
    return db.query(User).filter(User.email == token).first()


def find_user_by_wechat_openid(db: Session, openid: str) -> User | None:
    token = encrypt_wechat_openid(openid)
    return db.query(User).filter(User.wechat_openid == token).first()


def assign_phone(user: User, phone: str | None) -> None:
    user.phone = encrypt_phone(phone) if phone else None


def assign_email(user: User, email: str | None) -> None:
    user.email = encrypt_email(email) if email else None


def assign_wechat_openid(user: User, openid: str | None) -> None:
    user.wechat_openid = encrypt_wechat_openid(openid) if openid else None


def assign_wechat_unionid(user: User, unionid: str | None) -> None:
    user.wechat_unionid = encrypt_wechat_unionid(unionid) if unionid else None


def ensure_privacy_column_sizes(db: Session) -> None:
    """扩容 users 表隐私字段，兼容加密密文长度。"""
    alters = [
        "ALTER TABLE users MODIFY COLUMN phone VARCHAR(255) NULL",
        "ALTER TABLE users MODIFY COLUMN email VARCHAR(255) NULL",
        "ALTER TABLE users MODIFY COLUMN wechat_openid VARCHAR(255) NULL",
        "ALTER TABLE users MODIFY COLUMN wechat_unionid VARCHAR(255) NULL",
    ]
    for sql in alters:
        db.execute(text(sql))
    db.commit()


def migrate_user_privacy_fields(db: Session) -> int:
    """将 users 表中仍为明文的隐私字段批量加密。"""
    ensure_privacy_column_sizes(db)
    updated = 0
    for user in db.query(User).all():
        changed = False
        if user.phone and looks_like_plain_phone(user.phone):
            user.phone = encrypt_phone(user.phone)
            changed = True
        if user.email and looks_like_plain_email(user.email):
            user.email = encrypt_email(user.email)
            changed = True
        if user.wechat_openid and not is_encrypted(user.wechat_openid):
            user.wechat_openid = encrypt_wechat_openid(user.wechat_openid)
            changed = True
        if user.wechat_unionid and not is_encrypted(user.wechat_unionid):
            user.wechat_unionid = encrypt_wechat_unionid(user.wechat_unionid)
            changed = True
        if changed:
            updated += 1
    if updated:
        db.commit()
    return updated
