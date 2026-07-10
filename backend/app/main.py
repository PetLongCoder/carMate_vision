"""
CarMate 车载视觉系统 — 主入口
==============================

包含:
- REST API (auth, alerts, history, stats, plate, driver_gesture, police_gesture)
- WebSocket 实时车牌追踪端点 (/api/ws/plate/track/{session_id})
- 通用 WebSocket 端点 (/ws)
- 后台视频/流处理任务管理
"""
import asyncio
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import (
    admin_history,
    admin_logs,
    auth,
    driver_gesture,
    plate,
    police_gesture,
    alerts,
    history,
    stats,
    wechat,
)
from app.core.database import SessionLocal, init_db
from app.api.v1.auth import seed_default_users
from app.services.session_manager import (
    SessionStatus,
    SessionType,
    session_manager,
)
from app.services.video_processor import run_video_session
from app.utils.logger import logger


# ═══════════════════════════════════════════════════════════
#  应用实例
# ═══════════════════════════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 CarMate 服务启动成功")
    # 初始化数据库
    try:
        init_db()
        db = SessionLocal()
        try:
            seed_default_users(db)
        finally:
            db.close()
        logger.info("数据库初始化完成")
    except Exception as e:
        logger.warning(f"数据库初始化跳过: {e}")
    cleanup_task = asyncio.create_task(_cleanup_loop())
    yield
    cleanup_task.cancel()
    logger.info("CarMate 服务已关闭")


app = FastAPI(
    title="CarMate 车载视觉系统",
    version="2.0.0",
    docs_url="/docs",
    description="智能车载视觉感知系统后端 API — 支持实时车牌追踪",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册所有路由 (统一前缀 /api)
app.include_router(auth.router, prefix="/api", tags=["用户认证"])
app.include_router(admin_logs.router, prefix="/api", tags=["管理员"])
app.include_router(admin_history.router, prefix="/api", tags=["管理员"])
app.include_router(wechat.router, prefix="/api", tags=["微信登录(Mock)"])
app.include_router(driver_gesture.router, prefix="/api", tags=["车主手势控车"])
app.include_router(plate.router, prefix="/api", tags=["车牌识别"])
app.include_router(police_gesture.router, prefix="/api", tags=["交警手势识别"])
app.include_router(alerts.router, prefix="/api", tags=["告警管理"])
app.include_router(history.router, prefix="/api", tags=["历史记录"])
app.include_router(stats.router, prefix="/api", tags=["仪表盘统计"])


# ═══════════════════════════════════════════════════════════
#  根路径
# ═══════════════════════════════════════════════════════════

@app.get("/")
async def root():
    return {
        "message": "CarMate 后端服务已启动",
        "version": "2.0.0",
        "docs": "/docs",
    }


@app.get("/api/health")
async def health_check():
    """健康检查 + 会话统计"""
    active = await session_manager.get_active_count()
    sessions = await session_manager.list_sessions()
    return {
        "status": "ok",
        "activeSessions": active,
        "totalSessions": len(sessions),
    }


# ═══════════════════════════════════════════════════════════
#  通用 WebSocket (心跳/告警推送)
# ═══════════════════════════════════════════════════════════

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("WebSocket 客户端已连接 (通用)")
    try:
        while True:
            data = await websocket.receive_text()
            logger.debug(f"WebSocket 收到: {data}")
            await websocket.send_json({"type": "pong", "data": data})
    except WebSocketDisconnect:
        logger.info("WebSocket 客户端断开连接 (通用)")


# ═══════════════════════════════════════════════════════════
#  WebSocket 实时车牌追踪
# ═══════════════════════════════════════════════════════════

@app.websocket("/api/ws/plate/track/{session_id}")
async def ws_plate_track(websocket: WebSocket, session_id: str):
    """
    WebSocket 实时车牌追踪端点

    客户端连接流程:
    1. 先通过 REST API 创建会话 (POST /api/plate/track 上传视频)
    2. 获得 session_id 后, 连接到此 WebSocket
    3. 后端开始推送逐帧检测结果 JSON

    推送消息格式:
    - {"type":"detection","sessionId":"...","frameNumber":N,
       "timestamp":1.5,"detections":[...]}
    - {"type":"status","sessionId":"...","status":"processing",
       "progress":0.5,"framesProcessed":50}
    - {"type":"summary","sessionId":"...","plates":[...]}
    - {"type":"error","sessionId":"...","message":"..."}
    """
    session = await session_manager.get_session(session_id)
    if session is None:
        await websocket.accept()
        await websocket.send_json({
            "type": "error",
            "message": f"会话 {session_id} 不存在或已过期",
        })
        await websocket.close(code=4004)
        return

    await websocket.accept()
    queue: asyncio.Queue = asyncio.Queue(maxsize=256)
    await session.register_ws(queue)

    # 后台任务: 接收前端播放控制消息 (play/pause/seek/sync)
    async def client_reader():
        try:
            while True:
                data = await websocket.receive_text()
                try:
                    msg = __import__("json").loads(data)
                    session.put_client_message(msg)
                except Exception:
                    pass
        except WebSocketDisconnect:
            pass
        except Exception:
            pass

    reader_task = asyncio.create_task(client_reader())

    try:
        # 如果会话还没开始处理, 立即启动后台任务
        if session.status in (SessionStatus.PENDING,):
            asyncio.create_task(run_video_session(session))

        # 持续从队列读取并推送给客户端
        while True:
            try:
                msg = await asyncio.wait_for(queue.get(), timeout=30)
                await websocket.send_json(msg)

                # 终端消息 → 关闭连接
                if msg.get("type") in ("summary", "error"):
                    logger.info(f"会话 {session_id}: 收到终端消息, 关闭 WebSocket")
                    break

            except asyncio.TimeoutError:
                # 心跳: 30 秒无消息则发一次 status
                progress = (
                    session.processed_frames / session.total_frames
                    if session.total_frames > 0 else 0
                )
                try:
                    await websocket.send_json({
                        "type": "status",
                        "sessionId": session_id,
                        "status": session.status.value,
                        "progress": round(progress, 4),
                        "framesProcessed": session.processed_frames,
                        "totalFrames": session.total_frames,
                    })
                except Exception:
                    break  # 发送失败, 客户端可能已断开

                # 如果处理已完成但队列空了, 发 summary 后退出
                if session.status in (SessionStatus.COMPLETED,
                                      SessionStatus.ERROR,
                                      SessionStatus.STOPPED):
                    break

    except WebSocketDisconnect:
        logger.info(f"WebSocket 断开: 会话 {session_id}")
    except Exception as exc:
        logger.exception(f"WebSocket 异常 [{session_id}]: {exc}")
    finally:
        reader_task.cancel()
        await session.unregister_ws(queue)
        # 所有 WebSocket 断开后自动停止会话（避免后台残留）
        if session.ws_count == 0:
            if session.status in (SessionStatus.PENDING, SessionStatus.PROCESSING):
                logger.info(f"会话 {session_id}: WebSocket 已全部断开, 自动停止")
                session.update_status(SessionStatus.STOPPED, "前端页面刷新/关闭")


# ═══════════════════════════════════════════════════════════
#  定期清理任务
# ═══════════════════════════════════════════════════════════

async def _cleanup_loop():
    """每 5 分钟清理一次已完成的旧会话 (超过 5 分钟的)"""
    while True:
        await asyncio.sleep(300)
        try:
            sessions = await session_manager.list_sessions()
            now = time.time()
            for s in sessions:
                if s["status"] in ("completed", "error", "stopped"):
                    sess = await session_manager.get_session(s["sessionId"])
                    if sess is None:
                        continue
                    age = (time.mktime(sess.updated_at.timetuple())
                           if hasattr(sess.updated_at, "timetuple") else 0)
                    if age and (now - age) > 300:
                        await session_manager.remove_session(s["sessionId"])
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════
#  直接运行入口
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    import os

    port = int(os.getenv("CARMATE_MAIN_PORT", "8001"))
    print("=" * 60)
    print("CarMate 主 API 服务")
    print("=" * 60)
    print(f"端口: {port}")
    print(f"API 文档: http://localhost:{port}/docs")
    print(f"健康检查: http://localhost:{port}/api/health")
    print("=" * 60)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
