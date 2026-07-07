from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(11), unique=True)
    email: Mapped[str | None] = mapped_column(String(100), unique=True)
    role: Mapped[str] = mapped_column(String(10), default="user")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class VerificationCode(Base):
    __tablename__ = "verification_codes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    target: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(6), nullable=False)
    scene: Mapped[str] = mapped_column(String(20), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
