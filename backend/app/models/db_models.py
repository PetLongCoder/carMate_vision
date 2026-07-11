from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(255), unique=True)
    email: Mapped[str | None] = mapped_column(String(255), unique=True)
    role: Mapped[str] = mapped_column(String(10), default="user")
    wechat_openid: Mapped[str | None] = mapped_column(String(255), unique=True)
    wechat_unionid: Mapped[str | None] = mapped_column(String(255), unique=True)
    nickname: Mapped[str | None] = mapped_column(String(64))
    avatar_url: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class UserOperationLog(Base):
    __tablename__ = "user_operation_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(Integer, index=True)
    username: Mapped[str | None] = mapped_column(String(50), index=True)
    role: Mapped[str | None] = mapped_column(String(10))
    action: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    message: Mapped[str | None] = mapped_column(String(255))
    detail: Mapped[str | None] = mapped_column(Text)
    ip_address: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)


class HistoryRecord(Base):
    __tablename__ = "history_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(Integer, index=True)
    type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    image_url: Mapped[str | None] = mapped_column(String(500))
    result_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)


class RecognitionRecord(Base):
    __tablename__ = "recognition_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(Integer, index=True)
    type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    result_summary: Mapped[str | None] = mapped_column(String(255))
    confidence: Mapped[float | None] = mapped_column(Float)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)


class AlertRecord(Base):
    __tablename__ = "alert_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    level: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(String(100))
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)


class VerificationCode(Base):
    __tablename__ = "verification_codes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    target: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(6), nullable=False)
    scene: Mapped[str] = mapped_column(String(20), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class PlateRecord(Base):
    """车牌识别结果明细表 — 每行一个车牌"""
    __tablename__ = "plate_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # 关联到 history_records（不设物理外键约束，允许历史数据清理）
    history_record_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    # 追踪会话 ID（仅追踪/流场景有值）
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    # 用户 ID（反范式冗余，避免联表）
    user_id: Mapped[int | None] = mapped_column(Integer, index=True)
    # 车牌号码（核心查询字段）
    plate_no: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    # 车牌颜色: blue/green/yellow/white/black
    color: Mapped[str | None] = mapped_column(String(10))
    # 车辆类型: car/bus/truck/unknown
    vehicle_type: Mapped[str | None] = mapped_column(String(20))
    # 置信度 (0~1)
    confidence: Mapped[float | None] = mapped_column(Float)
    # 首次出现时间戳（秒，视频/追踪场景）
    first_seen: Mapped[float | None] = mapped_column(Float)
    # 最后出现时间戳（秒，视频/追踪场景）
    last_seen: Mapped[float | None] = mapped_column(Float)
    # 出现帧数（追踪场景）
    appearances: Mapped[int] = mapped_column(Integer, default=1)
    # 来源类型: image/video/track/stream
    source_type: Mapped[str | None] = mapped_column(String(10))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class PoliceGestureLog(Base):
    """交警手势识别日志 — 存储到云数据库"""
    __tablename__ = "police_gesture_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # 识别类型: image / video / video_stream / camera_stream
    recognition_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    # 视频会话 ID: 同一视频的所有手势段共享同一个 UUID, 用于分组
    video_session_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    # 文件名 (如有)
    filename: Mapped[str | None] = mapped_column(String(255))
    # 识别结果
    gesture: Mapped[str] = mapped_column(String(32), nullable=False, comment="手势名称")
    gesture_id: Mapped[int] = mapped_column(Integer, nullable=False, comment="手势ID(0-8)")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, comment="置信度")
    # 推理耗时 (毫秒)
    inference_ms: Mapped[float] = mapped_column(Float, nullable=False, comment="推理耗时(ms)")
    # Top-5 结果 (JSON 字符串)
    top5_json: Mapped[str | None] = mapped_column(Text, comment="Top-5识别结果JSON")
    # 视频相关字段
    frames_total: Mapped[int | None] = mapped_column(Integer, comment="视频总帧数")
    frames_processed: Mapped[int | None] = mapped_column(Integer, comment="实际处理帧数")
    video_fps: Mapped[float | None] = mapped_column(Float, comment="视频帧率")
    video_duration: Mapped[float | None] = mapped_column(Float, comment="视频时长(秒)")
    # 手势段 (视频模式, JSON)
    segments_json: Mapped[str | None] = mapped_column(Text, comment="手势段JSON")
    # 是否成功
    success: Mapped[bool] = mapped_column(default=True, comment="识别是否成功")
    # 错误信息
    error_message: Mapped[str | None] = mapped_column(Text, comment="错误信息")
    # 客户端 IP / User-Agent (可选)
    client_info: Mapped[str | None] = mapped_column(String(512), comment="客户端信息")
    # 时间戳
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
