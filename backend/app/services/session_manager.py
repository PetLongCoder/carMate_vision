"""
WebSocket 追踪会话管理器
=========================

管理实时车牌追踪的会话生命周期:
- 创建/销毁处理会话
- 管理 WebSocket 连接注册与消息广播
- 协调后台帧处理任务

每个会话对应一个视频文件或流 URL 的处理任务。
"""
import asyncio
import time
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from app.utils.logger import logger


class SessionType(str, Enum):
    VIDEO = "video"
    STREAM = "stream"


class SessionStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    ERROR = "error"
    STOPPED = "stopped"


class TrackingSession:
    """
    单个追踪会话

    维护: 状态, 追踪器, 视频源, WebSocket 连接池,
          以及关联的 VideoStreamProcessor (用于生成汇总数据)
    """

    def __init__(self, session_id: str, session_type: SessionType,
                 source: str, total_frames: int = 0):
        self.session_id = session_id
        self.type = session_type
        self.source = source
        self.status = SessionStatus.PENDING
        self.total_frames = total_frames
        self.processed_frames = 0
        self.fps = 30.0
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = self.created_at
        self.error_message: Optional[str] = None

        # 可选的处理器引用 (由后台任务设置, 用于获取追踪汇总)
        self.processor: Optional[object] = None  # VideoStreamProcessor

        # 最新标注帧 (JPEG bytes) — 用于 MJPEG 流推送
        self.latest_frame: Optional[bytes] = None
        self._frame_cond = asyncio.Condition()

        # WebSocket 连接池 (同一会话可多终端订阅)
        self._ws_connections: list[asyncio.Queue] = []
        self._lock = asyncio.Lock()

    async def set_frame(self, jpeg_bytes: bytes):
        """更新最新帧并通知等待者 (MJPEG 流用)"""
        async with self._frame_cond:
            self.latest_frame = jpeg_bytes
            self._frame_cond.notify_all()

    # ── 连接管理 ────────────────────────────────────

    async def register_ws(self, queue: asyncio.Queue):
        """注册一个新的 WebSocket 订阅者"""
        async with self._lock:
            self._ws_connections.append(queue)
            logger.info(f"会话 {self.session_id}: WebSocket 已注册 (共 {len(self._ws_connections)} 个)")

    async def unregister_ws(self, queue: asyncio.Queue):
        """注销一个 WebSocket 订阅者"""
        async with self._lock:
            try:
                self._ws_connections.remove(queue)
            except ValueError:
                pass
            logger.info(f"会话 {self.session_id}: WebSocket 已注销 (剩 {len(self._ws_connections)} 个)")

    async def broadcast(self, message: dict):
        """向所有订阅者广播消息"""
        async with self._lock:
            dead = []
            for queue in self._ws_connections:
                try:
                    await queue.put(message)
                except Exception:
                    dead.append(queue)
            for q in dead:
                self._ws_connections.remove(q)

    @property
    def ws_count(self) -> int:
        return len(self._ws_connections)

    # ── 状态更新 ────────────────────────────────────

    def update_status(self, status: SessionStatus, message: Optional[str] = None):
        self.status = status
        self.updated_at = datetime.now(timezone.utc)
        if message:
            self.error_message = message

    def to_dict(self) -> dict:
        return {
            "sessionId": self.session_id,
            "type": self.type.value,
            "status": self.status.value,
            "source": self.source,
            "totalFrames": self.total_frames,
            "processedFrames": self.processed_frames,
            "fps": self.fps,
            "wsConnections": self.ws_count,
            "createdAt": self.created_at.isoformat(),
            "updatedAt": self.updated_at.isoformat(),
            "errorMessage": self.error_message,
        }


# ═══════════════════════════════════════════════════════════
#  SessionManager — 全局会话管理器 (单例)
# ═══════════════════════════════════════════════════════════

class SessionManager:
    """
    全局追踪会话管理器

    单例模式, 维护所有活跃会话的映射。
    提供会话 CRUD 和广播功能。
    """

    def __init__(self):
        self._sessions: dict[str, TrackingSession] = {}
        self._lock = asyncio.Lock()

    async def create_session(self, session_type: SessionType, source: str,
                             total_frames: int = 0) -> TrackingSession:
        """创建新会话并返回"""
        session_id = uuid.uuid4().hex[:12]
        session = TrackingSession(session_id, session_type, source, total_frames)
        async with self._lock:
            self._sessions[session_id] = session
        logger.info(f"创建会话 {session_id}: {session_type.value} | {source}")
        return session

    async def get_session(self, session_id: str) -> Optional[TrackingSession]:
        async with self._lock:
            return self._sessions.get(session_id)

    async def remove_session(self, session_id: str):
        """移除会话 (主动停止后清理)"""
        async with self._lock:
            self._sessions.pop(session_id, None)
        logger.info(f"移除会话 {session_id}")

    async def list_sessions(self, status_filter: Optional[SessionStatus] = None) -> list[dict]:
        """列出所有会话 (用于管理 API)"""
        async with self._lock:
            sessions = list(self._sessions.values())
        if status_filter:
            sessions = [s for s in sessions if s.status == status_filter]
        return [s.to_dict() for s in sessions]

    async def get_active_count(self) -> int:
        async with self._lock:
            return sum(1 for s in self._sessions.values()
                       if s.status in (SessionStatus.PENDING, SessionStatus.PROCESSING))


# 全局单例
session_manager = SessionManager()
